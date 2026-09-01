"""Safety protocol — protection layer for Hermes tools."""
import json
import pathlib
import re
import time

from hermes.bus import bus

BLOCKED_SHELL_PATTERNS = [
    r"format\s+[a-zA-Z]:",
    r"rd\s+/s\s+[a-zA-Z]:",
    r"rmdir\s+/s\s+[a-zA-Z]:",
    r"del\s+[/\-]+[sfqSQ]+\s+[a-zA-Z]:",
    r"del\s+/[sfqSQ]+\s+\S+",
    r"rm\s+-rf\s+/",
    r"rm\s+-rf\s+~",
    r"rm\s+-rf\s+\*",
    r"mkfs\.",
    r"dd\s+if=.*of=/dev/",
    r"shutdown",
    r"reboot",
    r"bcdedit",
    r"diskpart",
    r"cipher\s+/w",
    r"icacls\s+[a-zA-Z]:\\\s*/grant",
    r"takeown\s+/f\s+[a-zA-Z]:",
    r"reg\s+delete\s+HKLM",
    r"reg\s+delete\s+HKCU\\Software\\Microsoft\\Windows\\CurrentVersion",
    r"net\s+user\s+\S+\s+/delete",
    r"net\s+localgroup\s+Administrators",
    r"attrib\s+-r\s+-s\s+-h\s+[a-zA-Z]:\\",
    r"vssadmin\s+delete",
    r"bcdboot",
    r"robocopy.*\/MIR\s+[a-zA-Z]:\\",
    r"xcopy.*\/Y\s+[a-zA-Z]:\\",
]

BLOCKED_PATHS = [
    r"C:\\Windows",
    r"C:\\Program Files",
    r"C:\\Program Files \(x86\)",
    r"C:\\Users\\[^\\]+\\AppData",
    r"C:\\Users\\[^\\]+\\NTUSER",
    r"C:\\Users\\[^\\]+\\.ssh",
    r"C:\\Users\\[^\\]+\\.env",
    r"C:\\Users\\[^\\]+\\Documents\\.*\.(key|pem|p12|pfx)",
    r"C:\\Users\\[^\\]+\\Desktop\\.*\.(key|pem)",
    r"D:\\.*\\.env",
    r"D:\\.*\\.git\\config",
    r"D:\\.*\\.ssh",
    r"/etc/passwd",
    r"/etc/shadow",
    r"/root",
    r"/boot",
    r"/sys",
    r"/proc",
]

DANGEROUS_EXTENSIONS = [
    ".sys", ".dll", ".exe", ".msi", ".com", ".bat", ".cmd",
    ".scr", ".pif", ".reg", ".inf", ".ini", ".drv",
]

BLOCKED_SHELL_RE = [re.compile(p, re.IGNORECASE) for p in BLOCKED_SHELL_PATTERNS]
BLOCKED_PATH_RE = [re.compile(p, re.IGNORECASE) for p in BLOCKED_PATHS]

SAFETY_VIOLATIONS = []


class SafetyViolation(Exception):
    def __init__(self, message, rule=""):
        super().__init__(message)
        self.rule = rule


def _check_safety_shell(command: str):
    for pattern in BLOCKED_SHELL_RE:
        if pattern.search(command):
            raise SafetyViolation(
                f"BLOCKED: Dangerous command detected: {command[:100]}",
                rule=f"Shell blocked: {pattern.pattern}",
            )


def _check_safety_path(path: str, action: str = "write"):
    check_str = path.replace("\\", "/")
    for pattern in BLOCKED_PATH_RE:
        if pattern.search(check_str):
            raise SafetyViolation(
                f"BLOCKED: Access to protected path denied: {path}",
                rule=f"Path blocked: {pattern.pattern}",
            )
    ext = pathlib.Path(path).suffix.lower()
    if ext in DANGEROUS_EXTENSIONS and action in ("write", "create", "delete"):
        raise SafetyViolation(
            f"BLOCKED: Cannot {action} system file: {path}",
            rule=f"Dangerous extension: {ext}",
        )


def _check_safety_git(message: str):
    lower = message.lower()
    dangerous = ["drop database", "delete all", "rm -rf", "format", "wipe", "destroy"]
    for d in dangerous:
        if d in lower:
            raise SafetyViolation(
                f"BLOCKED: Suspicious git commit message: {message[:100]}",
                rule=f"Suspicious content: {d}",
            )


def _check_safety_python(code: str):
    dangerous = [
        "os.system", "subprocess.call", "shutil.rmtree('/')",
        "__import__('os')", "__import__('subprocess')",
        "eval(", "exec(",
        "open('/etc/", "open('C:\\\\Windows",
        "os.remove", "os.unlink",
    ]
    for d in dangerous:
        if d in code:
            raise SafetyViolation(
                f"BLOCKED: Dangerous Python operation: {d}",
                rule=f"Python safety: {d}",
            )


def safety_check(tool_name: str, args: dict):
    try:
        if tool_name == "execute_shell_command":
            _check_safety_shell(args.get("command", ""))

        elif tool_name == "workspace_file_ops":
            path = args.get("path", "")
            action = args.get("action", "")
            if action in ("delete",):
                _check_safety_path(path, "delete")
            if action in ("write", "create"):
                _check_safety_path(path, "write")
                content = args.get("content", "")
                if content:
                    _check_safety_python(content)

        elif tool_name == "run_python":
            _check_safety_python(args.get("code", ""))

        elif tool_name == "git_checkpoint":
            _check_safety_git(args.get("message", ""))

        elif tool_name == "kill_process":
            name = args.get("name", "").lower()
            protected = ["explorer", "csrss", "lsass", "svchost", "winlogon", "services", "system", "kernel"]
            if name in protected:
                raise SafetyViolation(
                    f"BLOCKED: Cannot kill system process: {name}",
                    rule="Protected process",
                )

        elif tool_name == "scaffold_project":
            name = args.get("name", "")
            if "/" in name or "\\" in name or name.startswith("."):
                raise SafetyViolation(
                    f"BLOCKED: Invalid project name: {name}",
                    rule="Invalid name",
                )

        return True

    except SafetyViolation as e:
        SAFETY_VIOLATIONS.append({
            "tool": tool_name,
            "args": json.dumps(args, ensure_ascii=False)[:200],
            "message": str(e),
            "rule": e.rule,
            "ts": time.time(),
        })
        bus.emit("safety.blocked", {"tool": tool_name, "message": str(e), "rule": e.rule})
        raise
