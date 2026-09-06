"""Task planner — breaks complex tasks into simple atomic steps for small models."""
import re
import json


_STEP_TEMPLATES = {
    "create_project": [
        {"tool": "list_templates", "args": {}, "hint": "Check available templates"},
        {"tool": "scaffold_project", "args": {"template": "PLACEHOLDER", "name": "PLACEHOLDER"}, "hint": "Create project from template"},
        {"tool": "execute_shell_command", "args": {"command": "cd PROJECT_DIR && npm install"}, "hint": "Install dependencies"},
        {"tool": "workspace_file_ops", "args": {"action": "read", "path": "package.json"}, "hint": "Verify project structure"},
        {"tool": "git_checkpoint", "args": {"message": "feat: initial project setup"}, "hint": "Commit initial code"},
        {"tool": "done", "args": {"summary": "Project created successfully"}, "hint": "Finish"},
    ],
    "write_file": [
        {"tool": "workspace_file_ops", "args": {"action": "write", "path": "PLACEHOLDER", "content": "PLACEHOLDER"}, "hint": "Write the file"},
        {"tool": "git_checkpoint", "args": {"message": "feat: add FILENAME"}, "hint": "Commit the file"},
        {"tool": "done", "args": {"summary": "File created"}, "hint": "Finish"},
    ],
    "fix_bug": [
        {"tool": "search_code", "args": {"pattern": "PLACEHOLDER"}, "hint": "Find the error/bug in code"},
        {"tool": "workspace_file_ops", "args": {"action": "read", "path": "PLACEHOLDER"}, "hint": "Read the problematic file"},
        {"tool": "workspace_file_ops", "args": {"action": "search_replace", "path": "PLACEHOLDER", "old_text": "PLACEHOLDER", "new_text": "PLACEHOLDER"}, "hint": "Apply the fix"},
        {"tool": "execute_shell_command", "args": {"command": "PLACEHOLDER"}, "hint": "Test the fix"},
        {"tool": "git_checkpoint", "args": {"message": "fix: DESCRIPTION"}, "hint": "Commit the fix"},
        {"tool": "done", "args": {"summary": "Bug fixed"}, "hint": "Finish"},
    ],
    "run_tests": [
        {"tool": "execute_shell_command", "args": {"command": "python -m pytest --tb=short 2>&1 | head -50"}, "hint": "Run tests and check results"},
        {"tool": "done", "args": {"summary": "Tests completed"}, "hint": "Finish"},
    ],
    "analyze_code": [
        {"tool": "analyze_project_structure", "args": {"path": "."}, "hint": "Scan project structure"},
        {"tool": "search_code", "args": {"pattern": "PLACEHOLDER"}, "hint": "Search for specific patterns"},
        {"tool": "count_lines", "args": {"path": "."}, "hint": "Count lines of code"},
        {"tool": "done", "args": {"summary": "Analysis complete"}, "hint": "Finish"},
    ],
    "docker_deploy": [
        {"tool": "docker_build", "args": {"path": ".", "tag": "PLACEHOLDER"}, "hint": "Build Docker image"},
        {"tool": "docker_run", "args": {"image": "PLACEHOLDER"}, "hint": "Run the container"},
        {"tool": "docker_stats", "args": {}, "hint": "Check resource usage"},
        {"tool": "done", "args": {"summary": "Deployed"}, "hint": "Finish"},
    ],
    "api_test": [
        {"tool": "api_get", "args": {"url": "PLACEHOLDER"}, "hint": "Test the endpoint"},
        {"tool": "api_validate", "args": {"url": "PLACEHOLDER", "expected_status": 200}, "hint": "Validate response"},
        {"tool": "done", "args": {"summary": "API tested"}, "hint": "Finish"},
    ],
    "backup_data": [
        {"tool": "backup_directory", "args": {"source": "PLACEHOLDER"}, "hint": "Create backup"},
        {"tool": "list_backups", "args": {}, "hint": "Verify backup exists"},
        {"tool": "done", "args": {"summary": "Backup created"}, "hint": "Finish"},
    ],
    "db_work": [
        {"tool": "db_schema", "args": {}, "hint": "Check database schema"},
        {"tool": "db_query", "args": {"query": "PLACEHOLDER"}, "hint": "Run the query"},
        {"tool": "done", "args": {"summary": "Database operation complete"}, "hint": "Finish"},
    ],
}


def detect_task_type(prompt: str) -> str:
    """Detect the primary task type from a user prompt."""
    p = prompt.lower()

    if re.search(r"(?:создай|создать|собери|собрать|новый.*проект|new.*project|build.*app|create.*project)", p):
        return "create_project"
    if re.search(r"(?:напиши.*файл|write.*file|создай.*файл|create.*file|запиши)", p):
        return "write_file"
    if re.search(r"(?:исправ|fix|баг|bug|ошибк|error|не работ|broken)", p):
        return "fix_bug"
    if re.search(r"(?:тест|test|pytest|unittest|провер.*работ)", p):
        return "run_tests"
    if re.search(r"(?:анализ|analyz|посмотр.*код|исслед|что.*тут| count_lines|search_code)", p):
        return "analyze_code"
    if re.search(r"(?:docker|контейнер|container|compose)", p):
        return "docker_deploy"
    if re.search(r"(?:api.*test|тест.*api|провер.*api|graphql|endpoint)", p):
        return "api_test"
    if re.search(r"(?:бэкап|backup|резервн|копи|восстановл)", p):
        return "backup_data"
    if re.search(r"(?:sql|баз.*данн|database|запрос.*бд|таблиц|table)", p):
        return "db_work"
    if re.search(r"(?:напиши|write|код|code|скрипт|script|компонент|function)", p):
        return "write_file"
    return "general"


def create_plan(prompt: str) -> dict:
    """Create a step-by-step plan for the given task."""
    task_type = detect_task_type(prompt)
    steps = _STEP_TEMPLATES.get(task_type, None)

    if steps is None:
        steps = [
            {"tool": "analyze_project_structure", "args": {"path": "."}, "hint": "Understand the project"},
            {"tool": "done", "args": {"summary": "Task analyzed — model needs to decide next steps"}, "hint": "Finish or continue"},
        ]

    plan = {
        "task_type": task_type,
        "total_steps": len(steps),
        "steps": [],
        "needs_user_input": [],
    }

    for i, step in enumerate(steps):
        plan_step = {
            "index": i + 1,
            "tool": step["tool"],
            "args": dict(step["args"]),
            "hint": step["hint"],
            "status": "pending",
        }

        has_placeholder = any(v == "PLACEHOLDER" for v in step["args"].values())
        if has_placeholder:
            plan_step["status"] = "needs_input"
            plan["needs_user_input"].append(i + 1)

        plan["steps"].append(plan_step)

    return plan


def render_plan_for_model(plan: dict, prompt: str) -> str:
    """Render a plan as simple text instructions for the LLM."""
    lines = [f"TASK TYPE: {plan['task_type'].upper()}", ""]

    for step in plan["steps"]:
        status_marker = "[TODO]" if step["status"] == "pending" else "[?]"
        args_preview = json.dumps(step["args"], ensure_ascii=False)[:100]
        lines.append(
            f"Step {step['index']}: {status_marker} Call {step['tool']}({args_preview})"
        )
        lines.append(f"  -> {step['hint']}")
        lines.append("")

    lines.append(f"Total steps: {plan['total_steps']}")
    lines.append("After each step, check the result before proceeding to the next.")

    return "\n".join(lines)


def get_next_step(plan: dict) -> dict | None:
    """Get the next pending step from a plan."""
    for step in plan["steps"]:
        if step["status"] == "pending":
            return step
    return None


def mark_step_done(plan: dict, step_index: int, success: bool):
    """Mark a step as completed or failed."""
    for step in plan["steps"]:
        if step["index"] == step_index:
            step["status"] = "done" if success else "failed"
            break


def suggest_recovery(plan: dict, failed_step: dict, error: str) -> str:
    """Suggest recovery action when a step fails."""
    tool = failed_step["tool"]

    recovery_map = {
        "execute_shell_command": "Check if the command exists. Try: which COMMAND or where COMMAND",
        "workspace_file_ops": "Check if the path exists and is correct. Use list action to verify.",
        "docker_build": "Check if Dockerfile exists. Try: ls -la Dockerfile",
        "docker_run": "Check if image was built. Try: docker_images to list available images",
        "db_query": "Check if database exists. Try: db_schema to see tables",
        "api_get": "Check if URL is correct and server is running",
        "git_checkpoint": "Check git status. Maybe there's nothing to commit",
        "scaffold_project": "Try list_templates to see available templates",
    }

    suggestion = recovery_map.get(tool, f"Try a different approach for {tool}")
    return f"Step failed: {tool} — {error}\nSuggestion: {suggestion}"
