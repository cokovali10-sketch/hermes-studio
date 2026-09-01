"""Project-aware plugin loading — detect project type and auto-load relevant plugins."""
from __future__ import annotations

import pathlib

from hermes.core import WORKSPACE_DIR
from hermes.bus import bus


PROJECT_INDICATORS = {
    "python-fastapi": ["requirements.txt", "pyproject.toml", "main.py", "app.py"],
    "django": ["manage.py", "settings.py", "wsgi.py"],
    "python-package": ["setup.py", "setup.cfg", "pyproject.toml"],
    "react-ts": ["package.json", "tsconfig.json", "src"],
    "node-express": ["package.json", "server.js", "app.js"],
    "vanilla-js": ["index.html", "script.js"],
    "go": ["go.mod", "main.go"],
    "rust": ["Cargo.toml", "src"],
    "docker": ["Dockerfile", "docker-compose.yml"],
}

LANGUAGE_INDICATORS = {
    "python": [".py", "requirements.txt", "pyproject.toml"],
    "javascript": [".js", ".jsx", "package.json"],
    "typescript": [".ts", ".tsx", "tsconfig.json"],
    "go": [".go", "go.mod"],
    "rust": [".rs", "Cargo.toml"],
}


def detect_project_type(project_path: str | pathlib.Path | None = None) -> list[str]:
    root = pathlib.Path(project_path) if project_path else WORKSPACE_DIR
    if not root.exists():
        return []

    detected = []
    for ptype, indicators in PROJECT_INDICATORS.items():
        score = 0
        for indicator in indicators:
            if (root / indicator).exists():
                score += 1
        if score >= 2:
            detected.append(ptype)
        elif score == 1 and len(indicators) <= 3:
            detected.append(ptype)

    if not detected:
        py_count = len(list(root.rglob("*.py")))
        js_count = len(list(root.rglob("*.js"))) + len(list(root.rglob("*.ts")))
        if py_count > js_count and py_count > 0:
            detected.append("python-package")
        elif js_count > 0:
            detected.append("node-express")

    return list(dict.fromkeys(detected))


def get_relevant_plugins(project_type: list[str]) -> list[dict]:
    from hermes.modules.smart_plugins.registry import MARKETPLACE_PLUGINS
    relevant = []
    for name, manifest in MARKETPLACE_PLUGINS.items():
        manifest_types = manifest.get("project_types", [])
        if any(pt in manifest_types for pt in project_type):
            relevant.append({
                "name": name,
                "version": manifest["version"],
                "description": manifest["description"],
                "match_reason": f"project type: {[pt for pt in project_type if pt in manifest_types]}",
            })
    return relevant


def auto_load_plugins(project_path: str | pathlib.Path | None = None) -> dict:
    from hermes.modules.smart_plugins.registry import plugin_registry

    project_types = detect_project_type(project_path)
    relevant = get_relevant_plugins(project_types)

    loaded = []
    for plugin in relevant:
        if not plugin_registry._is_installed(plugin["name"]):
            result = plugin_registry.install_plugin(plugin["name"])
            if result.get("success"):
                loaded.append(plugin["name"])

    bus.emit("plugins.auto_loaded", {
        "project_types": project_types,
        "relevant_count": len(relevant),
        "loaded_count": len(loaded),
    })

    return {
        "success": True,
        "project_types": project_types,
        "relevant_plugins": relevant,
        "auto_loaded": loaded,
    }
