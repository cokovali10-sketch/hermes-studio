"""Pre-built workflow templates for common tasks."""
import json
import re


WORKFLOWS = {
    "react_app": {
        "name": "React TypeScript App",
        "description": "Создать React-приложение с TypeScript и Tailwind",
        "trigger": re.compile(
            r"(?:react.*(?:typescript|ts|tailwind)|реакт|создай.*react|new.*react)",
            re.IGNORECASE,
        ),
        "steps": [
            {"tool": "scaffold_project", "args": {"template": "react-ts", "name": "app"}, "parallel": False},
            {"tool": "execute_shell_command", "args": {"command": "cd app && npm install"}, "parallel": False},
            {"tool": "workspace_file_ops", "args": {"action": "read", "path": "app/package.json"}, "parallel": False},
            {"tool": "git_checkpoint", "args": {"message": "feat: init react-ts app with tailwind"}, "parallel": False},
            {"tool": "done", "args": {"summary": "React TypeScript app created with Tailwind CSS"} },
        ],
    },
    "python_api": {
        "name": "Python FastAPI",
        "description": "Создать Python FastAPI сервер",
        "trigger": re.compile(
            r"(?:fastapi|python.*api|пайтон.*сервер|python.*server|фастапи)",
            re.IGNORECASE,
        ),
        "steps": [
            {"tool": "scaffold_project", "args": {"template": "python-fastapi", "name": "api"}, "parallel": False},
            {"tool": "execute_shell_command", "args": {"command": "cd api && pip install -r requirements.txt"}, "parallel": False},
            {"tool": "workspace_file_ops", "args": {"action": "read", "path": "api/main.py"}, "parallel": False},
            {"tool": "git_checkpoint", "args": {"message": "feat: init python-fastapi project"}, "parallel": False},
            {"tool": "done", "args": {"summary": "Python FastAPI project created"} },
        ],
    },
    "static_site": {
        "name": "Static HTML Site",
        "description": "Создать статический HTML-сайт",
        "trigger": re.compile(
            r"(?:стати.*сайт|static.*site|html.*сайт|лендинг|landing|верстк|html.*css)",
            re.IGNORECASE,
        ),
        "steps": [
            {"tool": "scaffold_project", "args": {"template": "static-html", "name": "site"}, "parallel": False},
            {"tool": "workspace_file_ops", "args": {"action": "read", "path": "site/index.html"}, "parallel": False},
            {"tool": "git_checkpoint", "args": {"message": "feat: init static html site"}, "parallel": False},
            {"tool": "done", "args": {"summary": "Static HTML site created"} },
        ],
    },
    "express_api": {
        "name": "Node Express API",
        "description": "Создать Node.js Express сервер",
        "trigger": re.compile(
            r"(?:express|node.*api|нод.*сервер|node.*server|экспресс)",
            re.IGNORECASE,
        ),
        "steps": [
            {"tool": "scaffold_project", "args": {"template": "node-express", "name": "server"}, "parallel": False},
            {"tool": "execute_shell_command", "args": {"command": "cd server && npm install"}, "parallel": False},
            {"tool": "workspace_file_ops", "args": {"action": "read", "path": "server/package.json"}, "parallel": False},
            {"tool": "git_checkpoint", "args": {"message": "feat: init node-express server"}, "parallel": False},
            {"tool": "done", "args": {"summary": "Node Express API created"} },
        ],
    },
    "security_scan": {
        "name": "Security Scan",
        "description": "Полное сканирование безопасности проекта",
        "trigger": re.compile(
            r"(?:скан.*безопасност|security.*scan|провер.*безопасност|audit|аудит|найти.*секрет|find.*secret)",
            re.IGNORECASE,
        ),
        "steps": [
            {"tool": "scan_secrets", "args": {"path": "."}, "parallel": False},
            {"tool": "scan_dependencies", "args": {"path": "."}, "parallel": False},
            {"tool": "check_permissions", "args": {"path": "."}, "parallel": False},
            {"tool": "audit_env", "args": {}, "parallel": False},
            {"tool": "done", "args": {"summary": "Security scan complete"} },
        ],
    },
    "code_review": {
        "name": "Code Review",
        "description": "Обзор и анализ кодовой базы",
        "trigger": re.compile(
            r"(?:обзор.*код|code.*review|анализ.*код|проанализируй.*код|review.*code)",
            re.IGNORECASE,
        ),
        "steps": [
            {"tool": "analyze_project_structure", "args": {"path": "."}, "parallel": False},
            {"tool": "count_lines", "args": {"path": "."}, "parallel": False},
            {"tool": "analyze_code_quality", "args": {"path": "."}, "parallel": False},
            {"tool": "find_todos", "args": {"path": "."}, "parallel": False},
            {"tool": "scan_secrets", "args": {"path": "."}, "parallel": False},
            {"tool": "done", "args": {"summary": "Code review complete"} },
        ],
    },
    "full_deploy": {
        "name": "Full Deploy",
        "description": "Полная сборка и деплой",
        "trigger": re.compile(
            r"(?:деплой|deploy|запусти|run.*prod|build.*deploy|собрать.*запустить)",
            re.IGNORECASE,
        ),
        "steps": [
            {"tool": "analyze_project_structure", "args": {"path": "."}, "parallel": False},
            {"tool": "execute_shell_command", "args": {"command": "npm install"}, "parallel": False},
            {"tool": "execute_shell_command", "args": {"command": "npm run build"}, "parallel": False},
            {"tool": "docker_build", "args": {"path": ".", "tag": "app:latest"}, "parallel": False},
            {"tool": "docker_run", "args": {"image": "app:latest", "ports": "8080:80"}, "parallel": False},
            {"tool": "git_checkpoint", "args": {"message": "deploy: build and run in docker"}, "parallel": False},
            {"tool": "done", "args": {"summary": "Deployed successfully"} },
        ],
    },
    "git_save": {
        "name": "Git Save All",
        "description": "Сделать бэкап всех изменений",
        "trigger": re.compile(
            r"(?:сохрани|сохран|save|backup|коммит|commit.*all|запомни|закоммить)",
            re.IGNORECASE,
        ),
        "steps": [
            {"tool": "analyze_project_structure", "args": {"path": "."}, "parallel": False},
            {"tool": "git_checkpoint", "args": {"message": "chore: save progress", "add_all": True}, "parallel": False},
            {"tool": "done", "args": {"summary": "Changes committed"} },
        ],
    },
    "data_convert": {
        "name": "Data Conversion",
        "description": "Конвертация данных между форматами",
        "trigger": re.compile(
            r"(?:конверт.*csv|csv.*json|json.*csv|xml.*json|конверт.*json|конверт.*xml|transcode|преобраз)",
            re.IGNORECASE,
        ),
        "steps": [
            {"tool": "workspace_file_ops", "args": {"action": "list", "path": "."}, "parallel": False},
            {"tool": "done", "args": {"summary": "Identified files — use csv_to_json/json_to_csv/xml_to_json"} },
        ],
    },
    "db_backup": {
        "name": "Database Backup",
        "description": "Бэкап базы данных",
        "trigger": re.compile(
            r"(?:бэкап.*бд|бэкап.*баз|backup.*db|backup.*database|сохрани.*базу)",
            re.IGNORECASE,
        ),
        "steps": [
            {"tool": "db_schema", "args": {}, "parallel": False},
            {"tool": "db_backup", "args": {}, "parallel": False},
            {"tool": "list_backups", "args": {}, "parallel": False},
            {"tool": "done", "args": {"summary": "Database backed up"} },
        ],
    },
}


def match_workflow(prompt: str) -> dict | None:
    """Find a matching workflow for the given prompt."""
    for wf_id, wf in WORKFLOWS.items():
        if wf["trigger"].search(prompt):
            return {"id": wf_id, **wf}
    return None


def get_all_workflows() -> list:
    """Return list of all available workflows."""
    return [
        {"id": wf_id, "name": wf["name"], "description": wf["description"]}
        for wf_id, wf in WORKFLOWS.items()
    ]


def render_workflow_for_model(workflow: dict) -> str:
    """Render a workflow as simple step-by-step instructions."""
    lines = [f"WORKFLOW: {workflow['name']}", f"Description: {workflow['description']}", ""]
    for i, step in enumerate(workflow["steps"], 1):
        args_str = json.dumps(step["args"], ensure_ascii=False)[:80]
        lines.append(f"Step {i}: Call {step['tool']}({args_str})")
    lines.append(f"\nTotal steps: {len(workflow['steps'])}")
    return "\n".join(lines)
