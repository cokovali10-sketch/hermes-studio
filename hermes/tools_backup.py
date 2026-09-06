"""Backup and sync tools for Hermes agent."""
import asyncio
import json
import os
import shutil
import time

TOOLS = [
    {"name": "backup_directory", "description": "Create a compressed backup of a directory", "parameters": {"type": "object", "properties": {"source": {"type": "string"}, "dest": {"type": "string"}, "exclude": {"type": "array", "items": {"type": "string"}}}, "required": ["source", "dest"]}},
    {"name": "restore_backup", "description": "Restore a backup", "parameters": {"type": "object", "properties": {"backup_path": {"type": "string"}, "dest": {"type": "string"}}, "required": ["backup_path", "dest"]}},
    {"name": "list_backups", "description": "List available backups", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Backup directory"}}}},
    {"name": "sync_directories", "description": "Sync two directories (one-way)", "parameters": {"type": "object", "properties": {"source": {"type": "string"}, "dest": {"type": "string"}}, "required": ["source", "dest"]}},
    {"name": "cleanup_old_files", "description": "Delete files older than N days", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "days": {"type": "integer"}, "pattern": {"type": "string", "description": "File pattern (e.g. *.log)"}}, "required": ["path", "days"]}},
    {"name": "find_duplicates", "description": "Find duplicate files by hash", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}},
]

functions = {}

async def backup_directory(args):
    source = args["source"]
    dest = args["dest"]
    exclude = set(args.get("exclude", [".git", "node_modules", "__pycache__", ".venv"]))
    ts = time.strftime("%Y%m%d_%H%M%S")
    backup_name = f"backup_{os.path.basename(source)}_{ts}"
    backup_path = os.path.join(dest, backup_name)
    try:
        def ignore_func(directory, files):
            return [f for f in files if f in exclude or f.startswith('.')]
        shutil.copytree(source, backup_path, ignore=ignore_func)
        size = sum(os.path.getsize(os.path.join(dp, f)) for dp, dn, fn in os.walk(backup_path) for f in fn)
        return json.dumps({"success": True, "path": backup_path, "size_bytes": size, "size_mb": round(size / 1024 / 1024, 2)})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def restore_backup(args):
    backup_path = args["backup_path"]
    dest = args["dest"]
    try:
        if os.path.exists(dest):
            shutil.rmtree(dest)
        shutil.copytree(backup_path, dest)
        return json.dumps({"success": True, "restored_to": dest})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def list_backups(args):
    path = args.get("path", ".")
    backups = []
    try:
        for item in os.listdir(path):
            if item.startswith("backup_"):
                full = os.path.join(path, item)
                if os.path.isdir(full):
                    size = sum(os.path.getsize(os.path.join(dp, f)) for dp, dn, fn in os.walk(full) for f in fn)
                    backups.append({"name": item, "path": full, "size_mb": round(size / 1024 / 1024, 2), "modified": os.path.getmtime(full)})
    except Exception as e:
        return json.dumps({"error": str(e)})
    backups.sort(key=lambda x: x["modified"], reverse=True)
    return json.dumps({"backups": backups, "count": len(backups)})

async def sync_directories(args):
    source = args["source"]
    dest = args["dest"]
    copied, updated, deleted = 0, 0, 0
    for root, dirs, files in os.walk(source):
        dirs[:] = [d for d in dirs if d not in {'.git', 'node_modules'}]
        rel = os.path.relpath(root, source)
        dest_dir = os.path.join(dest, rel)
        os.makedirs(dest_dir, exist_ok=True)
        for fname in files:
            src_file = os.path.join(root, fname)
            dst_file = os.path.join(dest_dir, fname)
            if not os.path.exists(dst_file) or os.path.getmtime(src_file) > os.path.getmtime(dst_file):
                shutil.copy2(src_file, dst_file)
                if os.path.exists(dst_file):
                    updated += 1
                else:
                    copied += 1
    return json.dumps({"success": True, "copied": copied, "updated": updated})

async def cleanup_old_files(args):
    path = args["path"]
    days = args["days"]
    pattern = args.get("pattern", "*")
    cutoff = time.time() - (days * 86400)
    deleted = []
    import glob
    for fpath in glob.glob(os.path.join(path, "**", pattern), recursive=True):
        try:
            if os.path.getmtime(fpath) < cutoff:
                os.remove(fpath)
                deleted.append(fpath)
        except Exception:
            continue
    return json.dumps({"deleted": len(deleted), "files": deleted[:100]})

async def find_duplicates(args):
    path = args.get("path", ".")
    hash_map = {}
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in {'.git', 'node_modules'}]
        for fname in files:
            fpath = os.path.join(root, fname)
            try:
                import hashlib
                h = hashlib.md5(open(fpath, 'rb').read()).hexdigest()
                hash_map.setdefault(h, []).append(fpath)
            except Exception:
                continue
    duplicates = {h: files for h, files in hash_map.items() if len(files) > 1}
    return json.dumps({"duplicates": duplicates, "groups": len(duplicates), "total_duplicates": sum(len(f) - 1 for f in duplicates.values())})

functions = {
    "backup_directory": backup_directory, "restore_backup": restore_backup,
    "list_backups": list_backups, "sync_directories": sync_directories,
    "cleanup_old_files": cleanup_old_files, "find_duplicates": find_duplicates,
}
