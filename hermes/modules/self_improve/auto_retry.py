"""Auto-retry — determine retry strategy based on error type."""
from __future__ import annotations

from hermes.modules.self_improve.pattern_recognizer import recognize_pattern


async def auto_retry(tool_name: str, args: dict, error: str) -> tuple[dict | None, str]:
    matched = recognize_pattern(error)

    if not matched:
        return None, "skip"

    strategy = matched["strategy"]

    if strategy == "install_dependency":
        module = _extract_module_name(error)
        if module:
            return {"command": f"pip install {module}"}, "alternative_approach"
        return None, "skip"

    elif strategy == "fix_syntax":
        return args, "simplify"

    elif strategy == "verify_path":
        if "path" in args:
            path = args["path"]
            return {"action": "list", "path": "."}, "alternative_approach"
        return None, "skip"

    elif strategy == "fix_encoding":
        new_args = dict(args)
        if "content" in new_args:
            return new_args, "simplify"
        return None, "skip"

    elif strategy == "retry_later":
        return args, "retry"

    elif strategy == "change_port":
        new_args = dict(args)
        if "command" in new_args:
            new_args["command"] = new_args["command"].replace("8000", "8001")
            return new_args, "alternative_approach"
        return None, "skip"

    elif strategy == "elevate_or_skip":
        return None, "ask_user"

    return None, "skip"


def _extract_module_name(error: str) -> str | None:
    import re
    match = re.search(r"No module named ['\"](\w+)", error)
    if match:
        return match.group(1)
    match = re.search(r"ModuleNotFoundError.*'(\w+)'", error)
    if match:
        return match.group(1)
    return None
