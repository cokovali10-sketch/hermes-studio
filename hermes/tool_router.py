"""Smart tool router — pre-filters 100 tools down to 5-15 relevant per request."""
import re
from datetime import datetime


_TOOL_CATEGORIES = {
    "core": [
        "workspace_file_ops", "execute_shell_command", "git_checkpoint",
        "analyze_project_structure", "capture_screenshot", "read_image",
        "search_code", "run_python", "fetch_url", "diff_apply",
        "kill_process", "env_info", "list_templates", "scaffold_project", "done",
    ],
    "docker": [
        "docker_build", "docker_run", "docker_stop", "docker_list",
        "docker_logs", "docker_compose", "docker_images", "docker_exec",
        "docker_stats", "docker_clean",
    ],
    "security": [
        "scan_secrets", "scan_dependencies", "check_ssl", "port_scan",
        "hash_file", "check_headers", "vuln_scan", "check_permissions",
        "generate_secret", "audit_env",
    ],
    "profiling": [
        "profile_function", "benchmark_file", "measure_time", "memory_usage",
        "cpu_info", "disk_speed", "network_latency", "find_slow_code",
    ],
    "database": [
        "db_query", "db_schema", "db_backup", "db_analyze",
        "db_create_table", "db_insert", "db_export_csv", "db_optimize",
    ],
    "apitest": [
        "api_get", "api_post", "api_put", "api_delete", "api_patch",
        "api_benchmark", "api_validate", "graphql_query", "websocket_test", "api_mock",
    ],
    "docs": [
        "generate_readme", "generate_changelog", "generate_api_docs",
        "generate_docstring", "analyze_code_quality", "find_todos",
        "count_lines", "generate_type_hints",
    ],
    "git_advanced": [
        "git_log", "git_diff", "git_branch", "git_blame", "git_stash",
        "git_stats", "git_search", "git_file_history",
    ],
    "backup": [
        "backup_directory", "restore_backup", "list_backups",
        "sync_directories", "cleanup_old_files", "find_duplicates",
    ],
    "migration": [
        "csv_to_json", "json_to_csv", "xml_to_json", "json_transform",
        "merge_json", "split_file", "encode_decode",
    ],
    "kubernetes": [
        "k8s_get_pods", "k8s_get_services", "k8s_describe", "k8s_logs",
        "k8s_exec", "k8s_scale", "k8s_apply", "k8s_delete", "k8s_events",
        "k8s_context",
    ],
}

_KEYWORD_MAP = {
    "docker": re.compile(
        r"(?:docker|контейнер|container|образ|image|compose|kubectl)",
        re.IGNORECASE,
    ),
    "security": re.compile(
        r"(?:безопасност|security|секрет|secret|ssl|порт|port_scan|уязвим|vuln|аудит|audit|парол|password|токен|token|ключ|key)",
        re.IGNORECASE,
    ),
    "profiling": re.compile(
        r"(?:профил|profil|производительн|performance|бенчмарк|benchmark|память|memory|cpu|диск|disk|скорост|speed|медленн|slow|узк|bottleneck)",
        re.IGNORECASE,
    ),
    "database": re.compile(
        r"(?:баз[ауы]\s*данн|database|sql|запрос|query|таблиц|table|схем|schema|postgres|mysql|sqlite|бэкап.*бд|db_backup)",
        re.IGNORECASE,
    ),
    "apitest": re.compile(
        r"(?:api|rest|graphql|websocket|endpoint|запрос.*сервер|тест.*api|mock|мок|http.*get|http.*post)",
        re.IGNORECASE,
    ),
    "docs": re.compile(
        r"(?:документ|doc|readme|changelog|docstring|комментари|comment|todo|fixme|api.*doc|type.?hint|качеств.*код|code.*quality)",
        re.IGNORECASE,
    ),
    "git_advanced": re.compile(
        r"(?:git.*истор|git.*log|git.*diff|git.*blame|git.*stash|git.*stat|git.*search|git.*file|ветк|branch.*git|коммит.*истор)",
        re.IGNORECASE,
    ),
    "backup": re.compile(
        r"(?:бэкап|backup|резервн|копи|восстановл|restore|синхрон|sync|дубликат|duplicate|очистк.*стар|cleanup)",
        re.IGNORECASE,
    ),
    "migration": re.compile(
        r"(?:csv|json|xml|конверт|convert|миграц|migrat|трансформ|transform|слияни|merge|раздел|split|encode|decode|кодир)",
        re.IGNORECASE,
    ),
    "kubernetes": re.compile(
        r"(?:kubernetes|k8s|под|pod|сервис.*k8s|node.*cluster|манифест|deploy.*k8s|kubectl|scale)",
        re.IGNORECASE,
    ),
}

_TASK_TYPE_KEYWORDS = {
    "create_project": re.compile(
        r"(?:созд(ай|ать|.*проект|.*приложен)|собр(ай|ать)|постр(ой|оить)|сдел(ай|ать).*сайт|сдел.*приложен|build.*project|new.*project|create.*app|create.*project|новый.*проект)",
        re.IGNORECASE,
    ),
    "fix_bug": re.compile(
        r"(?:исправ|fix|баг|bug|ошибк|error|не работ|broken|crash|патч|patch)",
        re.IGNORECASE,
    ),
    "refactor": re.compile(
        r"(?:рефактор|refactor|перепиши|rewrite|улучши.*код|clean.*code|оптимиз|optimi)",
        re.IGNORECASE,
    ),
    "test": re.compile(
        r"(?:тест|test|провер|check.*work|запусти.*провер|pytest|unittest)",
        re.IGNORECASE,
    ),
    "deploy": re.compile(
        r"(?:деплой|deploy|запусти|run|build|собери|билд|настр|setup|install|установ)",
        re.IGNORECASE,
    ),
    "analyze": re.compile(
        r"(?:анализ|analyz|посмотр|look.*at|что.*тут|what.*here|исслед|explor|скан|scan)",
        re.IGNORECASE,
    ),
    "write_code": re.compile(
        r"(?:напиши|write|код|code|скрипт|script|функци|function|компонент|component|класс|class|метод|method|страниц|page)",
        re.IGNORECASE,
    ),
}


def classify_request(prompt: str) -> dict:
    """Classify a user prompt into task type, relevant categories, and confidence."""
    categories = set(["core"])
    task_type = "general"
    confidence = 0.0

    for cat, regex in _KEYWORD_MAP.items():
        if regex.search(prompt):
            categories.add(cat)
            confidence += 0.3

    for ttype, regex in _TASK_TYPE_KEYWORDS.items():
        if regex.search(prompt):
            task_type = ttype
            confidence += 0.2
            break

    if confidence > 1.0:
        confidence = 1.0

    return {
        "task_type": task_type,
        "categories": list(categories),
        "confidence": min(confidence, 1.0),
        "prompt_len": len(prompt),
    }


def get_relevant_tools(prompt: str, max_tools: int = 15) -> list:
    """Return a filtered list of tool names relevant to the prompt."""
    classification = classify_request(prompt)
    categories = classification["categories"]
    task_type = classification["task_type"]

    tool_names = []
    for cat in categories:
        tool_names.extend(_TOOL_CATEGORIES.get(cat, []))

    if task_type == "create_project":
        for name in ["scaffold_project", "list_templates", "workspace_file_ops",
                      "execute_shell_command", "git_checkpoint"]:
            if name not in tool_names:
                tool_names.append(name)

    if task_type == "fix_bug":
        for name in ["search_code", "workspace_file_ops", "execute_shell_command",
                      "run_python", "diff_apply", "git_checkpoint"]:
            if name not in tool_names:
                tool_names.append(name)

    if task_type == "refactor":
        for name in ["search_code", "workspace_file_ops", "diff_apply",
                      "git_checkpoint", "analyze_project_structure"]:
            if name not in tool_names:
                tool_names.append(name)

    if task_type == "test":
        for name in ["execute_shell_command", "run_python", "workspace_file_ops",
                      "search_code", "git_checkpoint"]:
            if name not in tool_names:
                tool_names.append(name)

    if task_type == "deploy":
        for name in ["execute_shell_command", "workspace_file_ops", "git_checkpoint",
                      "docker_compose", "docker_build", "docker_run"]:
            if name not in tool_names:
                tool_names.append(name)

    if task_type == "analyze":
        for name in ["analyze_project_structure", "search_code", "workspace_file_ops",
                      "env_info", "run_python", "count_lines"]:
            if name not in tool_names:
                tool_names.append(name)

    if task_type == "write_code":
        for name in ["workspace_file_ops", "execute_shell_command", "search_code",
                      "git_checkpoint", "run_python", "diff_apply"]:
            if name not in tool_names:
                tool_names.append(name)

    if "done" not in tool_names:
        tool_names.append("done")

    seen = set()
    unique = []
    for name in tool_names:
        if name not in seen:
            seen.add(name)
            unique.append(name)

    return unique[:max_tools]


def get_tool_schemas(prompt: str, all_schemas: list, max_tools: int = 15) -> list:
    """Return filtered tool schemas relevant to the prompt."""
    relevant = set(get_relevant_tools(prompt, max_tools))
    return [s for s in all_schemas if s["function"]["name"] in relevant]


def build_compact_system(prompt: str, workspace: str) -> str:
    """Build a compact system prompt tailored to the detected task."""
    classification = classify_request(prompt)
    task_type = classification["task_type"]
    categories = classification["categories"]
    relevant_tools = get_relevant_tools(prompt, max_tools=12)

    tool_lines = []
    for name in relevant_tools:
        desc_map = {
            "workspace_file_ops": "file ops: read/write/create/delete/list/grep/search_replace/read_lines",
            "execute_shell_command": "run shell commands",
            "git_checkpoint": "git commit",
            "analyze_project_structure": "scan directory tree",
            "capture_screenshot": "take screenshot",
            "read_image": "read image for vision",
            "search_code": "regex search in code",
            "run_python": "run python code",
            "fetch_url": "HTTP request",
            "diff_apply": "apply diff patch",
            "kill_process": "kill process",
            "env_info": "system info",
            "list_templates": "list templates",
            "scaffold_project": "create project from template",
            "done": "signal task done with summary",
            "docker_build": "build docker image",
            "docker_run": "run docker container",
            "docker_stop": "stop container",
            "docker_list": "list containers",
            "docker_logs": "container logs",
            "docker_compose": "docker-compose commands",
            "docker_images": "list docker images",
            "docker_exec": "exec in container",
            "docker_stats": "container stats",
            "docker_clean": "cleanup docker",
            "scan_secrets": "scan code for secrets",
            "scan_dependencies": "check dependency vulns",
            "check_ssl": "check SSL cert",
            "port_scan": "scan ports",
            "hash_file": "hash a file",
            "check_headers": "check HTTP headers",
            "vuln_scan": "scan for vulnerabilities",
            "check_permissions": "check file permissions",
            "generate_secret": "generate random secret",
            "audit_env": "audit environment",
            "profile_function": "profile a function",
            "benchmark_file": "benchmark file",
            "measure_time": "measure execution time",
            "memory_usage": "check memory usage",
            "cpu_info": "get CPU info",
            "disk_speed": "test disk speed",
            "network_latency": "test network latency",
            "find_slow_code": "find slow code",
            "db_query": "run SQL query",
            "db_schema": "show DB schema",
            "db_backup": "backup database",
            "db_analyze": "analyze database",
            "db_create_table": "create table",
            "db_insert": "insert data",
            "db_export_csv": "export to CSV",
            "db_optimize": "optimize database",
            "api_get": "HTTP GET",
            "api_post": "HTTP POST",
            "api_put": "HTTP PUT",
            "api_delete": "HTTP DELETE",
            "api_patch": "HTTP PATCH",
            "api_benchmark": "benchmark API",
            "api_validate": "validate API response",
            "graphql_query": "GraphQL query",
            "websocket_test": "test WebSocket",
            "api_mock": "mock API server",
            "generate_readme": "generate README.md",
            "generate_changelog": "generate CHANGELOG.md",
            "generate_api_docs": "generate API docs",
            "generate_docstring": "generate docstrings",
            "analyze_code_quality": "analyze code quality",
            "find_todos": "find TODO/FIXME",
            "count_lines": "count lines of code",
            "generate_type_hints": "generate type hints",
            "git_log": "git log",
            "git_diff": "git diff",
            "git_branch": "git branch",
            "git_blame": "git blame",
            "git_stash": "git stash",
            "git_stats": "git stats",
            "git_search": "search in commits",
            "git_file_history": "file history",
            "backup_directory": "backup directory",
            "restore_backup": "restore from backup",
            "list_backups": "list backups",
            "sync_directories": "sync directories",
            "cleanup_old_files": "cleanup old files",
            "find_duplicates": "find duplicate files",
            "csv_to_json": "CSV to JSON",
            "json_to_csv": "JSON to CSV",
            "xml_to_json": "XML to JSON",
            "json_transform": "transform JSON",
            "merge_json": "merge JSON files",
            "split_file": "split file",
            "encode_decode": "encode/decode",
            "k8s_get_pods": "list K8s pods",
            "k8s_get_services": "list K8s services",
            "k8s_describe": "describe K8s resource",
            "k8s_logs": "K8s pod logs",
            "k8s_exec": "exec in K8s pod",
            "k8s_scale": "scale K8s deployment",
            "k8s_apply": "apply K8s manifest",
            "k8s_delete": "delete K8s resource",
            "k8s_events": "K8s events",
            "k8s_context": "switch K8s context",
        }
        desc = desc_map.get(name, name)
        tool_lines.append(f"- {name}: {desc}")

    tools_text = "\n".join(tool_lines)

    task_hints = {
        "create_project": "Create a new project step by step. Use scaffold_project or write files manually.",
        "fix_bug": "Find and fix the bug. Search for error, read relevant code, apply fix.",
        "refactor": "Refactor the code. Read files, search for patterns, rewrite improved version.",
        "test": "Write and run tests. Create test file, run it, fix if needed.",
        "deploy": "Build and deploy. Install deps, build, start services.",
        "analyze": "Analyze the code/project. Scan structure, read files, report findings.",
        "write_code": "Write code step by step. Create files, test, commit.",
        "general": "Complete the task using available tools.",
    }

    hint = task_hints.get(task_type, task_hints["general"])

    return (
        f"You are Hermes — an autonomous AI agent. Complete the task step by step.\n\n"
        f"AVAILABLE TOOLS ({len(relevant_tools)}):\n{tools_text}\n\n"
        f"TASK: {hint}\n\n"
        f"RULES:\n"
        f"1. Use ONLY the tools listed above\n"
        f"2. Call ONE tool at a time, wait for result, then decide next step\n"
        f"3. If a tool call fails, try a different approach\n"
        f"4. For file ops use workspace_file_ops with action parameter\n"
        f"5. When task is complete, call done with a summary\n"
        f"6. NEVER access files outside workspace\n"
        f"7. NEVER run dangerous commands (rm -rf /, format, shutdown)\n\n"
        f"WORKSPACE: {workspace}\n"
        f"DATE: {datetime.now().strftime('%Y-%m-%d')}\n\n"
        f"Call tools as JSON: {{\"tool_calls\": [{{\"function\": {{\"name\": \"tool_name\", \"arguments\": {{...}}}}}}]}}\n"
        f"Or use function calling format supported by your model."
    )
