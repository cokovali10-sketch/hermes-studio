"""Language-specific plugin loading — auto-detect and load plugins for detected languages."""
from __future__ import annotations

import pathlib

from hermes.core import WORKSPACE_DIR


LANGUAGE_PLUGINS = {
    "python": {
        "plugins": ["python_linter", "python_tester"],
        "file_patterns": ["*.py"],
        "config_files": ["pyproject.toml", "setup.cfg", ".flake8", "ruff.toml"],
    },
    "javascript": {
        "plugins": ["js_linter"],
        "file_patterns": ["*.js", "*.jsx"],
        "config_files": [".eslintrc*", ".prettierrc*", "package.json"],
    },
    "typescript": {
        "plugins": ["js_linter"],
        "file_patterns": ["*.ts", "*.tsx"],
        "config_files": ["tsconfig.json", ".eslintrc*", ".prettierrc*"],
    },
    "go": {
        "plugins": [],
        "file_patterns": ["*.go"],
        "config_files": ["go.mod", ".golangci.yml"],
    },
    "rust": {
        "plugins": [],
        "file_patterns": ["*.rs"],
        "config_files": ["Cargo.toml", "rustfmt.toml"],
    },
}


def detect_languages(project_path: str | pathlib.Path | None = None) -> list[str]:
    root = pathlib.Path(project_path) if project_path else WORKSPACE_DIR
    if not root.exists():
        return []

    lang_counts: dict[str, int] = {}
    for lang, info in LANGUAGE_PLUGINS.items():
        count = 0
        for pattern in info["file_patterns"]:
            count += len(list(root.rglob(pattern)))
        if count > 0:
            lang_counts[lang] = count

    return sorted(lang_counts, key=lambda k: lang_counts[k], reverse=True)


def get_language_plugins(languages: list[str]) -> list[dict]:
    plugins = []
    seen = set()
    for lang in languages:
        lang_info = LANGUAGE_PLUGINS.get(lang, {})
        for plugin_name in lang_info.get("plugins", []):
            if plugin_name not in seen:
                seen.add(plugin_name)
                plugins.append({
                    "name": plugin_name,
                    "language": lang,
                    "reason": f"Detected {lang} project",
                })
    return plugins


def auto_load_language_plugins(project_path: str | pathlib.Path | None = None) -> dict:
    from hermes.modules.smart_plugins.registry import plugin_registry

    languages = detect_languages(project_path)
    plugins = get_language_plugins(languages)

    loaded = []
    for plugin in plugins:
        if not plugin_registry._is_installed(plugin["name"]):
            result = plugin_registry.install_plugin(plugin["name"])
            if result.get("success"):
                loaded.append(plugin["name"])

    return {
        "success": True,
        "languages_detected": languages,
        "plugins_found": plugins,
        "auto_loaded": loaded,
    }
