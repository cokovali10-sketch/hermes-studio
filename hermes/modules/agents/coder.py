"""Coder agent — writes and modifies code."""
from __future__ import annotations

from hermes.modules.agents.base import BaseAgent


class CoderAgent(BaseAgent):
    def __init__(self, task: str = "", model: str = "", **kwargs):
        super().__init__(role="coder", task=task, model=model, **kwargs)

    async def run(self) -> dict:
        from hermes.tools import (
            tool_workspace_file_ops,
            tool_diff_apply,
            tool_execute_shell_command,
            tool_run_python,
            tool_search_code,
        )

        result = {"success": True, "actions": [], "errors": []}
        return result

    async def write_file(self, path: str, content: str) -> dict:
        from hermes.tools import tool_workspace_file_ops
        return await tool_workspace_file_ops(action="write", path=path, content=content)

    async def read_file(self, path: str) -> dict:
        from hermes.tools import tool_workspace_file_ops
        return await tool_workspace_file_ops(action="read", path=path)

    async def apply_diff(self, path: str, diff: str) -> dict:
        from hermes.tools import tool_diff_apply
        return await tool_diff_apply(path=path, diff=diff)

    async def search_and_replace(self, path: str, old_text: str, new_text: str, replace_all: bool = False) -> dict:
        from hermes.tools import tool_workspace_file_ops
        return await tool_workspace_file_ops(
            action="search_replace", path=path,
            old_text=old_text, new_text=new_text, replace_all=replace_all,
        )

    async def run_shell(self, command: str, cwd: str = ".") -> dict:
        from hermes.tools import tool_execute_shell_command
        return await tool_execute_shell_command(command=command, cwd=cwd)

    async def run_python(self, code: str, timeout: int = 30) -> dict:
        from hermes.tools import tool_run_python
        return await tool_run_python(code=code, timeout=timeout)

    async def search_code(self, pattern: str, include: str = "") -> dict:
        from hermes.tools import tool_search_code
        return await tool_search_code(pattern=pattern, include=include)

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["capabilities"] = ["write_file", "read_file", "apply_diff", "search_and_replace", "run_shell", "run_python", "search_code"]
        return d
