"""Plugin registry — marketplace listing, installation, manifest management."""
from __future__ import annotations

import json
import pathlib
import shutil

from hermes.core import PLUGINS_DIR, ROOT
from hermes.bus import bus

MANIFEST_FILE = "hermes.plugin.json"
INSTALLED_DIR = PLUGINS_DIR / "installed"

"""Marketplace plugins (built-in definitions)."""
MARKETPLACE_PLUGINS = {
    "python_linter": {
        "name": "python_linter",
        "version": "1.0.0",
        "description": "Python linting and formatting with ruff",
        "languages": ["python"],
        "project_types": ["python-fastapi", "django", "python-package"],
        "tools": ["lint_python", "format_python"],
        "commands": {
            "lint_python": "ruff check {path}",
            "format_python": "ruff format {path}",
        },
    },
    "js_linter": {
        "name": "js_linter",
        "version": "1.0.0",
        "description": "JavaScript/TypeScript linting with ESLint",
        "languages": ["javascript", "typescript"],
        "project_types": ["react-ts", "node-express", "vanilla-js"],
        "tools": ["lint_js", "format_js"],
        "commands": {
            "lint_js": "npx eslint {path}",
            "format_js": "npx prettier --write {path}",
        },
    },
    "python_tester": {
        "name": "python_tester",
        "version": "1.0.0",
        "description": "Python test runner with pytest",
        "languages": ["python"],
        "project_types": ["python-fastapi", "django", "python-package"],
        "tools": ["test_python"],
        "commands": {
            "test_python": "python -m pytest {path} -v",
        },
    },
    "docker_builder": {
        "name": "docker_builder",
        "version": "1.0.0",
        "description": "Docker image builder and validator",
        "languages": ["python", "javascript", "go"],
        "project_types": ["docker", "containerized"],
        "tools": ["build_docker", "validate_dockerfile"],
        "commands": {
            "build_docker": "docker build -t {tag} .",
            "validate_dockerfile": "docker build --check .",
        },
    },
    "api_tester": {
        "name": "api_tester",
        "version": "1.0.0",
        "description": "API endpoint testing with curl/httpie",
        "languages": ["python", "javascript"],
        "project_types": ["python-fastapi", "node-express", "django"],
        "tools": ["test_api_endpoint"],
        "commands": {
            "test_api_endpoint": "curl -s -o /dev/null -w '%{{http_code}}' {url}",
        },
    },
}


class PluginRegistry:
    def __init__(self):
        INSTALLED_DIR.mkdir(parents=True, exist_ok=True)

    def list_available(self) -> list[dict]:
        plugins = []
        for name, manifest in MARKETPLACE_PLUGINS.items():
            plugins.append({
                "name": name,
                "version": manifest["version"],
                "description": manifest["description"],
                "installed": self._is_installed(name),
            })
        return plugins

    def get_manifest(self, name: str) -> dict | None:
        return MARKETPLACE_PLUGINS.get(name)

    def install_plugin(self, name: str) -> dict:
        manifest = MARKETPLACE_PLUGINS.get(name)
        if not manifest:
            return {"success": False, "error": f"Plugin not found: {name}"}

        if self._is_installed(name):
            return {"success": True, "message": f"Plugin already installed: {name}"}

        plugin_dir = INSTALLED_DIR / name
        plugin_dir.mkdir(parents=True, exist_ok=True)

        manifest_path = plugin_dir / MANIFEST_FILE
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        tool_defs = manifest.get("tools", [])
        commands = manifest.get("commands", {})
        plugin_code = self._generate_plugin_code(name, tool_defs, commands)
        plugin_file = plugin_dir / f"{name}.py"
        plugin_file.write_text(plugin_code, encoding="utf-8")

        bus.emit("plugin.installed", {"name": name, "version": manifest["version"]})
        return {"success": True, "name": name, "tools": tool_defs}

    def uninstall_plugin(self, name: str) -> dict:
        plugin_dir = INSTALLED_DIR / name
        if not plugin_dir.exists():
            return {"success": False, "error": f"Plugin not installed: {name}"}
        shutil.rmtree(plugin_dir)
        bus.emit("plugin.uninstalled", {"name": name})
        return {"success": True, "name": name}

    def list_installed(self) -> list[dict]:
        installed = []
        if not INSTALLED_DIR.exists():
            return installed
        for d in INSTALLED_DIR.iterdir():
            if d.is_dir():
                manifest_path = d / MANIFEST_FILE
                if manifest_path.exists():
                    try:
                        m = json.loads(manifest_path.read_text(encoding="utf-8"))
                        installed.append({"name": m["name"], "version": m["version"]})
                    except Exception:
                        pass
        return installed

    def _is_installed(self, name: str) -> bool:
        return (INSTALLED_DIR / name / MANIFEST_FILE).exists()

    def _generate_plugin_code(self, name: str, tools: list[str], commands: dict) -> str:
        lines = [f'"""Auto-generated plugin: {name}"""', ""]
        for tool_name in tools:
            cmd = commands.get(tool_name, f"echo 'No command for {tool_name}'")
            lines.append(f'async def tool_{tool_name}(path: str = ".") -> dict:')
            lines.append(f'    from hermes.tools import tool_execute_shell_command')
            lines.append(f'    command = f"{cmd}"')
            lines.append(f'    r = await tool_execute_shell_command(command=command)')
            lines.append(f'    return {{"success": r.get("success", False), "output": r.get("stdout", ""), "tool": "{tool_name}"}}')
            lines.append("")

        lines.append("HERMES_TOOLS = [")
        for tool_name in tools:
            lines.append(f'    {{"name": "{tool_name}", "function": tool_{tool_name}, "schema": {{"description": "Plugin tool: {tool_name}", "parameters": {{"type": "object", "properties": {{"path": {{"type": "string", "default": "."}}}}, "required": []}}}}}},')
        lines.append("]")
        return "\n".join(lines)


plugin_registry = PluginRegistry()
