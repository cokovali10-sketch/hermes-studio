"""Dependency graph builder for projects."""
import pathlib
import re
from typing import Any

IGNORE_DIRS = {
    "node_modules", ".git", "__pycache__", "dist", "build", ".next",
    "venv", ".venv",
}


class DependencyGraph:
    def __init__(self):
        self.nodes: dict[str, dict] = {}
        self.edges: list[dict] = []

    def build_graph(self, path: str) -> dict[str, Any]:
        root = pathlib.Path(path)
        if not root.exists():
            return {"error": f"Path not found: {path}"}

        self.nodes = {}
        self.edges = []

        for fpath in root.rglob("*"):
            if not fpath.is_file():
                continue
            if any(part in IGNORE_DIRS for part in fpath.relative_to(root).parts):
                continue

            rel = str(fpath.relative_to(root)).replace("\\", "/")
            ext = fpath.suffix.lower()

            self.nodes[rel] = {
                "path": rel,
                "extension": ext,
                "size": fpath.stat().st_size if fpath.exists() else 0,
            }

        for node_path in list(self.nodes.keys()):
            fpath = root / node_path
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            imports = self._extract_imports(content, fpath.suffix.lower())
            for imp in imports:
                resolved = self._resolve_import(imp, fpath, root)
                if resolved and resolved in self.nodes:
                    self.edges.append({
                        "from": node_path,
                        "to": resolved,
                        "import": imp,
                    })

        return {
            "nodes": list(self.nodes.values()),
            "edges": self.edges,
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
        }

    def _extract_imports(self, content: str, ext: str) -> list[str]:
        imports = []

        if ext == ".py":
            for m in re.finditer(r'^import\s+([\w.]+)', content, re.MULTILINE):
                imports.append(m.group(1))
            for m in re.finditer(r'^from\s+([\w.]+)\s+import', content, re.MULTILINE):
                imports.append(m.group(1))

        elif ext in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"):
            for m in re.finditer(r'import\s+.*?from\s+[\'"]([^\'"]+)[\'"]', content, re.MULTILINE):
                imports.append(m.group(1))
            for m in re.finditer(r'import\s+[\'"]([^\'"]+)[\'"]', content, re.MULTILINE):
                imports.append(m.group(1))
            for m in re.finditer(r'require\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)', content, re.MULTILINE):
                imports.append(m.group(1))

        return imports

    def _resolve_import(self, imp: str, from_file: pathlib.Path, root: pathlib.Path) -> str | None:
        if imp.startswith("."):
            resolved = (from_file.parent / imp).resolve()
            for ext in ("", ".py", ".js", ".ts", ".tsx", ".jsx", ".mjs", ".cjs", "/index.js", "/index.ts", "/index.py"):
                candidate = resolved.with_suffix("") if ext else resolved
                if ext.startswith("/"):
                    candidate = resolved / ext[1:]
                elif ext:
                    candidate = resolved.with_suffix(ext)
                try:
                    rel = str(candidate.relative_to(root)).replace("\\", "/")
                    if rel in self.nodes:
                        return rel
                except ValueError:
                    pass

        elif imp.startswith("@") or "/" not in imp:
            return None

        else:
            for ext in ("", ".js", ".ts", ".tsx", ".jsx", ".py", ".json", "/index.js", "/index.ts"):
                candidate = root / (imp + ext)
                if candidate.exists():
                    try:
                        return str(candidate.relative_to(root)).replace("\\", "/")
                    except ValueError:
                        pass

        return None

    def get_dependents(self, file_path: str) -> list[str]:
        return [e["from"] for e in self.edges if e["to"] == file_path]

    def get_dependencies(self, file_path: str) -> list[str]:
        return [e["to"] for e in self.edges if e["from"] == file_path]

    def get_isolated_files(self) -> list[str]:
        connected = set()
        for e in self.edges:
            connected.add(e["from"])
            connected.add(e["to"])
        return [n for n in self.nodes if n not in connected]


dep_graph = DependencyGraph()
