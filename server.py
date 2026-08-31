#!/usr/bin/env python3
"""
Hermes Studio v3 — Agentic Tool Suite (100% offline).

An autonomous AI agent that builds complete software projects.
External/local AI is the "brain", Hermes is its "hands" on disk.

Tools (OpenAI/Ollama function-calling compatible):
  workspace_file_ops      — read, write, create files with backup
  execute_shell_command   — run shell commands with timeout
  git_checkpoint          — auto-commit after each step
  analyze_project_structure — scan directory tree

Endpoints:
  GET  /api/health        — health check
  GET  /api/models        — installed models status
  POST /api/chat          — chat (?stream=1 for SSE)
  POST /api/agent         — run agent loop with tool calling
  POST /api/upload        — file upload
  GET  /api/events        — SSE event stream
  GET  /api/tools         — list available tools + schemas
  GET  /api/workspace     — workspace file tree
"""
import asyncio
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
# 1. Tool Definitions (OpenAI/Ollama JSON Schema)
# ════════════════════════════════════════════════════

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "workspace_file_ops",
            "description": "Read, write, create, delete, or list files in the workspace. Use 'action' to specify: read, write, create, delete, list, list_tree. For write/create, provide 'content'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["read", "write", "create", "delete", "list", "list_tree"],
                        "description": "File operation to perform"
                    },
                    "path": {
                        "type": "string",
                        "description": "Relative path from workspace root (e.g. 'src/App.tsx')"
                    },
                    "content": {
                        "type": "string",
                        "description": "File content for write/create actions"
                    },
                    "encoding": {
                        "type": "string",
                        "enum": ["utf-8", "latin-1"],
                        "default": "utf-8",
                        "description": "File encoding"
                    }
                },
                "required": ["action", "path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_shell_command",
            "description": "Execute a shell command in the workspace directory. Use for: npm install, npm run build, pip install, pytest, tsc, etc. Returns stdout, stderr, and exit code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to execute (e.g. 'npm install', 'python -m pytest')"
                    },
                    "timeout": {
                        "type": "integer",
                        "default": 120,
                        "description": "Timeout in seconds"
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Working directory relative to workspace (default: workspace root)"
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_checkpoint",
            "description": "Create a git checkpoint (commit) in the workspace. Use after completing a meaningful step.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Commit message describing what was done"
                    },
                    "add_all": {
                        "type": "boolean",
                        "default": True,
                        "description": "Stage all changes before commit"
                    }
                },
                "required": ["message"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_project_structure",
            "description": "Scan workspace directory tree and return file structure with sizes. Use to understand current project state.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "default": ".",
                        "description": "Relative path to scan from workspace root"
                    },
                    "max_depth": {
                        "type": "integer",
                        "default": 4,
                        "description": "Maximum directory depth to scan"
                    },
                    "ignore": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": ["node_modules", ".git", "__pycache__", "dist", "build", ".next"],
                        "description": "Directories to ignore"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "done",
            "description": "Signal that the task is complete. Provide a summary of what was built.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Summary of what was accomplished"
                    }
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
    """Resolve relative path safely within workspace."""
    if not rel or rel.startswith("..") or rel.startswith("/"):
        return None
    resolved = (WORKSPACE_DIR / rel).resolve()
    if not str(resolved).startswith(str(WORKSPACE_DIR.resolve())):
        return None
    return resolved


def _backup_file(target: pathlib.Path):
    """Create backup before overwriting."""
    if target.exists() and CFG["tools"].get("backup_on_write", True):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        rel = target.relative_to(WORKSPACE_DIR)
        bak = BACKUP_DIR / f"{ts}_{rel.parent}" / f"{target.name}"
        bak.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, bak)


async def tool_workspace_file_ops(action: str, path: str, content: str = "", encoding: str = "utf-8") -> dict:
    target = _safe_path(path)
    if target is None:
        return {"error": f"Invalid path: {path}", "success": False}

    try:
        if action == "read":
            if not target.exists():
                return {"error": f"File not found: {path}", "success": False}
            data = target.read_text(encoding=encoding, errors="replace")
            return {"content": data, "size": len(data), "success": True}

        elif action == "write":
            target.parent.mkdir(parents=True, exist_ok=True)
            _backup_file(target)
            target.write_text(content, encoding=encoding)
            return {"success": True, "path": str(target.relative_to(WORKSPACE_DIR)), "size": len(content)}

        elif action == "create":
            if target.exists():
                return {"error": f"File already exists: {path}. Use 'write' to overwrite.", "success": False}
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding=encoding)
            return {"success": True, "path": str(target.relative_to(WORKSPACE_DIR)), "size": len(content)}

        elif action == "delete":
            if not target.exists():
                return {"error": f"File not found: {path}", "success": False}
            if target.is_dir():
                shutil.rmtree(target)
                return {"success": True, "deleted": "directory"}
            _backup_file(target)
            target.unlink()
            return {"success": True, "deleted": "file"}

        elif action == "list":
            if not target.exists():
                return {"error": f"Directory not found: {path}", "success": False}
            if target.is_file():
                return {"files": [target.name], "success": True}
            entries = []
            for e in sorted(target.iterdir()):
                kind = "dir" if e.is_dir() else "file"
                size = e.stat().st_size if e.is_file() else 0
                entries.append({"name": e.name, "type": kind, "size": size})
            return {"files": entries, "success": True}

        elif action == "list_tree":
            if not target.exists():
                return {"error": f"Directory not found: {path}", "success": False}
            tree = _build_tree(target, max_depth=4)
            return {"tree": tree, "success": True}

        return {"error": f"Unknown action: {action}", "success": False}

    except Exception as e:
        return {"error": str(e), "success": False}


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


async def tool_execute_shell_command(command: str, timeout: int = 120, cwd: str = ".") -> dict:
    work_dir = _safe_path(cwd) or WORKSPACE_DIR
    if not work_dir.exists():
        work_dir = WORKSPACE_DIR

    timeout = min(timeout, SHELL_TIMEOUT)
    bus.emit("tool.shell", {"command": command, "cwd": str(work_dir)})

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=str(work_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return {"error": f"Command timed out after {timeout}s", "exit_code": -1, "success": False}

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
        files, dirs = 0, 0
        for n in node_list:
            if n["type"] == "dir":
                dirs += 1
                f, d = _count(n.get("children", []))
                files += f
                dirs += d
            else:
                files += 1
        return files, dirs

    total_files, total_dirs = _count(tree)

    return {
        "success": True,
        "path": str(scan_path.relative_to(WORKSPACE_DIR)) if scan_path != WORKSPACE_DIR else ".",
        "tree": tree,
        "stats": {"total_files": total_files, "total_dirs": total_dirs},
    }


# ════════════════════════════════════════════════════
# 3. Tool Dispatcher
# ════════════════════════════════════════════════════

TOOL_MAP = {
    "workspace_file_ops": tool_workspace_file_ops,
    "execute_shell_command": tool_execute_shell_command,
    "git_checkpoint": tool_git_checkpoint,
    "analyze_project_structure": tool_analyze_project_structure,
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
            _, data = await self._post("/api/generate", payload, timeout_s=180)
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
            async for chunk in self._post_stream("/api/generate", payload, timeout_s=180):
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
            async for chunk in self._post_stream("/api/chat", payload, timeout_s=180):
                yield chunk
        except Exception as e:
            yield {"error": str(e)}


ollama = Ollama()


# ════════════════════════════════════════════════════
# 5. Smart Router
# ════════════════════════════════════════════════════

CODE_KEYWORDS = re.compile(
    r"(?:"
    r"код|кодируй|напиши код|программ|скрипт|функци"
    r"|html|css|javascript|typescript|react|vue|angular|svelte"
    r"|python|java|c\+\+|rust|go|sql"
    r"|сайт|лендинг|интерфейс|страниц|верстк|фронтенд|бэкенд"
    r"|компонент|массив|объект|класс|метод|api|endpoint"
    r"|debug|ошибк|баг|fix|исправ"
    r"|deploy|билд|сборк|настроен"
    r"|bot|скрипт|автоматиз"
    r"|создай|создать|собери|собрать|проект|систему|приложен"
    r")",
    re.IGNORECASE,
)


def route_request(prompt):
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

SYSTEM_AGENT = (
    f"{AGENT_SYSTEM}\n\n"
    "You have these tools:\n"
    "- workspace_file_ops: read/write/create/delete/list files in workspace\n"
    "- execute_shell_command: run shell commands (npm install, pytest, etc.)\n"
    "- git_checkpoint: create git commits\n"
    "- analyze_project_structure: scan directory tree\n"
    "- done: signal task completion\n\n"
    f"Workspace: {WORKSPACE_DIR}\n"
    f"Current date: {datetime.now().strftime('%Y-%m-%d')}\n\n"
    "IMPORTANT: Use tools to build the project step by step. "
    "Write each file, run builds, fix errors, commit progress. "
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

    print("[Hermes] Ollama not running, attempting to start...")
    if not OLLAMA_EXE.exists():
        print(f"[Hermes] Ollama not found at {OLLAMA_EXE}")
        return False

    try:
        os.environ["OLLAMA_HOST"] = "127.0.0.1:11434"
        os.environ["OLLAMA_MODELS"] = OLLAMA_MODELS
        subprocess.Popen(
            [str(OLLAMA_EXE), "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as e:
        print(f"[Hermes] Failed to start Ollama: {e}")
        return False

    for _ in range(20):
        await asyncio.sleep(0.5)
        if await ollama.is_available():
            print("[Hermes] Ollama started successfully.")
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
        "version": "3.0-agentic",
        "port": PORT,
        "ollama": {"available": ollama_ok},
        "workspace": str(WORKSPACE_DIR),
    })


async def models_handler(request):
    ollama_ok = await ollama.is_available()
    models = await ollama.list_models() if ollama_ok else []
    return web.json_response({
        "ollama": {"available": ollama_ok, "models": models},
        "reasoning": {"model": MODEL_REASONING, "installed": ollama.model_installed(MODEL_REASONING, models)},
        "coding": {"model": MODEL_CODING, "installed": ollama.model_installed(MODEL_CODING, models)},
        "agent": {"model": MODEL_AGENT, "installed": ollama.model_installed(MODEL_AGENT, models)},
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
    system = SYSTEM_CODING if route_type == "coding" else SYSTEM_REASONING

    if history:
        recent = history[-6:]
        lines = []
        for m in recent:
            role = "User" if m.get("role") == "user" else "Assistant"
            lines.append(f"{role}: {m.get('content', '')}")
        system += "\n\nRecent context:\n" + "\n".join(lines)

    bus.emit("chat.request", {"prompt": prompt[:200], "model": model, "route": route_type})

    if not await ensure_ollama():
        msg = (
            "Ollama не запущена.\n\n"
            "1. Установи: https://ollama.com\n"
            "2. Запусти:  ollama serve\n"
            "3. Скачай модели:  python setup_models.py\n\n"
            "Или запусти Hermes — он попробует стартовать автоматически."
        )
        if use_stream:
            return await _stream_text(request, msg)
        return web.json_response({"text": msg, "model": "unavailable"})

    installed = await ollama.list_models()
    if not ollama.model_installed(model, installed):
        msg = (
            f"Модель {model} не скачана.\n\n"
            f"Запусти:  python setup_models.py\n"
            f"Или вручную:  ollama pull {model}"
        )
        if use_stream:
            return await _stream_text(request, msg)
        return web.json_response({"text": msg, "model": "missing"})

    if use_stream:
        bus.emit("chat.stream_start", {"model": model, "route": route_type})
        resp = web.StreamResponse(
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
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

    return web.json_response({"text": "Не удалось получить ответ. Попробуй ещё раз.", "model": "error"})


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
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
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


async def _stream_text(request, text):
    resp = web.StreamResponse(
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
    await resp.prepare(request)
    chunk = json.dumps({"text": text, "done": False}, ensure_ascii=False)
    await resp.write(f"data: {chunk}\n\n".encode())
    done = json.dumps({"text": "", "done": True}, ensure_ascii=False)
    await resp.write(f"data: {done}\n\n".encode())
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
                return web.json_response(
                    {"error": f"File too large (max {CFG['limits']['max_upload_mb']}MB)"},
                    status=413,
                )
            f.write(chunk)

    bus.emit("upload.done", {"filename": filename, "size": size})
    return web.json_response({"path": str(dest).replace("\\", "/"), "size": size, "filename": filename})


async def events_handler(request):
    q = bus.subscribe()
    resp = web.StreamResponse(
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
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
    web.post("/api/upload", upload_handler),
    web.get("/api/events", events_handler),
]
for route in routes:
    cors.add(app.router.add_route(route.method, route.path, route.handler))

if UPLOAD_DIR.exists():
    app.router.add_static("/uploads", str(UPLOAD_DIR), show_index=False)


async def on_startup(app):
    bus.emit("system.started", {"time": time.time(), "version": "3.0-agentic"})

    ollama_ok = await ensure_ollama()
    models = await ollama.list_models() if ollama_ok else []
    reasoning_ok = ollama.model_installed(MODEL_REASONING, models)
    coding_ok = ollama.model_installed(MODEL_CODING, models)
    agent_ok = ollama.model_installed(MODEL_AGENT, models)

    bus.emit("models.status", {
        "ollama": ollama_ok,
        "reasoning": reasoning_ok,
        "coding": coding_ok,
        "agent": agent_ok,
    })

    print()
    print(f"  Hermes Studio v3 — Agentic Tool Suite")
    print(f"  http://127.0.0.1:{PORT}")
    print(f"  Ollama:      {'ON' if ollama_ok else 'OFF'}")
    print(f"  Reasoning:   {MODEL_REASONING} {'ready' if reasoning_ok else 'NOT INSTALLED'}")
    print(f"  Coding:      {MODEL_CODING} {'ready' if coding_ok else 'NOT INSTALLED'}")
    print(f"  Agent:       {MODEL_AGENT} {'ready' if agent_ok else 'NOT INSTALLED'}")
    print(f"  Workspace:   {WORKSPACE_DIR}")
    print(f"  Tools:       {len(TOOLS_SCHEMA)} available")
    if not reasoning_ok or not coding_ok:
        print()
        print("  Run:  python setup_models.py")
    print()


app.on_startup.append(on_startup)


# ════════════════════════════════════════════════════
# 11. Main
# ════════════════════════════════════════════════════

if __name__ == "__main__":
    web.run_app(app, host="127.0.0.1", port=PORT)
