"""API endpoint discovery for Python and JS frameworks."""
import pathlib
import re
from typing import Any
# --- константы вынесены FORGE refactor ---
CONST_5 = 5


IGNORE_DIRS = {
    "node_modules", ".git", "__pycache__", "dist", "build", ".next",
    "venv", ".venv",
}


def discover_api_endpoints(path: str) -> list[dict[str, Any]]:
    root = pathlib.Path(path)
    if not root.exists():
        return []

    endpoints = []

    for fpath in root.rglob("*"):
        if not fpath.is_file():
            continue
        if any(part in IGNORE_DIRS for part in fpath.relative_to(root).parts):
            continue

        ext = fpath.suffix.lower()
        if ext not in (".py", ".js", ".ts", ".tsx", ".jsx", ".mjs", ".cjs"):
            continue

        try:
            content = fpath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        rel = str(fpath.relative_to(root)).replace("\\", "/")

        if ext == ".py":
            py_endpoints = _find_python_endpoints(content, rel)
            endpoints.extend(py_endpoints)
        else:
            js_endpoints = _find_js_endpoints(content, rel)
            endpoints.extend(js_endpoints)

    return endpoints


def _find_python_endpoints(content: str, file_path: str) -> list[dict[str, Any]]:
    endpoints = []
    lines = content.splitlines()

    patterns = [
        (r'@(?:app|router|api)\.(get|post|put|patch|delete|head|options)\s*\(\s*[\'"]([^\'"]+)[\'"]', "flask_fastapi"),
        (r'@(?:app|router|api)\.route\s*\(\s*[\'"]([^\'"]+)[\'"]', "flask_route"),
        (r'@(?:app|router|api)\.(get|post|put|patch|delete)\s*\(\s*[\'"]([^\'"]+)[\'"]\s*(?:,\s*methods\s*=\s*\[([^\]]+)\])?', "fastapi_method"),
    ]

    for i, line in enumerate(lines):
        for pattern, framework in patterns:
            for m in re.finditer(pattern, line, re.IGNORECASE):
                groups = m.groups()
                if framework == "flask_route":
                    route_path = groups[0]
                    method = "GET"
                else:
                    method = groups[0].upper() if groups[0] else "GET"
                    route_path = groups[1] if len(groups) > 1 else groups[0]

                handler = _find_handler_function(lines, i)

                endpoints.append({
                    "method": method,
                    "path": route_path,
                    "handler": handler,
                    "file": file_path,
                    "line": i + 1,
                    "framework": "flask" if "flask" in content.lower() else "fastapi",
                })

    return endpoints


def _find_js_endpoints(content: str, file_path: str) -> list[dict[str, Any]]:
    endpoints = []
    lines = content.splitlines()

    patterns = [
        (r'(?:app|router|server|api)\.(get|post|put|patch|delete|head|options|all)\s*\(\s*[\'"]([^\'"]+)[\'"]', "express"),
        (r'(?:app|router)\.route\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)\.(get|post|put|patch|delete)', "express_route"),
    ]

    for i, line in enumerate(lines):
        for pattern, framework in patterns:
            for m in re.finditer(pattern, line, re.IGNORECASE):
                groups = m.groups()
                if framework == "express_route":
                    route_path = groups[0]
                    method = groups[1].upper()
                else:
                    method = groups[0].upper()
                    route_path = groups[1]

                handler = _find_js_handler(lines, i)

                endpoints.append({
                    "method": method,
                    "path": route_path,
                    "handler": handler,
                    "file": file_path,
                    "line": i + 1,
                    "framework": "express",
                })

    return endpoints


def _find_handler_function(lines: list[str], decorator_line: int) -> str:
    for i in range(decorator_line + 1, min(decorator_line + CONST_5, len(lines))):
        m = re.search(r'(?:async\s+)?def\s+(\w+)', lines[i])
        if m:
            return m.group(1)
    return "unknown"


def _find_js_handler(lines: list[str], route_line: int) -> str:
    for i in range(route_line, min(route_line + CONST_5, len(lines))):
        m = re.search(r'(?:async\s+)?(?:function\s+(\w+)|(\w+)\s*(?:=\s*(?:async\s+)?(?:function|\([^)]*\)\s*=>)))', lines[i])
        if m:
            return m.group(1) or m.group(2) or "unknown"
    return "unknown"
