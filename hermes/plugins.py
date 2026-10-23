"""Plugin system — custom tools from Python files."""
import importlib.util

from aiohttp import web

from hermes.core import PLUGINS_DIR
from hermes.tools import TOOL_MAP, TOOLS_SCHEMA

_loaded_plugins = {}


def _load_plugins():
    """Scan plugins/ directory for Python files with tool definitions."""
    for py_file in PLUGINS_DIR.glob("*.py"):
        if py_file.name.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"hermes_plugin_{py_file.stem}", str(py_file))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            if hasattr(mod, "HERMES_TOOLS"):
                for tool_def in mod.HERMES_TOOLS:
                    name = tool_def["name"]
                    func = tool_def["function"]
                    schema = tool_def["schema"]
                    TOOLS_SCHEMA.append({
                        "type": "function",
                        "function": {
                            "name": name,
                            "description": schema.get("description", ""),
                            "parameters": schema.get("parameters", {"type": "object", "properties": {}}),
                        }
                    })
                    TOOL_MAP[name] = func
                    _loaded_plugins[name] = {"file": py_file.name, "schema": schema}
                    print(f"  [Plugin] Loaded: {name} from {py_file.name}")

            if hasattr(mod, "HERMES_INIT"):
                mod.HERMES_INIT()

        except Exception as e:
            print(f"  [Plugin] Failed to load {py_file.name}: {e}")


def _reload_plugins():
    """Reload all plugins."""
    global _loaded_plugins
    _loaded_plugins = {}
    to_remove = [k for k in TOOL_MAP if k not in [
        "workspace_file_ops", "execute_shell_command", "git_checkpoint",
        "analyze_project_structure", "capture_screenshot", "read_image",
        "search_code", "run_python", "fetch_url", "diff_apply",
        "kill_process", "env_info", "list_templates", "scaffold_project",
        "done",
    ]]
    for k in to_remove:
        del TOOL_MAP[k]
    for t in TOOLS_SCHEMA[:]:
        if t["function"]["name"] in to_remove:
            TOOLS_SCHEMA.remove(t)
    _load_plugins()


def register_plugin_tool(name: str, func, schema: dict):
    """Register a plugin tool. Plugin tools go through safety_check like built-in tools."""
    from hermes.tools import register_plugin_tool as _builtin_register
    _builtin_register(name, func, schema)
    _loaded_plugins[name] = {"file": "manual", "schema": schema}


async def plugins_handler(request):
    """List loaded plugins."""
    return web.json_response({
        "plugins": _loaded_plugins,
        "total": len(_loaded_plugins),
        "directory": str(PLUGINS_DIR),
    })


async def reload_plugins_handler(request):
    """Reload all plugins."""
    try:
        _reload_plugins()
        return web.json_response({
            "success": True,
            "plugins": _loaded_plugins,
            "total_tools": len(TOOL_MAP),
        })
    except Exception as e:
        return web.json_response({"error": str(e), "success": False}, status=500)
