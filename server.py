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


# ════════════════════════════════════════════════════
# 0. SAFETY PROTOCOL — Protection Layer
# ════════════════════════════════════════════════════

# Forbidden shell commands — system destruction / data loss
BLOCKED_SHELL_PATTERNS = [
    r"format\s+[a-zA-Z]:",           # format C:
    r"rd\s+/s\s+[a-zA-Z]:",          # rd /s C:
    r"rmdir\s+/s\s+[a-zA-Z]:",       # rmdir /s C:
    r"del\s+[/\-]+[sfqSQ]+\s+[a-zA-Z]:",  # del /sfq C:
    r"del\s+/[sfqSQ]+\s+\S+",        # del /sfq filename
    r"rm\s+-rf\s+/",                  # rm -rf /
    r"rm\s+-rf\s+~",                  # rm -rf ~
    r"rm\s+-rf\s+\*",                 # rm -rf *
    r"mkfs\.",                         # mkfs.ext4 / mkfs.ntfs
    r"dd\s+if=.*of=/dev/",           # dd writing to disk devices
    r"shutdown",                       # shutdown -s -t 0
    r"reboot",                         # reboot
    r"bcdedit",                        # bcdedit (boot config)
    r"diskpart",                       # diskpart (disk management)
    r"cipher\s+/w",                    # cipher /w (secure delete)
    r"icacls\s+[a-zA-Z]:\\\s*/grant", # icacls (permission changes on system)
    r"takeown\s+/f\s+[a-zA-Z]:",     # takeown on drives
    r"reg\s+delete\s+HKLM",          # deleting system registry
    r"reg\s+delete\s+HKCU\\Software\\Microsoft\\Windows\\CurrentVersion",  # critical registry
    r"net\s+user\s+\S+\s+/delete",   # deleting users
    r"net\s+localgroup\s+Administrators",  # admin group changes
    r"attrib\s+-r\s+-s\s+-h\s+[a-zA-Z]:\\",  # unhide system files
    r"vssadmin\s+delete",             # shadow copy deletion
    r"bcdboot",                        # bcdboot (boot repair = danger)
    r"robocopy.*\/MIR\s+[a-zA-Z]:\\", # mirroring to root
    r"xcopy.*\/Y\s+[a-zA-Z]:\\",     # overwriting root
]

# Forbidden file paths — system files, configs, critical data
BLOCKED_PATHS = [
    r"C:\\Windows",
    r"C:\\Program Files",
    r"C:\\Program Files \(x86\)",
    r"C:\\Users\\[^\\]+\\AppData",
    r"C:\\Users\\[^\\]+\\NTUSER",
    r"C:\\Users\\[^\\]+\\.ssh",
    r"C:\\Users\\[^\\]+\\.env",
    r"C:\\Users\\[^\\]+\\Documents\\.*\.(key|pem|p12|pfx)",
    r"C:\\Users\\[^\\]+\\Desktop\\.*\.(key|pem)",
    r"D:\\.*\\.env",
    r"D:\\.*\\.git\\config",
    r"D:\\.*\\.ssh",
    r"/etc/passwd",
    r"/etc/shadow",
    r"/root",
    r"/boot",
    r"/sys",
    r"/proc",
]

# Dangerous file extensions to never write/delete
DANGEROUS_EXTENSIONS = [
    ".sys", ".dll", ".exe", ".msi", ".com", ".bat", ".cmd",
    ".scr", ".pif", ".reg", ".inf", ".ini", ".drv",
]

BLOCKED_SHELL_RE = [re.compile(p, re.IGNORECASE) for p in BLOCKED_SHELL_PATTERNS]
BLOCKED_PATH_RE = [re.compile(p, re.IGNORECASE) for p in BLOCKED_PATHS]

SAFETY_VIOLATIONS = []


class SafetyViolation(Exception):
    def __init__(self, message, rule=""):
        super().__init__(message)
        self.rule = rule


def _check_safety_shell(command: str):
    """Validate shell command against safety rules."""
    for pattern in BLOCKED_SHELL_RE:
        if pattern.search(command):
            raise SafetyViolation(
                f"BLOCKED: Dangerous command detected: {command[:100]}",
                rule=f"Shell blocked: {pattern.pattern}"
            )


def _check_safety_path(path: str, action: str = "write"):
    """Validate file path against safety rules."""
    check_str = path.replace("\\", "/")

    for pattern in BLOCKED_PATH_RE:
        if pattern.search(check_str):
            raise SafetyViolation(
                f"BLOCKED: Access to protected path denied: {path}",
                rule=f"Path blocked: {pattern.pattern}"
            )

    ext = pathlib.Path(path).suffix.lower()
    if ext in DANGEROUS_EXTENSIONS and action in ("write", "create", "delete"):
        raise SafetyViolation(
            f"BLOCKED: Cannot {action} system file: {path}",
            rule=f"Dangerous extension: {ext}"
        )


def _check_safety_git(message: str):
    """Validate git commit message."""
    lower = message.lower()
    dangerous = ["drop database", "delete all", "rm -rf", "format", "wipe", "destroy"]
    for d in dangerous:
        if d in lower:
            raise SafetyViolation(
                f"BLOCKED: Suspicious git commit message: {message[:100]}",
                rule=f"Suspicious content: {d}"
            )


def _check_safety_python(code: str):
    """Validate Python code for dangerous operations."""
    dangerous = [
        "os.system", "subprocess.call", "shutil.rmtree('/')",
        "__import__('os')", "__import__('subprocess')",
        "eval(", "exec(",
        "open('/etc/", "open('C:\\\\Windows",
        "os.remove", "os.unlink",
    ]
    for d in dangerous:
        if d in code:
            raise SafetyViolation(
                f"BLOCKED: Dangerous Python operation: {d}",
                rule=f"Python safety: {d}"
            )


def safety_check(tool_name: str, args: dict):
    """Master safety check — called before every tool execution."""
    try:
        if tool_name == "execute_shell_command":
            _check_safety_shell(args.get("command", ""))

        elif tool_name == "workspace_file_ops":
            path = args.get("path", "")
            action = args.get("action", "")
            if action in ("delete",):
                _check_safety_path(path, "delete")
            if action in ("write", "create"):
                _check_safety_path(path, "write")
                content = args.get("content", "")
                if content:
                    _check_safety_python(content)

        elif tool_name == "run_python":
            _check_safety_python(args.get("code", ""))

        elif tool_name == "git_checkpoint":
            _check_safety_git(args.get("message", ""))

        elif tool_name == "kill_process":
            name = args.get("name", "").lower()
            protected = ["explorer", "csrss", "lsass", "svchost", "winlogon", "services", "system", "kernel"]
            if name in protected:
                raise SafetyViolation(
                    f"BLOCKED: Cannot kill system process: {name}",
                    rule="Protected process"
                )

        elif tool_name == "scaffold_project":
            name = args.get("name", "")
            if "/" in name or "\\" in name or name.startswith("."):
                raise SafetyViolation(
                    f"BLOCKED: Invalid project name: {name}",
                    rule="Invalid name"
                )

        return True

    except SafetyViolation as e:
        SAFETY_VIOLATIONS.append({
            "tool": tool_name,
            "args": json.dumps(args, ensure_ascii=False)[:200],
            "message": str(e),
            "rule": e.rule,
            "ts": time.time(),
        })
        bus.emit("safety.blocked", {"tool": tool_name, "message": str(e), "rule": e.rule})
        raise

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
    },
    {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": "Execute a Python script directly. Use for calculations, data processing, quick utilities. Returns stdout/stderr.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python code to execute"},
                    "timeout": {"type": "integer", "default": 30}
                },
                "required": ["code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Fetch content from a URL. Use for API calls, downloading docs, checking endpoints.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to fetch"},
                    "method": {"type": "string", "enum": ["GET", "POST"], "default": "GET"},
                    "body": {"type": "string", "description": "POST body (JSON string)"},
                    "timeout": {"type": "integer", "default": 15}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "diff_apply",
            "description": "Apply a unified diff patch to a file. Use for precise edits without rewriting entire files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File to patch"},
                    "diff": {"type": "string", "description": "Unified diff content (--- a/... +++ b/... format)"}
                },
                "required": ["path", "diff"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "kill_process",
            "description": "Kill a running process by name or PID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Process name to kill (e.g. 'node', 'python')"},
                    "pid": {"type": "integer", "description": "Process ID to kill"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "env_info",
            "description": "Get system environment info: OS, Python version, installed packages, disk space.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_templates",
            "description": "List available project templates for quick scaffolding.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scaffold_project",
            "description": "Create a new project from a template. Options: react-ts, python-fastapi, node-express, static-html.",
            "parameters": {
                "type": "object",
                "properties": {
                    "template": {"type": "string", "enum": ["react-ts", "python-fastapi", "node-express", "static-html", "vanilla-js"], "description": "Template to use"},
                    "name": {"type": "string", "description": "Project name / folder name"}
                },
                "required": ["template", "name"]
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


async def tool_run_python(code: str, timeout: int = 30) -> dict:
    timeout = min(timeout, 60)
    bus.emit("tool.python", {"code_len": len(code)})
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-c", code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return {"error": f"Timed out after {timeout}s", "exit_code": -1, "success": False}

        return {
            "stdout": stdout.decode("utf-8", errors="replace").strip()[-3000:],
            "stderr": stderr.decode("utf-8", errors="replace").strip()[-1000:],
            "exit_code": proc.returncode,
            "success": proc.returncode == 0,
        }
    except Exception as e:
        return {"error": str(e), "exit_code": -1, "success": False}


async def tool_fetch_url(url: str, method: str = "GET", body: str = "", timeout: int = 15) -> dict:
    import urllib.request
    import urllib.error
    timeout = min(timeout, 30)
    bus.emit("tool.fetch", {"url": url[:200]})

    try:
        req_body = body.encode("utf-8") if body and method == "POST" else None
        req = urllib.request.Request(url, data=req_body, method=method)
        req.add_header("User-Agent", "Hermes/3.0")

        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read().decode("utf-8", errors="replace")
            return {
                "status": resp.status,
                "headers": dict(resp.headers),
                "body": content[-5000:],
                "body_len": len(content),
                "success": True,
            }
    except urllib.error.HTTPError as e:
        return {"status": e.code, "error": str(e), "success": False}
    except Exception as e:
        return {"error": str(e), "success": False}


async def tool_diff_apply(path: str, diff: str) -> dict:
    target = _safe_path(path)
    if not target or not target.exists():
        return {"error": f"File not found: {path}", "success": False}

    try:
        lines = diff.splitlines()
        original = target.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)

        new_lines = list(original)
        offset = 0

        i = 0
        while i < len(lines):
            line = lines[i]
            if line.startswith("@@"):
                import re as _re
                m = _re.search(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
                if m:
                    old_start = int(m.group(1)) - 1 + offset
                    i += 1
                    remove_count = 0
                    add_lines = []
                    while i < len(lines) and not lines[i].startswith("@@") and not lines[i.startswith("diff")]:
                        if lines[i].startswith("-"):
                            remove_count += 1
                        elif lines[i].startswith("+"):
                            add_lines.append(lines[i][1:])
                        else:
                            remove_count += 1
                            add_lines.append(lines[i][1:] if lines[i].startswith(" ") else lines[i])
                        i += 1
                    new_lines[old_start:old_start + remove_count] = [l + "\n" if not l.endswith("\n") else l for l in add_lines]
                    offset += len(add_lines) - remove_count
                else:
                    i += 1
            else:
                i += 1

        _backup_file(target)
        target.write_text("".join(new_lines), encoding="utf-8")
        return {"success": True, "path": path, "lines_before": len(original), "lines_after": len(new_lines)}
    except Exception as e:
        return {"error": f"Failed to apply diff: {e}", "success": False}


async def tool_kill_process(name: str = "", pid: int = 0) -> dict:
    try:
        if pid:
            os.kill(pid, 9)
            return {"success": True, "killed": f"PID {pid}"}
        if name:
            if sys.platform == "win32":
                proc = await asyncio.create_subprocess_shell(
                    f'taskkill /F /IM "{name}.exe" 2>nul',
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                )
                await proc.communicate()
                return {"success": True, "killed": name}
            else:
                proc = await asyncio.create_subprocess_shell(
                    f"pkill -f {name}",
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                )
                await proc.communicate()
                return {"success": True, "killed": name}
        return {"error": "Provide name or pid", "success": False}
    except Exception as e:
        return {"error": str(e), "success": False}


async def tool_env_info() -> dict:
    import platform
    try:
        disk = shutil.disk_usage("/")
        disk_info = {"total_gb": round(disk.total / (1024**3), 1), "free_gb": round(disk.free / (1024**3), 1)}
    except Exception:
        disk_info = {}

    try:
        py_packages = []
        r = subprocess.run([sys.executable, "-m", "pip", "list", "--format=columns"],
                         capture_output=True, text=True, timeout=10)
        for line in r.stdout.splitlines()[2:22]:
            parts = line.split()
            if len(parts) >= 2:
                py_packages.append(f"{parts[0]}=={parts[1]}")
    except Exception:
        py_packages = []

    return {
        "success": True,
        "os": platform.platform(),
        "python": platform.python_version(),
        "machine": platform.machine(),
        "packages": py_packages,
        "disk": disk_info,
        "cwd": os.getcwd(),
    }


# ════════════════════════════════════════════════════
# Project Templates
# ════════════════════════════════════════════════════

TEMPLATES = {
    "react-ts": {
        "name": "React + TypeScript + Vite",
        "files": {
            "package.json": '{\n  "name": "{{name}}",\n  "private": true,\n  "version": "0.0.0",\n  "type": "module",\n  "scripts": {\n    "dev": "vite",\n    "build": "tsc && vite build",\n    "preview": "vite preview"\n  },\n  "dependencies": {\n    "react": "^18.2.0",\n    "react-dom": "^18.2.0"\n  },\n  "devDependencies": {\n    "@types/react": "^18.2.0",\n    "@types/react-dom": "^18.2.0",\n    "@vitejs/plugin-react": "^4.2.0",\n    "typescript": "^5.3.0",\n    "vite": "^5.0.0"\n  }\n}',
            "tsconfig.json": '{\n  "compilerOptions": {\n    "target": "ES2020",\n    "useDefineForClassFields": true,\n    "lib": ["ES2020", "DOM", "DOM.Iterable"],\n    "module": "ESNext",\n    "skipLibCheck": true,\n    "moduleResolution": "bundler",\n    "allowImportingTsExtensions": true,\n    "resolveJsonModule": true,\n    "isolatedModules": true,\n    "noEmit": true,\n    "jsx": "react-jsx",\n    "strict": true\n  },\n  "include": ["src"]\n}',
            "vite.config.ts": 'import { defineConfig } from "vite"\nimport react from "@vitejs/plugin-react"\n\nexport default defineConfig({\n  plugins: [react()],\n})',
            "index.html": '<!DOCTYPE html>\n<html lang="en">\n  <head>\n    <meta charset="UTF-8" />\n    <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n    <title>{{name}}</title>\n  </head>\n  <body>\n    <div id="root"></div>\n    <script type="module" src="/src/main.tsx"></script>\n  </body>\n</html>',
            "src/main.tsx": 'import React from "react"\nimport ReactDOM from "react-dom/client"\nimport App from "./App"\n\nReactDOM.createRoot(document.getElementById("root")!).render(\n  <React.StrictMode>\n    <App />\n  </React.StrictMode>,\n)',
            "src/App.tsx": 'export default function App() {\n  return (\n    <div style={{ padding: "2rem", fontFamily: "system-ui" }}>\n      <h1>{{name}}</h1>\n      <p>React + TypeScript is ready!</p>\n    </div>\n  )\n}',
            "src/vite-env.d.ts": '/// <reference types="vite" />',
        },
        "install": "npm install",
        "dev": "npm run dev",
    },
    "python-fastapi": {
        "name": "Python FastAPI",
        "files": {
            "requirements.txt": "fastapi==0.108.0\nuvicorn==0.25.0\npydantic==2.5.0",
            "main.py": 'from fastapi import FastAPI\nfrom pydantic import BaseModel\n\napp = FastAPI(title="{{name}}")\n\nclass Item(BaseModel):\n    name: str\n    price: float\n\n@app.get("/")\ndef root():\n    return {"message": "Hello from {{name}}"}\n\n@app.get("/items")\ndef list_items():\n    return [{"name": "Item 1", "price": 9.99}]\n\n@app.post("/items")\ndef create_item(item: Item):\n    return {"created": item.name, "price": item.price}\n\nif __name__ == "__main__":\n    import uvicorn\n    uvicorn.run(app, host="0.0.0.0", port=8000)',
            "README.md": "# {{name}}\n\nFastAPI project.\n\n```bash\npip install -r requirements.txt\npython main.py\n```\n\nOpen: http://localhost:8000/docs",
        },
        "install": "pip install -r requirements.txt",
        "dev": "python main.py",
    },
    "node-express": {
        "name": "Node.js Express",
        "files": {
            "package.json": '{\n  "name": "{{name}}",\n  "version": "1.0.0",\n  "scripts": {\n    "start": "node server.js",\n    "dev": "node --watch server.js"\n  },\n  "dependencies": {\n    "express": "^4.18.0"\n  }\n}',
            "server.js": 'const express = require("express")\nconst app = express()\nconst PORT = process.env.PORT || 3000\n\napp.use(express.json())\n\napp.get("/", (req, res) => {\n  res.json({ message: "Hello from {{name}}" })\n})\n\napp.get("/api/health", (req, res) => {\n  res.json({ status: "ok", uptime: process.uptime() })\n})\n\napp.listen(PORT, () => {\n  console.log(`Server running on http://localhost:${PORT}`)\n})',
            "README.md": "# {{name}}\n\nExpress server.\n\n```bash\nnpm install\nnpm run dev\n```",
        },
        "install": "npm install",
        "dev": "npm run dev",
    },
    "static-html": {
        "name": "Static HTML/CSS/JS",
        "files": {
            "index.html": '<!DOCTYPE html>\n<html lang="en">\n<head>\n  <meta charset="UTF-8" />\n  <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n  <title>{{name}}</title>\n  <link rel="stylesheet" href="style.css" />\n</head>\n<body>\n  <div class="container">\n    <h1>{{name}}</h1>\n    <p>Static site is ready!</p>\n  </div>\n  <script src="script.js"></script>\n</body>\n</html>',
            "style.css": '* { box-sizing: border-box; margin: 0; padding: 0; }\nbody { font-family: system-ui; padding: 2rem; background: #0a0a0a; color: #fafafa; }\n.container { max-width: 800px; margin: 0 auto; }\nh1 { font-size: 2rem; margin-bottom: 1rem; }',
            "script.js": 'console.log("{{name}} loaded!")',
        },
        "install": None,
        "dev": None,
    },
    "vanilla-js": {
        "name": "Vanilla JavaScript App",
        "files": {
            "package.json": '{\n  "name": "{{name}}",\n  "version": "1.0.0",\n  "scripts": {\n    "dev": "npx live-server --port=3000"\n  }\n}',
            "index.html": '<!DOCTYPE html>\n<html lang="en">\n<head>\n  <meta charset="UTF-8" />\n  <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n  <title>{{name}}</title>\n  <link rel="stylesheet" href="style.css" />\n</head>\n<body>\n  <div id="app"></div>\n  <script type="module" src="main.js"></script>\n</body>\n</html>',
            "main.js": 'import { createApp } from "./app.js"\ndocument.getElementById("app").appendChild(createApp())',
            "app.js": 'export function createApp() {\n  const div = document.createElement("div")\n  div.innerHTML = `<h1>{{name}}</h1><p>Vanilla JS is ready!</p>`\n  return div\n}',
            "style.css": '* { box-sizing: border-box; margin: 0; padding: 0; }\nbody { font-family: system-ui; padding: 2rem; background: #0a0a0a; color: #fafafa; }\nh1 { font-size: 2rem; margin-bottom: 1rem; }',
        },
        "install": None,
        "dev": "npx live-server --port=3000",
    },
}


async def tool_list_templates() -> dict:
    templates = []
    for key, tpl in TEMPLATES.items():
        templates.append({
            "id": key,
            "name": tpl["name"],
            "files": list(tpl["files"].keys()),
            "install": tpl.get("install"),
            "dev": tpl.get("dev"),
        })
    return {"templates": templates, "success": True}


async def tool_scaffold_project(template: str, name: str) -> dict:
    if template not in TEMPLATES:
        return {"error": f"Unknown template: {template}", "valid": list(TEMPLATES.keys()), "success": False}

    tpl = TEMPLATES[template]
    project_dir = WORKSPACE_DIR / name

    if project_dir.exists():
        return {"error": f"Directory already exists: {name}", "success": False}

    project_dir.mkdir(parents=True, exist_ok=True)
    created_files = []

    for file_path, content in tpl["files"].items():
        content = content.replace("{{name}}", name)
        target = project_dir / file_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        created_files.append(file_path)

    bus.emit("tool.scaffold", {"template": template, "name": name, "files": len(created_files)})

    return {
        "success": True,
        "project": name,
        "template": template,
        "files": created_files,
        "install": tpl.get("install"),
        "dev": tpl.get("dev"),
        "path": str(project_dir),
    }


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
    "run_python": tool_run_python,
    "fetch_url": tool_fetch_url,
    "diff_apply": tool_diff_apply,
    "kill_process": tool_kill_process,
    "env_info": tool_env_info,
    "list_templates": tool_list_templates,
    "scaffold_project": tool_scaffold_project,
}


async def call_tool(name: str, args: dict) -> dict:
    global _tool_call_count
    fn = TOOL_MAP.get(name)
    if not fn:
        return {"error": f"Unknown tool: {name}", "success": False}

    try:
        safety_check(name, args)
    except SafetyViolation as e:
        _tool_call_count += 1
        _tool_calls_by_name[name] = _tool_calls_by_name.get(name, 0) + 1
        return {"error": str(e), "success": False, "safety_blocked": True, "rule": e.rule}

    _tool_call_count += 1
    _tool_calls_by_name[name] = _tool_calls_by_name.get(name, 0) + 1

    bus.emit("tool.call", {"tool": name, "args": json.dumps(args, ensure_ascii=False)[:300]})

    t0 = time.time()
    result = await fn(**args)
    elapsed = time.time() - t0
    _tool_call_times.append({"tool": name, "time": elapsed, "success": result.get("success", False)})

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
    "- run_python: execute Python code directly\n"
    "- fetch_url: fetch content from URLs\n"
    "- diff_apply: apply unified diffs to files\n"
    "- list_templates: list project templates\n"
    "- scaffold_project: create project from template (react-ts, python-fastapi, node-express, static-html, vanilla-js)\n"
    "- done: signal task completion\n\n"
    f"Workspace: {WORKSPACE_DIR}\n"
    f"Current date: {datetime.now().strftime('%Y-%m-%d')}\n\n"
    "═══ SAFETY PROTOCOL (MANDATORY) ═══\n"
    "1. NEVER delete system files (C:\\Windows, /etc, /root, /boot)\n"
    "2. NEVER format drives or wipe data\n"
    "3. NEVER run: format, rd /s, rm -rf /, del /f, shutdown, reboot\n"
    "4. NEVER modify system registry or boot configuration\n"
    "5. NEVER kill system processes (explorer, csrss, lsass, svchost)\n"
    "6. NEVER write .exe, .dll, .sys, .bat files\n"
    "7. NEVER access .env files, .ssh keys, or credentials\n"
    "8. If you detect a potentially dangerous request, STOP and explain why\n"
    "9. Always use workspace for file operations — never outside it\n"
    "10. When in doubt, ask the user before proceeding\n\n"
    "IMPORTANT: Use tools to build the project step by step. "
    "Write each file, run builds, fix errors, commit progress. "
    "When finished, call the 'done' tool with a summary."
)


# ════════════════════════════════════════════════════
# 6. Agent Loop (Tool Calling + Output Parsing)
# ════════════════════════════════════════════════════

def _parse_tool_from_text(text: str) -> list:
    """Parse tool calls from plain text when model doesn't use function calling."""
    calls = []

    patterns = [
        (r'```json\s*\{[^`]*?"tool"\s*:\s*"([^"]+)"[^`]*?\}\s*```', 'json_block'),
        (r'```tool_call\s*\n(.*?)\n```', 'tool_block'),
        (r'(?:CALL|call|Call)\s+(\w+)\(([^)]*)\)', 'func_call'),
        (r'\[(?:TOOL|tool)\]\s*(\w+):\s*(.+)', 'bracket'),
    ]

    for pattern, fmt in patterns:
        for m in re.finditer(pattern, text, re.DOTALL):
            try:
                if fmt == 'json_block':
                    data = json.loads(m.group(0).strip('`json\n'))
                    calls.append({"name": data.get("tool", ""), "arguments": data.get("args", data.get("arguments", {}))})
                elif fmt == 'tool_block':
                    lines = m.group(1).strip().splitlines()
                    name = lines[0].strip() if lines else ""
                    args = {}
                    for line in lines[1:]:
                        if ":" in line:
                            k, v = line.split(":", 1)
                            args[k.strip()] = v.strip().strip('"')
                    calls.append({"name": name, "arguments": args})
                elif fmt == 'func_call':
                    name = m.group(1)
                    args_str = m.group(2)
                    args = {}
                    for pair in args_str.split(","):
                        if "=" in pair:
                            k, v = pair.split("=", 1)
                            args[k.strip()] = v.strip().strip('"').strip("'")
                    calls.append({"name": name, "arguments": args})
                elif fmt == 'bracket':
                    name = m.group(1)
                    args_str = m.group(2).strip()
                    args = {}
                    if args_str:
                        for pair in args_str.split(";"):
                            if "=" in pair:
                                k, v = pair.split("=", 1)
                                args[k.strip()] = v.strip().strip('"')
                    calls.append({"name": name, "arguments": args})
            except Exception:
                continue

    valid_tools = set(TOOL_MAP.keys())
    return [c for c in calls if c["name"] in valid_tools]


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
        self.consecutive_no_tools = 0

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
                parsed = _parse_tool_from_text(response_text)
                if parsed:
                    tool_calls = parsed

            if not tool_calls:
                self.consecutive_no_tools += 1
                if self.done:
                    break
                if self.consecutive_no_tools >= 3:
                    self.messages.append({
                        "role": "user",
                        "content": (
                            "You MUST use tools. Available tools: " +
                            ", ".join(TOOL_MAP.keys()) +
                            "\nExample: Use workspace_file_ops to create files, execute_shell_command to run commands, done when finished."
                        )
                    })
                    self.consecutive_no_tools = 0
                    continue
                if response_text.strip():
                    self.messages.append({
                        "role": "user",
                        "content": "Continue using tools. If done, call the done tool."
                    })
                    continue
                else:
                    break

            self.consecutive_no_tools = 0

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
# 9.5 Plugin System — Custom Tools from Python Files
# ════════════════════════════════════════════════════

PLUGINS_DIR = ROOT / "plugins"
PLUGINS_DIR.mkdir(exist_ok=True)

_loaded_plugins = {}


def _load_plugins():
    """Scan plugins/ directory for Python files with tool definitions."""
    for py_file in PLUGINS_DIR.glob("*.py"):
        if py_file.name.startswith("_"):
            continue
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(f"hermes_plugin_{py_file.stem}", str(py_file))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            if hasattr(mod, "HERMES_TOOLS"):
                for tool_def in mod.HERMES_TOOLS:
                    name = tool_def["name"]
                    func = tool_def["function"]
                    schema = tool_def["schema"]
                    TOOLS_SCHEMA.append({
                        "type": "function",
                        "function": {
                            "name": name,
                            "description": schema.get("description", ""),
                            "parameters": schema.get("parameters", {"type": "object", "properties": {}}),
                        }
                    })
                    TOOL_MAP[name] = func
                    _loaded_plugins[name] = {"file": py_file.name, "schema": schema}
                    print(f"  [Plugin] Loaded: {name} from {py_file.name}")

            if hasattr(mod, "HERMES_INIT"):
                mod.HERMES_INIT()

        except Exception as e:
            print(f"  [Plugin] Failed to load {py_file.name}: {e}")


def _reload_plugins():
    """Reload all plugins."""
    global _loaded_plugins
    _loaded_plugins = {}
    to_remove = [k for k in TOOL_MAP if k not in [
        "workspace_file_ops", "execute_shell_command", "git_checkpoint",
        "analyze_project_structure", "capture_screenshot", "read_image",
        "search_code", "run_python", "fetch_url", "diff_apply",
        "kill_process", "env_info", "list_templates", "scaffold_project",
        "done",
    ]]
    for k in to_remove:
        del TOOL_MAP[k]
    for t in TOOLS_SCHEMA[:]:
        if t["function"]["name"] in to_remove:
            TOOLS_SCHEMA.remove(t)
    _load_plugins()


async def plugins_handler(request):
    """List loaded plugins."""
    return web.json_response({
        "plugins": _loaded_plugins,
        "total": len(_loaded_plugins),
        "directory": str(PLUGINS_DIR),
    })


async def reload_plugins_handler(request):
    """Reload all plugins."""
    try:
        _reload_plugins()
        return web.json_response({
            "success": True,
            "plugins": _loaded_plugins,
            "total_tools": len(TOOL_MAP),
        })
    except Exception as e:
        return web.json_response({"error": str(e), "success": False}, status=500)


# ════════════════════════════════════════════════════
# 10. Stats Dashboard
# ════════════════════════════════════════════════════

_tool_call_count = 0
_tool_calls_by_name = {}
_tool_call_times = []

async def stats_handler(request):
    ollama_ok = await ollama.is_available()
    models_list = await ollama.list_models() if ollama_ok else []

    stats = {
        "server": {
            "version": "3.2-stats",
            "port": PORT,
            "uptime": time.time(),
        },
        "tools": {
            "total": len(TOOL_MAP),
            "available": list(TOOL_MAP.keys()),
            "total_calls": _tool_call_count,
            "calls_by_name": _tool_calls_by_name,
        },
        "models": {
            "ollama": ollama_ok,
            "reasoning": {"model": MODEL_REASONING, "installed": ollama.model_installed(MODEL_REASONING, models_list)},
            "coding": {"model": MODEL_CODING, "installed": ollama.model_installed(MODEL_CODING, models_list)},
            "agent": {"model": MODEL_AGENT, "installed": ollama.model_installed(MODEL_AGENT, models_list)},
            "vision": {"model": MODEL_VISION, "installed": ollama.model_installed(MODEL_VISION, models_list)},
        },
        "workspace": str(WORKSPACE_DIR),
        "pillow": PILLOW_OK,
    }
    return web.json_response(stats)


async def stats_dashboard_handler(request):
    html_path = FRONTEND_DIR / "stats.html"
    if html_path.exists():
        return web.FileResponse(html_path)
    return web.Response(text="Stats dashboard not found", status=404)


# ════════════════════════════════════════════════════
# 11. App Setup
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
    web.get("/stats", stats_dashboard_handler),
    web.get("/api/health", health_handler),
    web.get("/api/models", models_handler),
    web.get("/api/tools", tools_handler),
    web.get("/api/stats", stats_handler),
    web.get("/api/workspace", workspace_handler),
    web.get("/api/plugins", plugins_handler),
    web.post("/api/plugins/reload", reload_plugins_handler),
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
    bus.emit("system.started", {"time": time.time(), "version": "4.0"})

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
    print(f"  Hermes Studio v4.0 — Agentic Tool Suite")
    print(f"  http://127.0.0.1:{PORT}")
    print(f"  Ollama:      {'ON' if ollama_ok else 'OFF'}")
    print(f"  Reasoning:   {MODEL_REASONING} {'ready' if reasoning_ok else 'NOT INSTALLED'}")
    print(f"  Coding:      {MODEL_CODING} {'ready' if coding_ok else 'NOT INSTALLED'}")
    print(f"  Agent:       {MODEL_AGENT} {'ready' if agent_ok else 'NOT INSTALLED'}")
    print(f"  Vision:      {MODEL_VISION} {'ready' if vision_ok else 'NOT INSTALLED'}")
    print(f"  Pillow:      {'YES' if PILLOW_OK else 'NO (pip install Pillow)'}")
    print(f"  Workspace:   {WORKSPACE_DIR}")
    print(f"  Safety:      ACTIVE (30+ rules)")
    print(f"  Plugins:     {PLUGINS_DIR}")

    _load_plugins()
    print(f"  Tools:       {len(TOOLS_SCHEMA)} available")
    if not reasoning_ok or not coding_ok:
        print()
        print("  Run:  python setup_models.py")
    print()


app.on_startup.append(on_startup)


if __name__ == "__main__":
    web.run_app(app, host="127.0.0.1", port=PORT)
