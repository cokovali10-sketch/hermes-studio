"""Pattern recognizer — match errors against known patterns and suggest fixes."""
from __future__ import annotations

import re

KNOWN_PATTERNS = [
    {
        "name": "import_error",
        "pattern": r"ModuleNotFoundError|ImportError|No module named",
        "suggested_fix": "Install the missing module with pip install <module_name>",
        "strategy": "install_dependency",
    },
    {
        "name": "syntax_error",
        "pattern": r"SyntaxError|IndentationError|invalid syntax",
        "suggested_fix": "Check the reported line for syntax issues — missing colons, unclosed brackets, or bad indentation",
        "strategy": "fix_syntax",
    },
    {
        "name": "permission_error",
        "pattern": r"PermissionError|Permission denied|Access is denied",
        "suggested_fix": "Run with elevated privileges or check file permissions",
        "strategy": "elevate_or_skip",
    },
    {
        "name": "network_error",
        "pattern": r"ConnectionError|ConnectionRefused|TimeoutError|DNS|ENOTFOUND",
        "suggested_fix": "Check network connectivity and ensure the target service is running",
        "strategy": "retry_later",
    },
    {
        "name": "file_not_found",
        "pattern": r"FileNotFoundError|No such file|not found|does not exist",
        "suggested_fix": "Verify the file path exists and is correct",
        "strategy": "verify_path",
    },
    {
        "name": "type_error",
        "pattern": r"TypeError|unsupported operand|argument|cannot concatenate",
        "suggested_fix": "Check argument types — ensure correct types are passed to functions",
        "strategy": "fix_types",
    },
    {
        "name": "key_error",
        "pattern": r"KeyError|Key.*not found|missing key",
        "suggested_fix": "Check dictionary keys — use .get() with a default value",
        "strategy": "safe_access",
    },
    {
        "name": "value_error",
        "pattern": r"ValueError|invalid literal|not a valid",
        "suggested_fix": "Validate input before conversion — use try/except or pre-validation",
        "strategy": "validate_input",
    },
    {
        "name": "encoding_error",
        "pattern": r"UnicodeDecodeError|UnicodeEncodeError|charmap|encoding",
        "suggested_fix": "Specify encoding explicitly (e.g. encoding='utf-8') when opening files",
        "strategy": "fix_encoding",
    },
    {
        "name": "port_in_use",
        "pattern": r"Address already in use|EADDRINUSE|port.*in use",
        "suggested_fix": "Kill the process using the port or choose a different port",
        "strategy": "change_port",
    },
]


def recognize_pattern(error_message: str) -> dict | None:
    for known in KNOWN_PATTERNS:
        if re.search(known["pattern"], error_message, re.IGNORECASE):
            return {
                "matched": True,
                "pattern_name": known["name"],
                "suggested_fix": known["suggested_fix"],
                "strategy": known["strategy"],
            }
    return None


def get_all_patterns() -> list[dict]:
    return [
        {"name": p["name"], "pattern": p["pattern"], "suggested_fix": p["suggested_fix"]}
        for p in KNOWN_PATTERNS
    ]
