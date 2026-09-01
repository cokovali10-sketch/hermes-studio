"""Project structure scanner for memory and context."""
import json
import pathlib
import re
import time

from hermes.modules.memory_store import project_id_from_path

IGNORE_DIRS = {
    "node_modules", ".git", "__pycache__", "dist", "build", ".next",
    "venv", ".venv", ".mypy_cache", ".pytest_cache", "target", "vendor",
}

EXTENSION_LANGUAGES = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript",
    ".jsx": "JavaScript", ".rs": "Rust", ".go": "Go", ".java": "Java",
    ".rb": "Ruby", ".php": "PHP", ".cs": "C#", ".cpp": "C++", ".c": "C",
    ".h": "C/C++", ".hpp": "C++", ".swift": "Swift", ".kt": "Kotlin",
    ".scala": "Scala", ".r": "R", ".R": "R", ".lua": "Lua", ".dart": "Dart",
    ".vue": "Vue", ".svelte": "Svelte", ".html": "HTML", ".css": "CSS",
    ".scss": "SCSS", ".less": "LESS", ".json": "JSON", ".yaml": "YAML",
    ".yml": "YAML", ".toml": "TOML", ".xml": "XML", ".sql": "SQL",
    ".sh": "Shell", ".bash": "Shell", ".ps1": "PowerShell",
}

SOURCE_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go", ".java", ".rb"}


def _detect_js_framework(config_path: pathlib.Path) -> str:
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        if "next" in deps:
            return "Next.js"
        if "nuxt" in deps or "@nuxt" in deps:
            return "Nuxt.js"
        if "svelte" in deps:
            return "Svelte"
        if "vue" in deps:
            return "Vue.js"
        if "react" in deps:
            return "React"
        if "angular" in deps or "@angular/core" in deps:
            return "Angular"
        if "express" in deps:
            return "Express"
        if "fastify" in deps:
            return "Fastify"
    except (json.JSONDecodeError, OSError):
        pass
    return "Node.js"


CONFIG_FRAMEWORKS = {
    "package.json": _detect_js_framework,
    "requirements.txt": "Python",
    "setup.py": "Python",
    "pyproject.toml": "Python",
    "Cargo.toml": "Rust",
    "go.mod": "Go",
    "Gemfile": "Ruby",
    "composer.json": "PHP",
    "pom.xml": "Java",
    "build.gradle": "Java",
    "CMakeLists.txt": "C++",
    "Makefile": "C/C++",
    "Pipfile": "Python",
    "poetry.lock": "Python",
    "angular.json": "Angular",
    "svelte.config.js": "Svelte",
    "next.config.js": "Next.js",
    "nuxt.config.ts": "Nuxt.js",
    "vite.config.ts": "Vite",
    "vite.config.js": "Vite",
    "tsconfig.json": "TypeScript",
    "Dockerfile": "Docker",
    "docker-compose.yml": "Docker",
    "docker-compose.yaml": "Docker",
}


def _count_lines(p: pathlib.Path) -> int:
    try:
        return len(p.read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError:
        return 0


def scan_project_structure(path: str) -> dict:
    root = pathlib.Path(path).resolve()
    project_id = project_id_from_path(str(root))

    languages: dict[str, int] = {}
    frameworks: set[str] = set()
    dependencies: list[str] = []
    file_index: list[dict] = []
    total_files = 0
    total_dirs = 0
    total_size = 0

    for item in root.rglob("*"):
        if any(part in IGNORE_DIRS for part in item.relative_to(root).parts):
            continue

        if item.is_dir():
            total_dirs += 1
            continue

        total_files += 1
        try:
            size = item.stat().st_size
        except OSError:
            size = 0
        total_size += size
        ext = item.suffix.lower()
        rel = item.relative_to(root).as_posix()

        lang = EXTENSION_LANGUAGES.get(ext)
        if lang:
            languages[lang] = languages.get(lang, 0) + 1

        if item.name in CONFIG_FRAMEWORKS and item.parent == root:
            fw = CONFIG_FRAMEWORKS[item.name]
            if callable(fw):
                frameworks.add(fw(item))
            else:
                frameworks.add(fw)

        if item.name == "package.json" and item.parent == root:
            try:
                data = json.loads(item.read_text(encoding="utf-8"))
                for key in ("dependencies", "devDependencies"):
                    for dep_name in data.get(key, {}):
                        dependencies.append(dep_name)
            except (json.JSONDecodeError, OSError):
                pass

        if item.name == "requirements.txt" and item.parent == root:
            try:
                for line in item.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and not line.startswith("-"):
                        dependencies.append(re.split(r"[>=<!\[]", line)[0])
            except OSError:
                pass

        if item.name == "Cargo.toml" and item.parent == root:
            try:
                content = item.read_text(encoding="utf-8")
                for m in re.finditer(r'^(\w[\w-]*)\s*=\s*["\{]', content, re.MULTILINE):
                    dependencies.append(m.group(1))
            except OSError:
                pass

        if len(file_index) < 200:
            line_count = _count_lines(item) if ext in SOURCE_EXTENSIONS else 0
            file_index.append({
                "path": rel,
                "ext": ext,
                "size": size,
                "lines": line_count,
                "lang": lang or "",
            })

    return {
        "project_id": project_id,
        "name": root.name,
        "path": str(root),
        "languages": sorted(languages.keys()),
        "language_counts": languages,
        "frameworks": sorted(frameworks),
        "dependencies": sorted(set(dependencies)),
        "file_index": file_index,
        "stats": {
            "total_files": total_files,
            "total_dirs": total_dirs,
            "total_size": total_size,
        },
        "scanned_at": time.time(),
    }
