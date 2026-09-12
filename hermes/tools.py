"""All tool implementations for Hermes agent."""
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
from datetime import datetime

from hermes.core import (
    WORKSPACE_DIR, BACKUP_DIR, CFG, SHELL_TIMEOUT,
)
from hermes.bus import bus
from hermes.safety import safety_check, SafetyViolation

try:
    from PIL import ImageGrab
    PILLOW_OK = True
except ImportError:
    PILLOW_OK = False
    print("[Hermes] Pillow not installed — screenshot tools disabled. pip install Pillow")


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
                                   max_results: int = 30,
                                   replace_all: bool = False) -> dict:
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
            if replace_all:
                new_data = data.replace(old_text, new_text)
                replaced = count
            else:
                new_data = data.replace(old_text, new_text, 1)
                replaced = 1
            target.write_text(new_data, encoding="utf-8")
            return {"success": True, "replaced": replaced, "remaining_occurrences": new_data.count(old_text), "path": path}

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

    async def _run(cmd: list):
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=str(WORKSPACE_DIR),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
        out, err = await asyncio.wait_for(proc.communicate(), timeout=30)
        return proc.returncode, out.decode("utf-8", errors="replace"), err.decode("utf-8", errors="replace")

    try:
        code, _, err = await _run(["git", "init"])
        if code != 0 and "already exists" not in err:
            return {"error": f"git init failed: {err}", "success": False}

        if add_all:
            code, _, err = await _run(["git", "add", "-A"])
            if code != 0:
                return {"error": f"git add failed: {err}", "success": False}

        code, out, err = await _run(["git", "commit", "-m", message, "--allow-empty"])
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
    """Capture a screenshot.

    NOTE: The 'region' parameter is accepted for API compatibility but the
    capture is always fullscreen because Pillow's ImageGrab.grab() does not
    support selecting individual windows or regions across platforms.
    """
    if not PILLOW_OK:
        return {"error": "Pillow not installed. Run: pip install Pillow", "success": False}

    try:
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
        req.add_header("User-Agent", "Hermes/5.0")

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
                    while i < len(lines) and not lines[i].startswith("@@") and not lines[i].startswith("diff"):
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

    py_packages = []
    try:
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


async def tool_done(summary: str) -> dict:
    return {"success": True, "summary": summary}


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
                    "replace_all": {"type": "boolean", "default": False, "description": "Replace all occurrences (search_replace only)"},
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
            "description": "Capture a screenshot of the entire screen. Returns base64 image. Note: region parameter is accepted for API compatibility but capture is always fullscreen.",
            "parameters": {
                "type": "object",
                "properties": {
                    "region": {
                        "type": "string",
                        "enum": ["fullscreen", "active_window", "region"],
                        "default": "fullscreen",
                        "description": "What to capture (always fullscreen due to Pillow limitation)"
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
            "description": "Create a new project from a template. Options: react-ts, python-fastapi, node-express, static-html, vanilla-js.",
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
    "list_templates": None,
    "scaffold_project": None,
    "done": tool_done,
}


def _wrap_module_tool(fn):
    """Wrap a tool function from a module (takes args dict, returns JSON string) to
    work with call_tool's **kwargs dispatch and dict-return convention."""
    import json as _json
    async def wrapper(**kwargs):
        raw = await fn(kwargs)
        if isinstance(raw, str):
            try:
                return _json.loads(raw)
            except Exception:
                return {"result": raw, "success": True}
        return raw
    wrapper.__name__ = fn.__name__
    return wrapper


def _register_tool_module(module_name: str):
    """Import a tool module, convert its schemas, wrap its functions, register them."""
    import importlib
    mod = importlib.import_module(f"hermes.{module_name}")
    for tool_def in mod.TOOLS:
        name = tool_def["name"]
        TOOLS_SCHEMA.append({
            "type": "function",
            "function": {
                "name": name,
                "description": tool_def.get("description", ""),
                "parameters": tool_def.get("parameters", {"type": "object", "properties": {}}),
            }
        })
        fn = mod.functions.get(name)
        if fn:
            TOOL_MAP[name] = _wrap_module_tool(fn)


_tool_modules = [
    "tools_docker",
    "tools_security",
    "tools_profiling",
    "tools_database",
    "tools_apitest",
    "tools_docs",
    "tools_git_advanced",
    "tools_backup",
    "tools_migration",
    "tools_kubernetes",
    "tools_monitoring",
    "tools_automation",
    "tools_ai",
    "tools_web",
]

for _mod_name in _tool_modules:
    try:
        _register_tool_module(_mod_name)
    except Exception as _e:
        print(f"[Hermes] Failed to load tool module {_mod_name}: {_e}")


_tool_call_count = 0
_tool_calls_by_name = {}
_tool_call_times = []


def _init_template_tools():
    """Lazily import template tools to avoid circular imports."""
    from hermes.templates import tool_list_templates, tool_scaffold_project
    TOOL_MAP["list_templates"] = tool_list_templates
    TOOL_MAP["scaffold_project"] = tool_scaffold_project


_init_template_tools()


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


def register_plugin_tool(name: str, func, schema: dict):
    """Register a plugin tool. Plugin tools go through safety_check like built-in tools."""
    TOOL_MAP[name] = func
    TOOLS_SCHEMA.append({
        "type": "function",
        "function": {
            "name": name,
            "description": schema.get("description", ""),
            "parameters": schema.get("parameters", {"type": "object", "properties": {}}),
        }
    })
