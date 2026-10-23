"""Explorer agent — analyzes project structure and architecture."""
from __future__ import annotations

import re

from hermes.modules.agents.base import BaseAgent
from hermes.modules.agents.message import MessageType
# --- константы вынесены FORGE refactor ---
CONST_4 = 4



class ExplorerAgent(BaseAgent):
    def __init__(self, task: str = "", model: str = "", **kwargs):
        super().__init__(role="explorer", task=task, model=model, **kwargs)

    async def run(self) -> dict:
        from hermes.tools import tool_analyze_project_structure, tool_search_code

        structure = await tool_analyze_project_structure(path=".", max_depth=CONST_4)
        if not structure.get("success"):
            return {"error": structure.get("error", "Failed to analyze project"), "success": False}

        key_files = self._find_key_files(structure.get("tree", []))
        languages = self._detect_languages(structure.get("tree", []))
        arch = self._infer_architecture(key_files, languages)

        result = {
            "success": True,
            "tree": structure.get("tree", []),
            "stats": structure.get("stats", {}),
            "key_files": key_files,
            "languages": languages,
            "architecture": arch,
        }

        self.send_message("coordinator", f"Exploration complete. Found {len(key_files)} key files, languages: {', '.join(languages)}", MessageType.RESULT, result)
        return result

    def _find_key_files(self, tree: list, depth: int = 0) -> list[str]:
        key_patterns = [
            r"package\.json$", r"requirements\.txt$", r"pyproject\.toml$",
            r"Cargo\.toml$", r"go\.mod$", r"Makefile$", r"Dockerfile$",
            r"\.env\.example$", r"README\.md$", r"setup\.py$", r"setup\.cfg$",
            r"tsconfig\.json$", r"vite\.config\.", r"next\.config\.",
            r"main\.(py|js|ts|go|rs)$", r"app\.(py|js|ts)$", r"index\.(js|ts|html)$",
        ]
        found = []
        for node in tree:
            name = node.get("name", "")
            if node["type"] == "file":
                for pat in key_patterns:
                    if re.search(pat, name):
                        found.append(name)
                        break
            elif node["type"] == "dir" and depth < 3:
                found.extend(self._find_key_files(node.get("children", []), depth + 1))
        return found

    def _detect_languages(self, tree: list, depth: int = 0) -> list[str]:
        ext_map = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".jsx": "react", ".tsx": "react-ts", ".go": "go",
            ".rs": "rust", ".java": "java", ".rb": "ruby",
            ".html": "html", ".css": "css", ".scss": "scss",
        }
        counts: dict[str, int] = {}
        for node in tree:
            if node["type"] == "file":
                for ext, lang in ext_map.items():
                    if node.get("name", "").endswith(ext):
                        counts[lang] = counts.get(lang, 0) + 1
            elif node["type"] == "dir" and depth < CONST_4:
                for lang, c in self._count_langs(node.get("children", []), ext_map, depth + 1).items():
                    counts[lang] = counts.get(lang, 0) + c
        return sorted(counts, key=lambda k: counts[k], reverse=True)

    def _count_langs(self, tree: list, ext_map: dict, depth: int) -> dict[str, int]:
        counts: dict[str, int] = {}
        for node in tree:
            if node["type"] == "file":
                for ext, lang in ext_map.items():
                    if node.get("name", "").endswith(ext):
                        counts[lang] = counts.get(lang, 0) + 1
            elif node["type"] == "dir" and depth < CONST_4:
                for lang, c in self._count_langs(node.get("children", []), ext_map, depth + 1).items():
                    counts[lang] = counts.get(lang, 0) + c
        return counts

    def _infer_architecture(self, key_files: list[str], languages: list[str]) -> str:
        if "package.json" in key_files and any(l in ("react", "react-ts") for l in languages):
            return "React/Next.js frontend"
        if "pyproject.toml" in key_files or "setup.py" in key_files:
            return "Python package"
        if "requirements.txt" in key_files:
            return "Python project"
        if "Cargo.toml" in key_files:
            return "Rust project"
        if "go.mod" in key_files:
            return "Go project"
        if "Makefile" in key_files and "Dockerfile" in key_files:
            return "Containerized project"
        if languages and languages[0] in ("javascript", "typescript"):
            return "JavaScript/TypeScript project"
        if languages and languages[0] == "python":
            return "Python project"
        return "Mixed/unknown project"
