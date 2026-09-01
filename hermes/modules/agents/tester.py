"""Tester agent — runs tests and reports failures."""
from __future__ import annotations

from hermes.modules.agents.base import BaseAgent
from hermes.modules.agents.message import MessageType


class TesterAgent(BaseAgent):
    def __init__(self, task: str = "", model: str = "", **kwargs):
        super().__init__(role="tester", task=task, model=model, **kwargs)

    async def run(self) -> dict:
        from hermes.tools import tool_execute_shell_command, tool_run_python

        result = {
            "success": True,
            "tests_run": 0,
            "tests_passed": 0,
            "tests_failed": 0,
            "failures": [],
            "output": "",
        }

        test_commands = self._detect_test_commands()
        for cmd in test_commands:
            r = await tool_execute_shell_command(command=cmd, timeout=120)
            result["tests_run"] += 1
            if r.get("success"):
                result["tests_passed"] += 1
            else:
                result["tests_failed"] += 1
                result["failures"].append({"command": cmd, "error": r.get("error", r.get("stderr", ""))})
                result["success"] = False

            output = r.get("stdout", "") + r.get("stderr", "")
            result["output"] += output[-2000:] + "\n"

        self.send_message("coordinator",
                         f"Tests complete: {result['tests_passed']}/{result['tests_run']} passed",
                         MessageType.RESULT, result)
        return result

    def _detect_test_commands(self) -> list[str]:
        from pathlib import Path
        from hermes.core import WORKSPACE_DIR

        commands = []
        if (WORKSPACE_DIR / "package.json").exists():
            commands.append("npm test --silent")
        if list(WORKSPACE_DIR.rglob("test_*.py")) or list(WORKSPACE_DIR.rglob("*_test.py")):
            commands.append("python -m pytest -x --tb=short -q")
        if (WORKSPACE_DIR / "Makefile").exists():
            content = (WORKSPACE_DIR / "Makefile").read_text(encoding="utf-8", errors="replace")
            if "test:" in content:
                commands.append("make test")
        if not commands:
            commands.append("python -m pytest -x --tb=short -q")
        return commands

    async def run_specific_test(self, test_path: str) -> dict:
        from hermes.tools import tool_execute_shell_command
        r = await tool_execute_shell_command(command=f"python -m pytest {test_path} -v --tb=short")
        return {
            "success": r.get("success", False),
            "test_path": test_path,
            "output": r.get("stdout", "") + r.get("stderr", ""),
        }

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["capabilities"] = ["run_all_tests", "run_specific_test", "detect_test_framework"]
        return d
