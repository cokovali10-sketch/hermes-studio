#!/usr/bin/env python3
"""
Hermes Studio v3.1 — Agentic Tool Suite with Vision (100% offline).

Tools (OpenAI/Ollama function-calling compatible):
  workspace_file_ops      — read, write, create, delete, list, diff, search_replace, grep
  execute_shell_command   — run shell commands with timeout
  git_checkpoint          — auto-commit after each step
  analyze_project_structure — scan directory tree
  capture_screenshot      — take screenshot of screen/window
  read_image              — read image for vision analysis
  search_code             — search across codebase with regex
  done                    — signal task completion

Endpoints:
  GET  /api/health, /api/models, /api/tools, /api/workspace
  POST /api/chat, /api/agent, /api/upload
  POST /api/analyze_image  — vision analysis of uploaded image
  GET  /api/events         — SSE event stream
"""
import asyncio
import base64
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime

import aiohttp
import aiohttp_cors
from aiohttp import web

ROOT = pathlib.Path(__file__).parent
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
PORT = CFG["server"]["port"]
URL = f"http://127.0.0.1:{PORT}"
OLLAMA_HOST = CFG["ollama"]["host"]
OLLAMA_DIR = ROOT / ".ollama"
OLLAMA_EXE = OLLAMA_DIR / "ollama.exe"
OLLAMA_MODELS = str(OLLAMA_DIR / "models")
MODEL_REASONING = CFG["models"]["reasoning"]
MODEL_CODING = CFG["models"]["coding"]
MODEL_AGENT = CFG["models"].get("agent", MODEL_CODING)
MODEL_VISION = CFG["models"].get("vision", "llava:1.6-mistral")
UPLOAD_DIR = pathlib.Path(CFG["paths"]["uploads"])
WORKSPACE_DIR = pathlib.Path(CFG["paths"]["workspace"])
BACKUP_DIR = pathlib.Path(CFG["paths"]["backups"])
FRONTEND_DIR = ROOT / "frontend"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

MAX_TOOL_STEPS = CFG["limits"].get("max_tool_steps", 50)
SHELL_TIMEOUT = CFG["limits"].get("shell_timeout_sec", 120)
MAX_PROMPT_CHARS = CFG["limits"].get("max_prompt_chars", 32000)
AGENT_SYSTEM = CFG.get("agent", {}).get("system_prompt", "You are Hermes.")
MAX_ITERATIONS = CFG.get("agent", {}).get("max_iterations", 30)

try:
    from PIL import ImageGrab
    PILLOW_OK = True
except ImportError:
    PILLOW_OK = False
    print("[Hermes] Pillow not installed — screenshot tools disabled. pip install Pillow")


# ════════════════════════════════════════════════════
# 1. Tool Definitions (OpenAI/Ollama JSON Schema)
# ════════════════════════════════════════════════════

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "workspace_file_ops",
            "description": "File operations in workspace. Actions: read, write, create, delete, list, list_tree, read_lines, search_replace, grep. For write/create provide 'content'. For search_replace provide 'old_text' and 'new_text'. For grep provide 'pattern'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["read", "write", "create", "delete", "list", "list_tree", "read_lines", "search_replace", "grep"],
                        "description": "File operation to perform"
                    },
                    "path": {"type": "string", "description": "Relative path from workspace root"},
                    "content": {"type": "string", "description": "File content for write/create"},
                    "old_text": {"type": "string", "description": "Text to find for search_replace"},
                    "new_text": {"type": "string", "description": "Replacement text for search_replace"},
                    "pattern": {"type": "string", "description": "Regex pattern for grep"},
                    "start_line": {"type": "integer", "description": "Start line for read_lines (1-indexed)"},
                    "end_line": {"type": "integer", "description": "End line for read_lines (inclusive)"},
                    "include": {"type": "string", "description": "File glob for grep (e.g. '*.py')"},
                    "max_results": {"type": "integer", "default": 30, "description": "Max grep results"}
                },
                "required": ["action", "path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_shell_command",
            "description": "Execute a shell command in the workspace. Returns stdout, stderr, exit_code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Command to run"},
                    "timeout": {"type": "integer", "default": 120},
                    "cwd": {"type": "string", "description": "Working dir relative to workspace"}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_checkpoint",
            "description": "Create a git commit in workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Commit message"},
                    "add_all": {"type": "boolean", "default": True}
                },
                "required": ["message"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_project_structure",
            "description": "Scan workspace directory tree with file sizes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "default": "."},
                    "max_depth": {"type": "integer", "default": 4},
                    "ignore": {"type": "array", "items": {"type": "string"}, "default": ["node_modules", ".git", "__pycache__", "dist", "build", ".next", "venv"]}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "capture_screenshot",
            "description": "Capture a screenshot of the entire screen or a specific window. Returns base64 image.",
            "parameters": {
                "type": "object",
                "properties": {
                    "region": {
                        "type": "string",
                        "enum": ["fullscreen", "active_window", "region"],
                        "default": "fullscreen",
                        "description": "What to capture"
                    },
                    "save_path": {
                        "type": "string",
                        "description": "Optional: save screenshot to workspace path (e.g. 'screenshots/shot1.png')"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_image",
            "description": "Read an image file from disk and return it as base64 for vision analysis. Supports png, jpg, jpeg, gif, webp, bmp.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to image (relative to workspace or absolute)"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": "Search across the codebase for a pattern. Returns matching files and lines with context.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regex pattern to search for"},
                    "include": {"type": "string", "description": "File glob filter (e.g. '*.py', '*.ts,*.tsx')"},
                    "path": {"type": "string", "default": ".", "description": "Relative path to search in"},
                    "max_results": {"type": "integer", "default": 50},
                    "context_lines": {"type": "integer", "default": 2, "description": "Lines of context around matches"}
                },
                "required": ["pattern"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "done",
            "description": "Signal task completion.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Summary of what was built"}
                },
                "required": ["summary"]
            }
        }
    }
]


# ════════════════════════════════════════════════════
# 2. Tool Implementations
# ════════════════════════════════════════════════════

def _safe_path(rel: str) -> pathlib.Path | None:
    if not rel:
        return None
    if rel.startswith("/") or rel.startswith("\\"):
        p = pathlib.Path(rel)
        if p.exists():
            return p
        return None
    if ".." in rel:
        return None
    resolved = (WORKSPACE_DIR / rel).resolve()
    if not str(resolved).startswith(str(WORKSPACE_DIR.resolve())):
        return None
    return resolved


def _backup_file(target: pathlib.Path):
    if target.exists() and CFG["tools"].get("backup_on_write", True):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        try:
            rel = target.relative_to(WORKSPACE_DIR)
        except ValueError:
            rel = pathlib.Path(target.name)
        bak = BACKUP_DIR / f"{ts}_{rel.parent}" / f"{target.name}"
        bak.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, bak)


def _build_tree(path: pathlib.Path, max_depth: int = 4, ignore: set = None) -> list:
    if ignore is None:
        ignore = {"node_modules", ".git", "__pycache__", "dist", "build", ".next", "venv", ".venv"}
    result = []
    try:
        for e in sorted(path.iterdir()):
            if e.name in ignore:
                continue
            if e.is_dir():
                children = _build_tree(e, max_depth - 1, ignore) if max_depth > 0 else []
                result.append({"name": e.name, "type": "dir", "children": children})
            else:
                size = e.stat().st_size
                result.append({"name": e.name, "type": "file", "size": size})
    except PermissionError:
        pass
    return result


async def tool_workspace_file_ops(action: str, path: str, content: str = "",
                                   old_text: str = "", new_text: str = "",
                                   pattern: str = "", start_line: int = 0,
                                   end_line: int = 0, include: str = "",
                                   max_results: int = 30) -> dict:
    target = _safe_path(path)
    if target is None and action not in ("list", "list_tree", "grep"):
        return {"error": f"Invalid path: {path}", "success": False}

    try:
        if action == "read":
            if not target.exists():
                return {"error": f"File not found: {path}", "success": False}
            data = target.read_text(encoding="utf-8", errors="replace")
            lines = data.count("\n") + 1
            return {"content": data, "size": len(data), "lines": lines, "success": True}

        elif action == "read_lines":
            if not target.exists():
                return {"error": f"File not found: {path}", "success": False}
            all_lines = target.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
            s = max(0, (start_line or 1) - 1)
            e = min(len(all_lines), end_line or len(all_lines))
            selected = "".join(all_lines[s:e])
            return {"content": selected, "total_lines": len(all_lines), "from": s + 1, "to": e, "success": True}

        elif action == "write":
            target.parent.mkdir(parents=True, exist_ok=True)
            _backup_file(target)
            target.write_text(content, encoding="utf-8")
            lines = content.count("\n") + 1
            return {"success": True, "path": str(target.relative_to(WORKSPACE_DIR)), "size": len(content), "lines": lines}

        elif action == "create":
            if target.exists():
                return {"error": f"Already exists: {path}. Use 'write' to overwrite.", "success": False}
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return {"success": True, "path": str(target.relative_to(WORKSPACE_DIR)), "size": len(content)}

        elif action == "delete":
            if not target.exists():
                return {"error": f"Not found: {path}", "success": False}
            if target.is_dir():
                shutil.rmtree(target)
                return {"success": True, "deleted": "directory"}
            _backup_file(target)
            target.unlink()
            return {"success": True, "deleted": "file"}

        elif action == "list":
            if not target.exists():
                return {"error": f"Not found: {path}", "success": False}
            if target.is_file():
                return {"files": [{"name": target.name, "type": "file", "size": target.stat().st_size}], "success": True}
            entries = []
            for e in sorted(target.iterdir()):
                kind = "dir" if e.is_dir() else "file"
                size = e.stat().st_size if e.is_file() else 0
                entries.append({"name": e.name, "type": kind, "size": size})
            return {"files": entries, "count": len(entries), "success": True}

        elif action == "list_tree":
            scan = target if target and target.exists() else WORKSPACE_DIR
            tree = _build_tree(scan, max_depth=4)
            return {"tree": tree, "success": True}

        elif action == "search_replace":
            if not target.exists():
                return {"error": f"Not found: {path}", "success": False}
            if not old_text:
                return {"error": "old_text is required", "success": False}
            data = target.read_text(encoding="utf-8", errors="replace")
            count = data.count(old_text)
            if count == 0:
                return {"error": f"old_text not found in {path}", "success": False, "occurrences": 0}
            _backup_file(target)
            new_data = data.replace(old_text, new_text, 1)
            target.write_text(new_data, encoding="utf-8")
            return {"success": True, "replaced": 1, "remaining_occurrences": new_data.count(old_text), "path": path}

        elif action == "grep":
            search_dir = WORKSPACE_DIR
            if target and target.exists() and target.is_dir():
                search_dir = target
            if not pattern:
                return {"error": "pattern is required for grep", "success": False}

            regex = re.compile(pattern, re.IGNORECASE)
            glob_filter = include or "*"
            results = []
            total_matches = 0

            for fpath in search_dir.rglob(glob_filter):
                if not fpath.is_file():
                    continue
                if any(skip in fpath.parts for skip in ["node_modules", ".git", "__pycache__", "dist", "build", "venv"]):
                    continue
                try:
                    lines = fpath.read_text(encoding="utf-8", errors="replace").splitlines()
                except Exception:
                    continue
                for i, line in enumerate(lines):
                    if regex.search(line):
                        total_matches += 1
                        if total_matches > max_results:
                            break
                        try:
                            rel = fpath.relative_to(WORKSPACE_DIR)
                        except ValueError:
                            rel = fpath
                        results.append({
                            "file": str(rel),
                            "line": i + 1,
                            "text": line.strip()[:200],
                        })
                if total_matches > max_results:
                    break

            return {"matches": results, "total": total_matches, "truncated": total_matches > max_results, "success": True}

        return {"error": f"Unknown action: {action}", "success": False}

    except Exception as e:
        return {"error": str(e), "success": False}


async def tool_execute_shell_command(command: str, timeout: int = 120, cwd: str = ".") -> dict:
    work_dir = _safe_path(cwd) or WORKSPACE_DIR
    if not work_dir.exists():
        work_dir = WORKSPACE_DIR

    timeout = min(timeout, SHELL_TIMEOUT)
    bus.emit("tool.shell", {"command": command})

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=str(work_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "GIT_TERMINAL_PROMPT": "0"},
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return {"error": f"Timed out after {timeout}s", "exit_code": -1, "success": False}

        stdout_str = stdout.decode("utf-8", errors="replace").strip()
        stderr_str = stderr.decode("utf-8", errors="replace").strip()

        return {
            "stdout": stdout_str[-4000:],
            "stderr": stderr_str[-2000:],
            "exit_code": proc.returncode,
            "success": proc.returncode == 0,
        }
    except Exception as e:
        return {"error": str(e), "exit_code": -1, "success": False}


async def tool_git_checkpoint(message: str, add_all: bool = True) -> dict:
    bus.emit("tool.git", {"message": message})

    async def _run(cmd):
        proc = await asyncio.create_subprocess_shell(
            cmd, cwd=str(WORKSPACE_DIR),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
        out, err = await asyncio.wait_for(proc.communicate(), timeout=30)
        return proc.returncode, out.decode("utf-8", errors="replace"), err.decode("utf-8", errors="replace")

    try:
        code, _, err = await _run("git init")
        if code != 0 and "already exists" not in err:
            return {"error": f"git init failed: {err}", "success": False}

        if add_all:
            code, _, err = await _run("git add -A")
            if code != 0:
                return {"error": f"git add failed: {err}", "success": False}

        code, out, err = await _run(f'git commit -m "{message}" --allow-empty')
        if code != 0:
            return {"error": f"git commit failed: {err}", "success": False}

        short_hash = out.strip().split("\n")[0] if out.strip() else "ok"
        return {"success": True, "message": message, "commit": short_hash}
    except Exception as e:
        return {"error": str(e), "success": False}


async def tool_analyze_project_structure(path: str = ".", max_depth: int = 4, ignore: list = None) -> dict:
    scan_path = _safe_path(path) or WORKSPACE_DIR
    if not scan_path.exists():
        return {"error": f"Path not found: {path}", "success": False}

    ignore_set = set(ignore) if ignore else {"node_modules", ".git", "__pycache__", "dist", "build", ".next", "venv"}
    tree = _build_tree(scan_path, max_depth=max_depth, ignore=ignore_set)

    def _count(node_list):
        files, dirs, total_size = 0, 0, 0
        for n in node_list:
            if n["type"] == "dir":
                dirs += 1
                f, d, s = _count(n.get("children", []))
                files += f
                dirs += d
                total_size += s
            else:
                files += 1
                total_size += n.get("size", 0)
        return files, dirs, total_size

    total_files, total_dirs, total_size = _count(tree)
    return {
        "success": True,
        "tree": tree,
        "stats": {"total_files": total_files, "total_dirs": total_dirs, "total_size": total_size},
    }


async def tool_capture_screenshot(region: str = "fullscreen", save_path: str = "") -> dict:
    if not PILLOW_OK:
        return {"error": "Pillow not installed. Run: pip install Pillow", "success": False}

    try:
        if region == "fullscreen":
            img = ImageGrab.grab()
        elif region == "active_window":
            img = ImageGrab.grab()
        else:
            img = ImageGrab.grab()

        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")

        if save_path:
            save_target = _safe_path(save_path)
            if save_target:
                save_target.parent.mkdir(parents=True, exist_ok=True)
                img.save(str(save_target), format="PNG")
                return {"success": True, "base64": b64[:100] + "...(truncated)", "saved_to": save_path, "width": img.width, "height": img.height, "full_base64": b64}

        return {"success": True, "base64": b64, "width": img.width, "height": img.height}
    except Exception as e:
        return {"error": str(e), "success": False}


async def tool_read_image(path: str) -> dict:
    try:
        img_path = pathlib.Path(path)
        if not img_path.is_absolute():
            img_path = WORKSPACE_DIR / path

        if not img_path.exists():
            return {"error": f"Image not found: {path}", "success": False}

        suffix = img_path.suffix.lower()
        if suffix not in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"):
            return {"error": f"Unsupported format: {suffix}", "success": False}

        with open(img_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")

        try:
            from PIL import Image
            img = Image.open(str(img_path))
            w, h = img.size
        except Exception:
            w, h = 0, 0

        return {"success": True, "base64": b64, "path": str(img_path), "width": w, "height": h, "format": suffix}
    except Exception as e:
        return {"error": str(e), "success": False}


async def tool_search_code(pattern: str, include: str = "", path: str = ".",
                           max_results: int = 50, context_lines: int = 2) -> dict:
    try:
        search_dir = WORKSPACE_DIR
        target = _safe_path(path)
        if target and target.exists() and target.is_dir():
            search_dir = target

        regex = re.compile(pattern, re.IGNORECASE)

        glob_patterns = [include] if include and "*" in include else [include] if include else ["*"]
        results = []

        for gp in glob_patterns:
            for fpath in search_dir.rglob(gp):
                if not fpath.is_file():
                    continue
                if any(skip in fpath.parts for skip in ["node_modules", ".git", "__pycache__", "dist", "build", "venv", ".next"]):
                    continue
                try:
                    lines = fpath.read_text(encoding="utf-8", errors="replace").splitlines()
                except Exception:
                    continue

                for i, line in enumerate(lines):
                    if regex.search(line):
                        try:
                            rel = fpath.relative_to(WORKSPACE_DIR)
                        except ValueError:
                            rel = fpath
                        ctx_start = max(0, i - context_lines)
                        ctx_end = min(len(lines), i + context_lines + 1)
                        context = []
                        for j in range(ctx_start, ctx_end):
                            prefix = ">>>" if j == i else "   "
                            context.append(f"{prefix} {j+1:4d} | {lines[j].rstrip()}")
                        results.append({
                            "file": str(rel),
                            "line": i + 1,
                            "match": line.strip()[:200],
                            "context": "\n".join(context),
                        })
                        if len(results) >= max_results:
                            break
                if len(results) >= max_results:
                    break

        return {"results": results, "total": len(results), "truncated": len(results) >= max_results, "success": True}
    except Exception as e:
        return {"error": str(e), "success": False}


# ════════════════════════════════════════════════════
# 3. Tool Dispatcher
# ════════════════════════════════════════════════════

TOOL_MAP = {
    "workspace_file_ops": tool_workspace_file_ops,
    "execute_shell_command": tool_execute_shell_command,
    "git_checkpoint": tool_git_checkpoint,
    "analyze_project_structure": tool_analyze_project_structure,
    "capture_screenshot": tool_capture_screenshot,
    "read_image": tool_read_image,
    "search_code": tool_search_code,
}


async def call_tool(name: str, args: dict) -> dict:
    fn = TOOL_MAP.get(name)
    if not fn:
        return {"error": f"Unknown tool: {name}", "success": False}

    bus.emit("tool.call", {"tool": name, "args": json.dumps(args, ensure_ascii=False)[:300]})

    result = await fn(**args)

    bus.emit("tool.result", {
        "tool": name,
        "success": result.get("success", False),
        "summary": json.dumps(result, ensure_ascii=False)[:200],
    })
    return result


# ════════════════════════════════════════════════════
# 4. Ollama Client
# ════════════════════════════════════════════════════

class Ollama:
    def __init__(self, host=OLLAMA_HOST):
        self.host = host
        self._available = None

    async def _get(self, path, timeout_s=5):
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{self.host}{path}", timeout=aiohttp.ClientTimeout(total=timeout_s)) as r:
                return r.status, await r.json()

    async def _post(self, path, payload, timeout_s=120):
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{self.host}{path}", json=payload,
                timeout=aiohttp.ClientTimeout(total=timeout_s),
            ) as r:
                return r.status, await r.json()

    async def _post_stream(self, path, payload, timeout_s=120):
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{self.host}{path}", json=payload,
                timeout=aiohttp.ClientTimeout(total=timeout_s),
            ) as r:
                async for raw in r.content:
                    line = raw.decode().strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue

    async def is_available(self):
        if self._available is not None:
            return self._available
        try:
            status, _ = await self._get("/api/tags", timeout_s=3)
            self._available = status == 200
        except Exception:
            self._available = False
        return self._available

    async def list_models(self):
        try:
            _, data = await self._get("/api/tags", timeout_s=5)
            return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    def model_installed(self, model_name, installed_list):
        for m in installed_list:
            if m == model_name or m.startswith(model_name.split(":")[0]):
                return True
        return False

    async def generate(self, prompt, model, system="", images=None):
        payload = {"model": model, "prompt": prompt, "stream": False}
        if system:
            payload["system"] = system
        if images:
            payload["images"] = images
        try:
            _, data = await self._post("/api/generate", payload, timeout_s=300)
            return data.get("response", "")
        except Exception as e:
            print(f"[Ollama] generate({model}) error: {e}")
            return None

    async def stream(self, prompt, model, system="", images=None):
        payload = {"model": model, "prompt": prompt, "stream": True}
        if system:
            payload["system"] = system
        if images:
            payload["images"] = images
        try:
            async for chunk in self._post_stream("/api/generate", payload, timeout_s=300):
                text = chunk.get("response", "")
                if text:
                    yield text
                if chunk.get("done"):
                    return
        except Exception as e:
            yield f"\n\n[Ollama error: {e}]"

    async def chat_stream(self, messages, model, tools=None):
        payload = {"model": model, "messages": messages, "stream": True}
        if tools:
            payload["tools"] = tools
        try:
            async for chunk in self._post_stream("/api/chat", payload, timeout_s=300):
                yield chunk
        except Exception as e:
            yield {"error": str(e)}

    async def vision_analyze(self, prompt: str, image_b64: str, model: str = None) -> str:
        use_model = model or MODEL_VISION
        installed = await self.list_models()
        if not self.model_installed(use_model, installed):
            use_model = MODEL_CODING if self.model_installed(MODEL_CODING, installed) else MODEL_REASONING
        return await self.generate(prompt, model=use_model, images=[image_b64])


ollama = Ollama()


# ════════════════════════════════════════════════════
# 5. Smart Router
# ════════════════════════════════════════════════════

CODE_KEYWORDS = re.compile(
    r"(?:код|кодируй|напиши код|программ|скрипт|функци"
    r"|html|css|javascript|typescript|react|vue|angular|svelte"
    r"|python|java|c\+\+|rust|go|sql"
    r"|сайт|лендинг|интерфейс|страниц|верстк|фронтенд|бэкенд"
    r"|компонент|массив|объект|класс|метод|api|endpoint"
    r"|debug|ошибк|баг|fix|исправ"
    r"|deploy|билд|сборк|настроен"
    r"|bot|скрипт|автоматиз"
    r"|создай|создать|собери|собрать|проект|систему|приложен"
    r")", re.IGNORECASE)

VISION_KEYWORDS = re.compile(
    r"(?:скриншот|screenshot|покажи|видео|изображен|картинк|фото|анализ.*экран|что.*на.*экране|what.*on.*screen)",
    re.IGNORECASE)


def route_request(prompt):
    if VISION_KEYWORDS.search(prompt):
        return MODEL_VISION, "vision"
    if CODE_KEYWORDS.search(prompt):
        return MODEL_CODING, "coding"
    return MODEL_REASONING, "reasoning"


SYSTEM_REASONING = (
    "Ты — Hermes Studio, локальный ИИ-ассистент. "
    "Отвечай подробно, структурно, на русском языке. "
    "Будь полезным, умным и точным."
)

SYSTEM_CODING = (
    "Ты — Hermes Studio, локальный ИИ-ассистент для кода. "
    "Пиши чистый, рабочий, готовый к запуску код. "
    "Отвечай на русском. "
    "Код обёртывай в ```html, ```python, ```typescript и т.д. "
    "Всегда объясняй что делаешь."
)

SYSTEM_VISION = (
    "Ты — Hermes Studio, локальный ИИ с поддержкой зрения. "
    "Анализируй изображения подробно и точно. "
    "Описывай что видишь на скриншоте, интерфейсе, диаграмме. "
    "Отвечай на русском."
)

SYSTEM_AGENT = (
    f"{AGENT_SYSTEM}\n\n"
    "You have these tools:\n"
    "- workspace_file_ops: read/write/create/delete/list/grep/search_replace/read_lines files\n"
    "- execute_shell_command: run shell commands (npm install, pytest, tsc, etc.)\n"
    "- git_checkpoint: create git commits\n"
    "- analyze_project_structure: scan directory tree\n"
    "- capture_screenshot: take screenshots for visual analysis\n"
    "- read_image: read images from disk for vision\n"
    "- search_code: search across codebase with regex\n"
    "- done: signal task completion\n\n"
    f"Workspace: {WORKSPACE_DIR}\n"
    f"Current date: {datetime.now().strftime('%Y-%m-%d')}\n\n"
    "IMPORTANT: Use tools to build the project step by step. "
    "Write each file, run builds, fix errors, commit progress. "
    "Use capture_screenshot to verify visual output. "
    "When finished, call the 'done' tool with a summary."
)


# ════════════════════════════════════════════════════
# 6. Agent Loop (Tool Calling)
# ════════════════════════════════════════════════════

class AgentLoop:
    def __init__(self, task: str, model: str = None):
        self.task = task
        self.model = model or MODEL_AGENT
        self.messages = [
            {"role": "system", "content": SYSTEM_AGENT},
            {"role": "user", "content": task},
        ]
        self.steps = []
        self.done = False
        self.result_summary = ""

    async def run(self, on_step=None):
        bus.emit("agent.start", {"task": self.task[:200], "model": self.model})

        for iteration in range(MAX_ITERATIONS):
            if self.done:
                break

            bus.emit("agent.iteration", {"step": iteration + 1, "max": MAX_ITERATIONS})

            response_text = ""
            tool_calls = []

            async for chunk in ollama.chat_stream(self.messages, self.model, tools=TOOLS_SCHEMA):
                if "error" in chunk:
                    bus.emit("agent.error", {"error": chunk["error"]})
                    break

                if "message" in chunk:
                    msg = chunk["message"]
                    if msg.get("content"):
                        response_text += msg["content"]
                    if msg.get("tool_calls"):
                        for tc in msg["tool_calls"]:
                            fn = tc.get("function", {})
                            tool_calls.append({
                                "id": tc.get("id", f"call_{uuid.uuid4().hex[:8]}"),
                                "name": fn.get("name", ""),
                                "arguments": fn.get("arguments", {}),
                            })

            if response_text:
                bus.emit("agent.text", {"text": response_text[:500]})
                self.messages.append({"role": "assistant", "content": response_text})

            if not tool_calls:
                if self.done:
                    break
                if response_text.strip():
                    self.messages.append({
                        "role": "user",
                        "content": "Continue. Use tools to build the project. If you're done, call the 'done' tool."
                    })
                    continue
                else:
                    break

            for tc in tool_calls:
                name = tc["name"]
                args = tc["arguments"]

                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}

                bus.emit("agent.tool_call", {"tool": name, "args": json.dumps(args, ensure_ascii=False)[:300]})

                result = await call_tool(name, args)

                step_record = {
                    "step": iteration + 1,
                    "tool": name,
                    "args": args,
                    "result": result,
                    "ts": time.time(),
                }
                self.steps.append(step_record)

                if on_step:
                    await on_step(step_record)

                if name == "done":
                    self.done = True
                    self.result_summary = args.get("summary", "")
                    break

                result_str = json.dumps(result, ensure_ascii=False)[:2000]
                self.messages.append({
                    "role": "tool",
                    "content": f"Tool '{name}' result:\n{result_str}"
                })

        bus.emit("agent.finish", {
            "steps": len(self.steps),
            "done": self.done,
            "summary": self.result_summary,
        })

        return {
            "done": self.done,
            "steps": len(self.steps),
            "summary": self.result_summary,
            "history": self.steps,
        }


# ════════════════════════════════════════════════════
# 7. Event Bus (SSE)
# ════════════════════════════════════════════════════

class EventBus:
    def __init__(self):
        self.subscribers = []

    def subscribe(self):
        q = asyncio.Queue()
        self.subscribers.append(q)
        return q

    def unsubscribe(self, q):
        if q in self.subscribers:
            self.subscribers.remove(q)

    def emit(self, event, payload=None):
        msg = json.dumps({"event": event, "payload": payload or {}, "ts": time.time()}, ensure_ascii=False)
        for q in self.subscribers[:]:
            try:
                q.put_nowait(msg)
            except Exception:
                self.subscribers.remove(q)

    async def stream(self, q):
        try:
            while True:
                msg = await q.get()
                yield f"data: {msg}\n\n"
        except asyncio.CancelledError:
            pass


bus = EventBus()


# ════════════════════════════════════════════════════
# 8. Ollama Auto-Start
# ════════════════════════════════════════════════════

async def ensure_ollama():
    if await ollama.is_available():
        return True
    if not CFG["ollama"].get("auto_start", True):
        return False

    print("[Hermes] Ollama not running, starting...")
    if not OLLAMA_EXE.exists():
        print(f"[Hermes] Ollama not found at {OLLAMA_EXE}")
        return False

    try:
        os.environ["OLLAMA_HOST"] = "127.0.0.1:11434"
        os.environ["OLLAMA_MODELS"] = OLLAMA_MODELS
        subprocess.Popen(
            [str(OLLAMA_EXE), "serve"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as e:
        print(f"[Hermes] Failed to start Ollama: {e}")
        return False

    for _ in range(20):
        await asyncio.sleep(0.5)
        if await ollama.is_available():
            print("[Hermes] Ollama started.")
            return True

    print("[Hermes] Ollama did not start in time.")
    return False


# ════════════════════════════════════════════════════
# 9. HTTP Handlers
# ════════════════════════════════════════════════════

async def index_handler(request):
    html_path = FRONTEND_DIR / "index.html"
    if html_path.exists():
        return web.FileResponse(html_path)
    return web.Response(text="Frontend not found", status=404)


async def health_handler(request):
    ollama_ok = await ollama.is_available()
    return web.json_response({
        "status": "ok",
        "version": "3.1-vision",
        "port": PORT,
        "ollama": {"available": ollama_ok},
        "workspace": str(WORKSPACE_DIR),
        "pillow": PILLOW_OK,
    })


async def models_handler(request):
    ollama_ok = await ollama.is_available()
    models = await ollama.list_models() if ollama_ok else []
    return web.json_response({
        "ollama": {"available": ollama_ok, "models": models},
        "reasoning": {"model": MODEL_REASONING, "installed": ollama.model_installed(MODEL_REASONING, models)},
        "coding": {"model": MODEL_CODING, "installed": ollama.model_installed(MODEL_CODING, models)},
        "agent": {"model": MODEL_AGENT, "installed": ollama.model_installed(MODEL_AGENT, models)},
        "vision": {"model": MODEL_VISION, "installed": ollama.model_installed(MODEL_VISION, models)},
    })


async def tools_handler(request):
    return web.json_response({"tools": TOOLS_SCHEMA})


async def workspace_handler(request):
    tree = _build_tree(WORKSPACE_DIR, max_depth=5)
    return web.json_response({"workspace": str(WORKSPACE_DIR), "tree": tree})


async def chat_handler(request):
    body = await request.json()
    prompt = (body.get("prompt") or "").strip()
    history = body.get("history", [])
    images = body.get("images")
    use_stream = request.query.get("stream") == "1"

    if not prompt and not images:
        return web.json_response({"error": "empty prompt"}, status=400)

    model, route_type = route_request(prompt)
    system = SYSTEM_CODING if route_type == "coding" else SYSTEM_VISION if route_type == "vision" else SYSTEM_REASONING

    if history:
        recent = history[-6:]
        lines = []
        for m in recent:
            role = "User" if m.get("role") == "user" else "Assistant"
            lines.append(f"{role}: {m.get('content', '')}")
        system += "\n\nRecent context:\n" + "\n".join(lines)

    bus.emit("chat.request", {"prompt": prompt[:200], "model": model, "route": route_type})

    if not await ensure_ollama():
        msg = "Ollama not running. Install: https://ollama.com | Then: ollama serve"
        if use_stream:
            return await _stream_text(request, msg)
        return web.json_response({"text": msg, "model": "unavailable"})

    installed = await ollama.list_models()
    if not ollama.model_installed(model, installed):
        fallback = MODEL_CODING if ollama.model_installed(MODEL_CODING, installed) else MODEL_REASONING
        if not ollama.model_installed(fallback, installed):
            msg = f"Model {model} not installed. Run: python setup_models.py"
            if use_stream:
                return await _stream_text(request, msg)
            return web.json_response({"text": msg, "model": "missing"})
        model = fallback

    if use_stream:
        bus.emit("chat.stream_start", {"model": model, "route": route_type})
        resp = web.StreamResponse(
            headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )
        await resp.prepare(request)

        async def send_sse(data):
            await resp.write(f"data: {json.dumps(data, ensure_ascii=False)}\n\n".encode())

        try:
            async for text in ollama.stream(prompt, model=model, system=system, images=images):
                await send_sse({"text": text, "done": False, "model": model, "route": route_type})
            await send_sse({"text": "", "done": True, "model": model, "route": route_type})
            bus.emit("chat.done", {"model": model, "route": route_type})
        except Exception as e:
            await send_sse({"text": f"\n\n[Error: {e}]", "done": True})
        return resp

    bus.emit("chat.generate", {"model": model, "route": route_type})
    text = await ollama.generate(prompt, model=model, system=system, images=images)
    if text:
        bus.emit("chat.done", {"model": model, "route": route_type})
        return web.json_response({"text": text, "model": model, "route": route_type})

    return web.json_response({"text": "Failed to get response. Try again.", "model": "error"})


async def agent_handler(request):
    body = await request.json()
    task = (body.get("task") or "").strip()
    model = body.get("model")

    if not task:
        return web.json_response({"error": "empty task"}, status=400)

    if not await ensure_ollama():
        return web.json_response({"error": "Ollama not running"}, status=503)

    installed = await ollama.list_models()
    use_model = model or MODEL_AGENT
    if not ollama.model_installed(use_model, installed):
        use_model = MODEL_CODING if ollama.model_installed(MODEL_CODING, installed) else MODEL_REASONING
        if not ollama.model_installed(use_model, installed):
            return web.json_response({"error": "No suitable model installed"}, status=503)

    agent = AgentLoop(task=task, model=use_model)

    resp = web.StreamResponse(
        headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
    await resp.prepare(request)

    async def send_sse(data):
        await resp.write(f"data: {json.dumps(data, ensure_ascii=False)}\n\n".encode())

    async def on_step(step):
        await send_sse({
            "type": "step",
            "step": step["step"],
            "tool": step["tool"],
            "args": step["args"],
            "result_summary": json.dumps(step["result"], ensure_ascii=False)[:300],
        })

    try:
        result = await agent.run(on_step=on_step)
        await send_sse({"type": "done", "result": result})
    except Exception as e:
        await send_sse({"type": "error", "error": str(e)})

    return resp


async def analyze_image_handler(request):
    body = await request.json()
    image_b64 = body.get("image")
    prompt = body.get("prompt", "Describe this image in detail.")
    save_path = body.get("save_path")

    if not image_b64:
        return web.json_response({"error": "No image provided"}, status=400)

    if save_path:
        save_target = WORKSPACE_DIR / save_path
        save_target.parent.mkdir(parents=True, exist_ok=True)
        import base64 as b64mod
        save_target.write_bytes(b64mod.b64decode(image_b64))

    result = await ollama.vision_analyze(prompt, image_b64)
    if result:
        return web.json_response({"description": result, "model": MODEL_VISION})

    return web.json_response({"error": "Vision analysis failed"}, status=500)


async def _stream_text(request, text):
    resp = web.StreamResponse(
        headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
    await resp.prepare(request)
    await resp.write(f"data: {json.dumps({'text': text, 'done': False}, ensure_ascii=False)}\n\n".encode())
    await resp.write(f"data: {json.dumps({'text': '', 'done': True}, ensure_ascii=False)}\n\n".encode())
    return resp


async def upload_handler(request):
    reader = await request.multipart()
    field = await reader.next()
    if not field or field.name != "file":
        return web.json_response({"error": "no file field"}, status=400)

    filename = field.filename or "upload.bin"
    filename = "".join(c for c in filename if c.isalnum() or c in "._- ")[:60].strip()
    if not filename:
        filename = "upload.bin"

    dest = UPLOAD_DIR / f"{uuid.uuid4().hex[:8]}_{filename}"
    max_bytes = CFG["limits"]["max_upload_mb"] * 1024 * 1024
    size = 0

    with open(dest, "wb") as f:
        while True:
            chunk = await field.read_chunk(8192)
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                return web.json_response({"error": f"Too large (max {CFG['limits']['max_upload_mb']}MB)"}, status=413)
            f.write(chunk)

    bus.emit("upload.done", {"filename": filename, "size": size})
    return web.json_response({"path": str(dest).replace("\\", "/"), "size": size, "filename": filename})


async def events_handler(request):
    q = bus.subscribe()
    resp = web.StreamResponse(
        headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}
    )
    await resp.prepare(request)
    try:
        async for chunk in bus.stream(q):
            await resp.write(chunk.encode())
    except asyncio.CancelledError:
        pass
    finally:
        bus.unsubscribe(q)
    return resp


# ════════════════════════════════════════════════════
# 10. App Setup
# ════════════════════════════════════════════════════

app = web.Application()

cors = aiohttp_cors.setup(
    app,
    defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
            allow_methods="*",
        )
    },
)

routes = [
    web.get("/", index_handler),
    web.get("/api/health", health_handler),
    web.get("/api/models", models_handler),
    web.get("/api/tools", tools_handler),
    web.get("/api/workspace", workspace_handler),
    web.post("/api/chat", chat_handler),
    web.post("/api/agent", agent_handler),
    web.post("/api/analyze_image", analyze_image_handler),
    web.post("/api/upload", upload_handler),
    web.get("/api/events", events_handler),
]
for route in routes:
    cors.add(app.router.add_route(route.method, route.path, route.handler))

if UPLOAD_DIR.exists():
    app.router.add_static("/uploads", str(UPLOAD_DIR), show_index=False)


async def on_startup(app):
    bus.emit("system.started", {"time": time.time(), "version": "3.1-vision"})

    ollama_ok = await ensure_ollama()
    models = await ollama.list_models() if ollama_ok else []
    reasoning_ok = ollama.model_installed(MODEL_REASONING, models)
    coding_ok = ollama.model_installed(MODEL_CODING, models)
    agent_ok = ollama.model_installed(MODEL_AGENT, models)
    vision_ok = ollama.model_installed(MODEL_VISION, models)

    bus.emit("models.status", {
        "ollama": ollama_ok, "reasoning": reasoning_ok,
        "coding": coding_ok, "agent": agent_ok, "vision": vision_ok,
    })

    print()
    print(f"  Hermes Studio v3.1 — Agentic Tool Suite + Vision")
    print(f"  http://127.0.0.1:{PORT}")
    print(f"  Ollama:      {'ON' if ollama_ok else 'OFF'}")
    print(f"  Reasoning:   {MODEL_REASONING} {'ready' if reasoning_ok else 'NOT INSTALLED'}")
    print(f"  Coding:      {MODEL_CODING} {'ready' if coding_ok else 'NOT INSTALLED'}")
    print(f"  Agent:       {MODEL_AGENT} {'ready' if agent_ok else 'NOT INSTALLED'}")
    print(f"  Vision:      {MODEL_VISION} {'ready' if vision_ok else 'NOT INSTALLED'}")
    print(f"  Pillow:      {'YES' if PILLOW_OK else 'NO (pip install Pillow)'}")
    print(f"  Workspace:   {WORKSPACE_DIR}")
    print(f"  Tools:       {len(TOOLS_SCHEMA)} available")
    if not reasoning_ok or not coding_ok:
        print()
        print("  Run:  python setup_models.py")
    print()


app.on_startup.append(on_startup)


if __name__ == "__main__":
    web.run_app(app, host="127.0.0.1", port=PORT)
