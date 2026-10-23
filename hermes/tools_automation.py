"""Automation tools for Hermes agent."""
import asyncio
import fnmatch
import json
import os
import shutil
import sys
import time
from datetime import datetime
# --- константы вынесены FORGE refactor ---
CONST_30 = 30
CONST_50 = 50
CONST_60 = 60
CONST_1024 = 1024
CONST_86400 = 86400


TOOLS = [
    {"name": "schedule_task", "description": "Schedule a shell command to run after a delay or at a specific time", "parameters": {"type": "object", "properties": {"command": {"type": "string", "description": "Shell command to run"}, "delay_seconds": {"type": "integer", "description": "Delay before running (seconds)", "default": 0}, "at_time": {"type": "string", "description": "Run at HH:MM (24h format)"}}, "required": ["command"]}},
    {"name": "watch_file", "description": "Watch a file for changes and return when modified", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "File path to watch"}, "timeout": {"type": "integer", "description": "Max wait time in seconds", "default": CONST_60}}, "required": ["path"]}},
    {"name": "watch_directory", "description": "Watch a directory for changes and return new/modified files", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Directory to watch"}, "timeout": {"type": "integer", "description": "Max wait time in seconds", "default": CONST_30}, "recursive": {"type": "boolean", "description": "Watch subdirectories", "default": False}}}},
    {"name": "batch_rename", "description": "Rename files in bulk using pattern matching", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Directory containing files"}, "find_pattern": {"type": "string", "description": "Pattern to match (e.g. '*.txt', '*.IMG_*')"}, "replace_with": {"type": "string", "description": "Replacement pattern (use {1} for capture groups)"}, "dry_run": {"type": "boolean", "description": "Preview without renaming", "default": True}}, "required": ["path", "find_pattern", "replace_with"]}},
    {"name": "batch_convert", "description": "Convert files between formats (image/text/video)", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Directory with source files"}, "from_format": {"type": "string", "description": "Source format (e.g. .txt, .csv)"}, "to_format": {"type": "string", "description": "Target format (e.g. .json, .md)"}, "converter": {"type": "string", "description": "Conversion method: 'upper', 'lower', 'csv_to_json', 'json_to_csv', 'markdown'"}}, "required": ["path", "from_format", "to_format", "converter"]}},
    {"name": "auto_cleanup", "description": "Auto-delete old files matching criteria", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Directory to clean"}, "older_than_days": {"type": "integer", "description": "Delete files older than N days"}, "pattern": {"type": "string", "description": "File pattern to match (e.g. '*.log', '*.tmp')"}, "dry_run": {"type": "boolean", "description": "Preview without deleting", "default": True}}}},
    {"name": "sync_folder", "description": "One-way sync: copy source to destination (mirror)", "parameters": {"type": "object", "properties": {"source": {"type": "string", "description": "Source directory"}, "dest": {"type": "string", "description": "Destination directory"}, "delete_orphans": {"type": "boolean", "description": "Delete files in dest not in source", "default": False}, "exclude": {"type": "array", "items": {"type": "string"}, "description": "Patterns to exclude"}}, "required": ["source", "dest"]}},
    {"name": "mirror_folder", "description": "Two-way sync: merge changes between two folders", "parameters": {"type": "object", "properties": {"folder_a": {"type": "string", "description": "First directory"}, "folder_b": {"type": "string", "description": "Second directory"}, "dry_run": {"type": "boolean", "description": "Preview without syncing", "default": True}}}},
    {"name": "compress_files", "description": "Create zip or tar archive from files", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "File or directory to compress"}, "output": {"type": "string", "description": "Output archive path"}, "format": {"type": "string", "enum": ["zip", "tar", "tar.gz"], "description": "Archive format", "default": "zip"}}, "required": ["path", "output"]}},
    {"name": "extract_archive", "description": "Extract zip, tar, or tar.gz archive", "parameters": {"type": "object", "properties": {"archive": {"type": "string", "description": "Archive file path"}, "dest": {"type": "string", "description": "Destination directory"}, "password": {"type": "string", "description": "Archive password (zip only)"}}, "required": ["archive", "dest"]}},
]

functions = {}

async def schedule_task(args):
    command = args["command"]
    delay = args.get("delay_seconds", 0)
    at_time = args.get("at_time", "")
    try:
        if at_time:
            now = datetime.now()
            h, m = map(int, at_time.split(":"))
            target = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if target <= now:
                target = target.replace(day=target.day + 1)
            delay = int((target - now).total_seconds())
        if sys.platform == "win32":
            task_name = f"HermesTask_{int(time.time())}"
            run_time = datetime.now().strftime("%H:%M")
            proc = await asyncio.create_subprocess_shell(
                f'schtasks /create /tn "{task_name}" /tr "{command}" /sc once /st {run_time} /f',
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            return json.dumps({"success": proc.returncode == 0, "output": stdout.decode(errors="ignore").strip(), "delay_seconds": delay})
        else:
            async def _run_later():
                await asyncio.sleep(delay)
                proc = await asyncio.create_subprocess_shell(
                    command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
                )
                await proc.communicate()
            asyncio.create_task(_run_later())
            return json.dumps({"success": True, "scheduled": True, "delay_seconds": delay, "command": command})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def watch_file(args):
    path = args["path"]
    timeout = args.get("timeout", CONST_60)
    try:
        target = os.path.abspath(path)
        if not os.path.exists(target):
            return json.dumps({"error": f"File not found: {path}", "success": False})
        initial_mtime = os.path.getmtime(target)
        initial_size = os.path.getsize(target)
        start = time.time()
        while time.time() - start < timeout:
            await asyncio.sleep(0.5)
            current_mtime = os.path.getmtime(target)
            if current_mtime != initial_mtime:
                current_size = os.path.getsize(target)
                return json.dumps({
                    "success": True, "changed": True,
                    "file": path, "elapsed_seconds": round(time.time() - start, 2),
                    "old_size": initial_size, "new_size": current_size,
                })
        return json.dumps({"success": True, "changed": False, "file": path, "timeout": timeout, "elapsed_seconds": timeout})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def watch_directory(args):
    path = args["path"]
    timeout = args.get("timeout", CONST_30)
    recursive = args.get("recursive", False)
    try:
        target = os.path.abspath(path)
        if not os.path.exists(target):
            return json.dumps({"error": f"Directory not found: {path}", "success": False})
        def _snapshot():
            files = {}
            if recursive:
                for root, dirs, fnames in os.walk(target):
                    for f in fnames:
                        fp = os.path.join(root, f)
                        files[fp] = (os.path.getmtime(fp), os.path.getsize(fp))
            else:
                for f in os.listdir(target):
                    fp = os.path.join(target, f)
                    if os.path.isfile(fp):
                        files[fp] = (os.path.getmtime(fp), os.path.getsize(fp))
            return files
        before = _snapshot()
        start = time.time()
        while time.time() - start < timeout:
            await asyncio.sleep(1)
            after = _snapshot()
            new_files = [f for f in after if f not in before]
            modified_files = [f for f in after if f in before and after[f] != before[f]]
            deleted_files = [f for f in before if f not in after]
            if new_files or modified_files or deleted_files:
                return json.dumps({
                    "success": True, "changed": True,
                    "new_files": [os.path.relpath(f, target) for f in new_files],
                    "modified_files": [os.path.relpath(f, target) for f in modified_files],
                    "deleted_files": [os.path.relpath(f, target) for f in deleted_files],
                    "elapsed_seconds": round(time.time() - start, 2),
                })
        return json.dumps({"success": True, "changed": False, "timeout": timeout})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def batch_rename(args):
    path = args["path"]
    find_pattern = args["find_pattern"]
    replace_with = args.get("replace_with", "")
    dry_run = args.get("dry_run", True)
    try:
        target = os.path.abspath(path)
        if not os.path.exists(target):
            return json.dumps({"error": f"Directory not found: {path}", "success": False})
        files = [f for f in os.listdir(target) if os.path.isfile(os.path.join(target, f))]
        matched = fnmatch.filter(files, find_pattern)
        renames = []
        for fname in matched:
            new_name = fname
            base, ext = os.path.splitext(fname)
            new_name = replace_with.replace("{name}", base).replace("{ext}", ext).replace("{0}", base)
            import re as _re
            for i, part in enumerate(_re.findall(r'\{(\d+)\}', replace_with)):
                idx = int(part) if part.isdigit() else 0
                if idx < len(base):
                    new_name = _re.sub(r'\{' + str(part) + r'\}', base[idx:idx+1] if idx < len(base) else "", new_name, 1)
            if "{ext}" not in replace_with and not new_name.endswith(ext):
                new_name = new_name + ext
            if new_name != fname:
                renames.append({"old": fname, "new": new_name})
                if not dry_run:
                    os.rename(os.path.join(target, fname), os.path.join(target, new_name))
        return json.dumps({"success": True, "renames": renames, "count": len(renames), "dry_run": dry_run})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def batch_convert(args):
    path = args["path"]
    from_fmt = args["from_format"]
    to_fmt = args["to_format"]
    converter = args["converter"]
    try:
        target = os.path.abspath(path)
        if not os.path.exists(target):
            return json.dumps({"error": f"Path not found: {path}", "success": False})
        converted = []
        for root, dirs, files in os.walk(target):
            for fname in files:
                if not fname.endswith(from_fmt):
                    continue
                src = os.path.join(root, fname)
                dst = os.path.join(root, os.path.splitext(fname)[0] + to_fmt)
                try:
                    if converter == "upper":
                        with open(src, "r", errors="ignore") as f:
                            content = f.read()
                        with open(dst, "w", encoding="utf-8") as f:
                            f.write(content.upper())
                    elif converter == "lower":
                        with open(src, "r", errors="ignore") as f:
                            content = f.read()
                        with open(dst, "w", encoding="utf-8") as f:
                            f.write(content.lower())
                    elif converter == "csv_to_json":
                        import csv
                        with open(src, "r", errors="ignore") as f:
                            reader = csv.DictReader(f)
                            rows = list(reader)
                        with open(dst, "w", encoding="utf-8") as f:
                            json.dump(rows, f, indent=2)
                    elif converter == "json_to_csv":
                        import csv
                        with open(src, "r", errors="ignore") as f:
                            data = json.load(f)
                        if isinstance(data, list) and data:
                            with open(dst, "w", newline="", encoding="utf-8") as f:
                                writer = csv.DictWriter(f, fieldnames=data[0].keys())
                                writer.writeheader()
                                writer.writerows(data)
                    elif converter == "markdown":
                        with open(src, "r", errors="ignore") as f:
                            content = f.read()
                        import re as _re
                        md = _re.sub(r'^\s*#\s+(.+)$', r'# \1', content, flags=_re.MULTILINE)
                        with open(dst, "w", encoding="utf-8") as f:
                            f.write(md)
                    converted.append({"from": fname, "to": os.path.basename(dst)})
                except Exception as ce:
                    converted.append({"from": fname, "error": str(ce)})
        return json.dumps({"success": True, "converted": converted, "count": len(converted)})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def auto_cleanup(args):
    path = args["path"]
    older_than_days = args.get("older_than_days", CONST_30)
    pattern = args.get("pattern", "*")
    dry_run = args.get("dry_run", True)
    try:
        target = os.path.abspath(path)
        if not os.path.exists(target):
            return json.dumps({"error": f"Directory not found: {path}", "success": False})
        cutoff = time.time() - (older_than_days * CONST_86400)
        deleted = []
        total_size = 0
        for root, dirs, files in os.walk(target):
            for fname in files:
                if not fnmatch.fnmatch(fname, pattern):
                    continue
                fp = os.path.join(root, fname)
                try:
                    mtime = os.path.getmtime(fp)
                    if mtime < cutoff:
                        size = os.path.getsize(fp)
                        deleted.append({"file": os.path.relpath(fp, target), "size": size, "age_days": round((time.time() - mtime) / CONST_86400, 1)})
                        total_size += size
                        if not dry_run:
                            os.remove(fp)
                except Exception:
                    pass
        return json.dumps({
            "success": True, "deleted": deleted, "count": len(deleted),
            "total_size_mb": round(total_size / CONST_1024 / CONST_1024, 2),
            "dry_run": dry_run, "older_than_days": older_than_days,
        })
    except Exception as e:
        return json.dumps({"error": str(e)})

async def sync_folder(args):
    source = args["source"]
    dest = args["dest"]
    delete_orphans = args.get("delete_orphans", False)
    exclude = args.get("exclude", [])
    try:
        src = os.path.abspath(source)
        dst = os.path.abspath(dest)
        if not os.path.exists(src):
            return json.dumps({"error": f"Source not found: {source}", "success": False})
        os.makedirs(dst, exist_ok=True)
        copied, skipped, deleted = [], [], []
        def _should_exclude(name):
            return any(fnmatch.fnmatch(name, pat) for pat in exclude)
        for root, dirs, files in os.walk(src):
            rel_root = os.path.relpath(root, src)
            for f in files:
                if _should_exclude(f):
                    continue
                src_file = os.path.join(root, f)
                dst_file = os.path.join(dst, rel_root, f)
                os.makedirs(os.path.dirname(dst_file), exist_ok=True)
                try:
                    if not os.path.exists(dst_file) or os.path.getmtime(src_file) > os.path.getmtime(dst_file):
                        shutil.copy2(src_file, dst_file)
                        copied.append(os.path.relpath(src_file, src))
                    else:
                        skipped.append(os.path.relpath(src_file, src))
                except Exception:
                    pass
        if delete_orphans:
            for root, dirs, files in os.walk(dst):
                rel_root = os.path.relpath(root, dst)
                for f in files:
                    src_file = os.path.join(src, rel_root, f)
                    if not os.path.exists(src_file):
                        os_file = os.path.join(root, f)
                        try:
                            os.remove(os_file)
                            deleted.append(os.path.relpath(os_file, dst))
                        except Exception:
                            pass
        return json.dumps({"success": True, "copied": len(copied), "skipped": len(skipped), "deleted": len(deleted), "copied_files": copied[:CONST_50], "deleted_files": deleted[:CONST_50]})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def mirror_folder(args):
    folder_a = args["folder_a"]
    folder_b = args["folder_b"]
    dry_run = args.get("dry_run", True)
    try:
        a = os.path.abspath(folder_a)
        b = os.path.abspath(folder_b)
        if not os.path.exists(a):
            return json.dumps({"error": f"Directory not found: {folder_a}", "success": False})
        os.makedirs(b, exist_ok=True)
        a_to_b, b_to_a = [], []
        def _sync(src, dst, direction):
            changes = []
            os.makedirs(dst, exist_ok=True)
            for root, dirs, files in os.walk(src):
                rel_root = os.path.relpath(root, src)
                for f in files:
                    src_file = os.path.join(root, f)
                    dst_file = os.path.join(dst, rel_root, f)
                    os.makedirs(os.path.dirname(dst_file), exist_ok=True)
                    src_mtime = os.path.getmtime(src_file)
                    if not os.path.exists(dst_file) or src_mtime > os.path.getmtime(dst_file):
                        if not dry_run:
                            shutil.copy2(src_file, dst_file)
                        changes.append(os.path.relpath(src_file, src))
            return changes
        a_to_b = _sync(a, b, "a->b")
        b_to_a = _sync(b, a, "b->a") if os.path.exists(b) else []
        return json.dumps({"success": True, "a_to_b": a_to_b, "b_to_a": b_to_a, "dry_run": dry_run})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def compress_files(args):
    path = args["path"]
    output = args["output"]
    fmt = args.get("format", "zip")
    try:
        target = os.path.abspath(path)
        if not os.path.exists(target):
            return json.dumps({"error": f"Path not found: {path}", "success": False})
        out = os.path.abspath(output)
        if fmt == "zip":
            import zipfile
            with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as zf:
                if os.path.isfile(target):
                    zf.write(target, os.path.basename(target))
                else:
                    for root, dirs, files in os.walk(target):
                        for f in files:
                            fp = os.path.join(root, f)
                            arcname = os.path.relpath(fp, os.path.dirname(target))
                            zf.write(fp, arcname)
        elif fmt in ("tar", "tar.gz"):
            import tarfile
            mode = "w:gz" if fmt == "tar.gz" else "w"
            with tarfile.open(out, mode) as tf:
                if os.path.isfile(target):
                    tf.add(target, os.path.basename(target))
                else:
                    tf.add(target, arcname=os.path.basename(target))
        size = os.path.getsize(out)
        return json.dumps({"success": True, "archive": out, "format": fmt, "size_mb": round(size / CONST_1024 / CONST_1024, 2)})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def extract_archive(args):
    archive = args["archive"]
    dest = args["dest"]
    password = args.get("password", "")
    try:
        arc = os.path.abspath(archive)
        if not os.path.exists(arc):
            return json.dumps({"error": f"Archive not found: {archive}", "success": False})
        dst = os.path.abspath(dest)
        os.makedirs(dst, exist_ok=True)
        extracted = []
        if arc.endswith(".zip"):
            import zipfile
            with zipfile.ZipFile(arc, 'r') as zf:
                if password:
                    zf.setpassword(password.encode())
                zf.extractall(dst)
                extracted = zf.namelist()
        elif arc.endswith((".tar.gz", ".tgz")):
            import tarfile
            with tarfile.open(arc, "r:gz") as tf:
                tf.extractall(dst)
                extracted = [m.name for m in tf.getmembers()]
        elif arc.endswith(".tar"):
            import tarfile
            with tarfile.open(arc, "r") as tf:
                tf.extractall(dst)
                extracted = [m.name for m in tf.getmembers()]
        else:
            return json.dumps({"error": f"Unsupported format: {arc}", "success": False})
        return json.dumps({"success": True, "extracted": len(extracted), "files": extracted[:100], "destination": dst})
    except Exception as e:
        return json.dumps({"error": str(e)})

functions = {
    "schedule_task": schedule_task,
    "watch_file": watch_file,
    "watch_directory": watch_directory,
    "batch_rename": batch_rename,
    "batch_convert": batch_convert,
    "auto_cleanup": auto_cleanup,
    "sync_folder": sync_folder,
    "mirror_folder": mirror_folder,
    "compress_files": compress_files,
    "extract_archive": extract_archive,
}
