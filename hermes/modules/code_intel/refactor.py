"""Refactoring operations — rename, extract, find definitions/references."""
import pathlib
import re
import shutil
import time
from typing import Any

from hermes.core import WORKSPACE_DIR, BACKUP_DIR
# --- константы вынесены FORGE refactor ---
CONST_200 = 200


IGNORE_DIRS = {
    "node_modules", ".git", "__pycache__", "dist", "build", ".next",
    "venv", ".venv",
}
SOURCE_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx", ".css", ".scss", ".html"}


def _backup_file(target: pathlib.Path):
    ts = time.strftime("%Y%m%d_%H%M%S")
    try:
        rel = target.relative_to(WORKSPACE_DIR)
    except ValueError:
        rel = pathlib.Path(target.name)
    bak = BACKUP_DIR / "refactor" / f"{ts}_{rel.parent}" / target.name
    bak.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target, bak)
    return str(bak)


def _find_source_files(root: pathlib.Path) -> list[pathlib.Path]:
    files = []
    for fpath in root.rglob("*"):
        if not fpath.is_file():
            continue
        if any(part in IGNORE_DIRS for part in fpath.relative_to(root).parts):
            continue
        if fpath.suffix.lower() in SOURCE_EXTENSIONS:
            files.append(fpath)
    return files


def rename_symbol(path: str, old_name: str, new_name: str) -> list[dict[str, Any]]:
    root = pathlib.Path(path)
    if not root.exists():
        return [{"error": f"Path not found: {path}"}]

    if root.is_file():
        files = [root]
    else:
        files = _find_source_files(root)

    changes = []
    for fpath in files:
        try:
            content = fpath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        ext = fpath.suffix.lower()
        patterns = _get_rename_patterns(old_name, ext)
        new_content = content
        file_changes = []

        for pattern in patterns:
            matches = list(re.finditer(pattern, content, re.MULTILINE))
            for m in reversed(matches):
                line_num = content[:m.start()].count("\n") + 1
                old_text = m.group(0)
                new_text = re.sub(
                    r'\b' + re.escape(old_name) + r'\b',
                    new_name,
                    old_text,
                )
                if old_text != new_text:
                    new_content = new_content[:m.start()] + new_text + new_content[m.end():]
                    file_changes.append({
                        "file": str(fpath.relative_to(WORKSPACE_DIR)) if fpath.is_relative_to(WORKSPACE_DIR) else str(fpath),
                        "line": line_num,
                        "old": old_text[:100],
                        "new": new_text[:100],
                    })

        if file_changes:
            backup = _backup_file(fpath)
            fpath.write_text(new_content, encoding="utf-8")
            changes.append({
                "file": str(fpath.relative_to(WORKSPACE_DIR)) if fpath.is_relative_to(WORKSPACE_DIR) else str(fpath),
                "changes": file_changes,
                "backup": backup,
            })

    return changes


def _get_rename_patterns(name: str, ext: str) -> list[str]:
    escaped = re.escape(name)
    patterns = [r'\b' + escaped + r'\b']
    return patterns


def extract_function(path: str, start_line: int, end_line: int, func_name: str) -> dict[str, Any]:
    target = pathlib.Path(path)
    if not target.exists():
        return {"error": f"File not found: {path}"}

    try:
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    except Exception as e:
        return {"error": f"Cannot read file: {e}"}

    if start_line < 1 or end_line > len(lines) or start_line > end_line:
        return {"error": f"Invalid line range: {start_line}-{end_line} (file has {len(lines)} lines)"}

    selected = lines[start_line - 1:end_line]
    indent_match = re.match(r'^(\s*)', selected[0])
    base_indent = indent_match.group(1) if indent_match else ""
    code_indent = base_indent + "    "

    dedented = []
    for line in selected:
        stripped = line.lstrip()
        current_indent = line[:len(line) - len(stripped)]
        if current_indent.startswith(base_indent):
            new_indent = code_indent + current_indent[len(base_indent):]
            dedented.append(new_indent + stripped)
        else:
            dedented.append(code_indent + stripped)

    func_body = "\n".join(dedented)
    func_def = f"{base_indent}def {func_name}():\n"
    docstring = f'{code_indent}"""Extracted function."""\n'
    func_code = func_body

    backup = _backup_file(target)

    new_line = f"{base_indent}{func_name}()\n"
    new_lines = lines[:start_line - 1] + [new_line] + lines[end_line:]

    inserted_func = False
    insert_pos = 0
    for i, line in enumerate(new_lines):
        if line.strip() and not line.strip().startswith("#") and not line.strip().startswith('"""'):
            insert_pos = i
            break

    func_block = "\n" + func_def + docstring + func_code + "\n\n"
    new_lines.insert(insert_pos, func_block)

    target.write_text("".join(new_lines), encoding="utf-8")

    return {
        "success": True,
        "file": str(target.relative_to(WORKSPACE_DIR)) if target.is_relative_to(WORKSPACE_DIR) else str(target),
        "extracted_to": func_name,
        "lines_extracted": f"{start_line}-{end_line}",
        "backup": backup,
    }


def find_definitions(name: str, path: str) -> list[dict[str, Any]]:
    root = pathlib.Path(path)
    if not root.exists():
        return [{"error": f"Path not found: {path}"}]

    files = _find_source_files(root)
    results = []

    for fpath in files:
        try:
            content = fpath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        lines = content.splitlines()
        ext = fpath.suffix.lower()

        for i, line in enumerate(lines):
            if _is_definition(line, name, ext):
                rel = str(fpath.relative_to(root)) if fpath.is_relative_to(root) else str(fpath)
                results.append({
                    "file": rel,
                    "line": i + 1,
                    "text": line.strip()[:CONST_200],
                    "type": _get_definition_type(line, ext),
                })

    return results


def _is_definition(line: str, name: str, ext: str) -> bool:
    stripped = line.strip()
    escaped = re.escape(name)

    if ext == ".py":
        patterns = [
            rf'^class\s+{escaped}\b',
            rf'^def\s+{escaped}\b',
            rf'^async\s+def\s+{escaped}\b',
            rf'^{escaped}\s*=',
            rf'^{escaped}\s*:',
        ]
        return any(re.search(p, stripped) for p in patterns)
    elif ext in (".js", ".jsx", ".ts", ".tsx"):
        patterns = [
            rf'^export\s+(?:default\s+)?(?:async\s+)?function\s+{escaped}\b',
            rf'^(?:export\s+)?(?:const|let|var)\s+{escaped}\s*=',
            rf'^export\s+class\s+{escaped}\b',
            rf'^class\s+{escaped}\b',
            rf'^(?:export\s+)?function\s+{escaped}\b',
        ]
        return any(re.search(p, stripped) for p in patterns)
    elif ext == ".css":
        return re.match(rf'^{escaped}\s*\{{', stripped) is not None
    return False


def _get_definition_type(line: str, ext: str) -> str:
    stripped = line.strip()
    if ext == ".py":
        if "class " in stripped:
            return "class"
        if "def " in stripped:
            return "function"
        return "variable"
    elif ext in (".js", ".jsx", ".ts", ".tsx"):
        if "class " in stripped:
            return "class"
        if "function " in stripped:
            return "function"
        if "=>" in stripped:
            return "arrow_function"
        return "variable"
    return "unknown"


def find_references(name: str, path: str) -> list[dict[str, Any]]:
    root = pathlib.Path(path)
    if not root.exists():
        return [{"error": f"Path not found: {path}"}]

    files = _find_source_files(root)
    results = []
    pattern = re.compile(r'\b' + re.escape(name) + r'\b')

    for fpath in files:
        try:
            content = fpath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        lines = content.splitlines()
        ext = fpath.suffix.lower()

        for i, line in enumerate(lines):
            if pattern.search(line):
                if not _is_definition(line, name, ext):
                    rel = str(fpath.relative_to(root)) if fpath.is_relative_to(root) else str(fpath)
                    results.append({
                        "file": rel,
                        "line": i + 1,
                        "text": line.strip()[:CONST_200],
                    })

    return results
