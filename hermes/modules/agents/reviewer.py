"""Reviewer agent — reviews code, finds bugs, suggests improvements."""
from __future__ import annotations

from hermes.modules.agents.base import BaseAgent
from hermes.modules.agents.message import MessageType


class ReviewerAgent(BaseAgent):
    def __init__(self, task: str = "", model: str = "", **kwargs):
        super().__init__(role="reviewer", task=task, model=model, **kwargs)

    async def run(self) -> dict:
        from hermes.tools import tool_search_code, tool_workspace_file_ops

        result = {
            "success": True,
            "issues": [],
            "suggestions": [],
            "summary": "",
        }

        patterns = [
            (r"except\s*:", "Bare except clause — catch specific exceptions instead"),
            (r"eval\(", "Use of eval() — potential security risk"),
            (r"exec\(", "Use of exec() — potential security risk"),
            (r"TODO|FIXME|HACK|XXX", "Unresolved TODO/FIXME comment"),
            (r"password\s*=\s*['\"]", "Hardcoded password detected"),
            (r"print\(", "Debug print statement left in code"),
        ]

        for pattern, desc in patterns:
            r = await tool_search_code(pattern=pattern, include="*.py", max_results=10)
            for match in r.get("results", []):
                result["issues"].append({
                    "file": match["file"],
                    "line": match["line"],
                    "description": desc,
                    "snippet": match.get("match", "")[:100],
                })

        self.send_message("coordinator",
                         f"Review complete: {len(result['issues'])} issues found",
                         MessageType.RESULT, result)
        return result

    async def review_file(self, path: str) -> dict:
        from hermes.tools import tool_workspace_file_ops, tool_ast_parse

        content_r = await tool_workspace_file_ops(action="read", path=path)
        if not content_r.get("success"):
            return {"success": False, "error": content_r.get("error", "Cannot read file")}

        issues = []
        suggestions = []
        lines = content_r["content"].splitlines()

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if len(stripped) > 120:
                suggestions.append({"line": i, "description": f"Line too long ({len(stripped)} chars)"})
            if stripped.startswith("def ") and ":" not in stripped:
                issues.append({"line": i, "description": "Malformed function definition"})

        return {
            "success": True,
            "path": path,
            "issues": issues,
            "suggestions": suggestions,
            "lines": len(lines),
        }

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["capabilities"] = ["review_codebase", "review_file", "find_issues", "suggest_improvements"]
        return d
