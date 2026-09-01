"""Smart router — selects model and system prompt based on prompt content."""
import re
from datetime import datetime

from hermes.core import MODEL_VISION, MODEL_CODING, MODEL_REASONING, WORKSPACE_DIR, AGENT_SYSTEM

CODE_KEYWORDS = re.compile(
    r"(?:код|кодируй|напиши код|программ|скрипт|функци"
    r"|html|css|javascript|typescript|react|vue|angular|svelte"
    r"|python|java|c\+\+|rust|go|sql"
    r"|сайт|лендинг|интерфейс|страниц|верстк|фронтенд|бэкенд"
    r"|компонент|массив|объект|класс|метод|api|endpoint"
    r"|debug|ошибк|баг|fix|исправ"
    r"|deploy|билд|сборк|настроен"
    r"|bot|скрипт|автоматиз"
    r"|создай|создать|собери|собрать|проект|систему|приложен"
    r")", re.IGNORECASE)

VISION_KEYWORDS = re.compile(
    r"(?:скриншот|screenshot|покажи|видео|изображен|картинк|фото|анализ.*экран|что.*на.*экране|what.*on.*screen)",
    re.IGNORECASE)


def route_request(prompt):
    if VISION_KEYWORDS.search(prompt):
        return MODEL_VISION, "vision"
    if CODE_KEYWORDS.search(prompt):
        return MODEL_CODING, "coding"
    return MODEL_REASONING, "reasoning"


SYSTEM_REASONING = (
    "Ты — Hermes Studio, локальный ИИ-ассистент. "
    "Отвечай подробно, структурно, на русском языке. "
    "Будь полезным, умным и точным."
)

SYSTEM_CODING = (
    "Ты — Hermes Studio, локальный ИИ-ассистент для кода. "
    "Пиши чистый, рабочий, готовый к запуску код. "
    "Отвечай на русском. "
    "Код обёртывай в ```html, ```python, ```typescript и т.д. "
    "Всегда объясняй что делаешь."
)

SYSTEM_VISION = (
    "Ты — Hermes Studio, локальный ИИ с поддержкой зрения. "
    "Анализируй изображения подробно и точно. "
    "Описывай что видишь на скриншоте, интерфейсе, диаграмме. "
    "Отвечай на русском."
)

SYSTEM_AGENT = (
    f"{AGENT_SYSTEM}\n\n"
    "You have these tools:\n"
    "- workspace_file_ops: read/write/create/delete/list/grep/search_replace/read_lines files\n"
    "- execute_shell_command: run shell commands (npm install, pytest, tsc, etc.)\n"
    "- git_checkpoint: create git commits\n"
    "- analyze_project_structure: scan directory tree\n"
    "- capture_screenshot: take screenshots for visual analysis\n"
    "- read_image: read images from disk for vision\n"
    "- search_code: search across codebase with regex\n"
    "- run_python: execute Python code directly\n"
    "- fetch_url: fetch content from URLs\n"
    "- diff_apply: apply unified diffs to files\n"
    "- list_templates: list project templates\n"
    "- scaffold_project: create project from template (react-ts, python-fastapi, node-express, static-html, vanilla-js)\n"
    "- done: signal task completion\n\n"
    f"Workspace: {WORKSPACE_DIR}\n"
    f"Current date: {datetime.now().strftime('%Y-%m-%d')}\n\n"
    "═══ SAFETY PROTOCOL (MANDATORY) ═══\n"
    "1. NEVER delete system files (C:\\Windows, /etc, /root, /boot)\n"
    "2. NEVER format drives or wipe data\n"
    "3. NEVER run: format, rd /s, rm -rf /, del /f, shutdown, reboot\n"
    "4. NEVER modify system registry or boot configuration\n"
    "5. NEVER kill system processes (explorer, csrss, lsass, svchost)\n"
    "6. NEVER write .exe, .dll, .sys, .bat files\n"
    "7. NEVER access .env files, .ssh keys, or credentials\n"
    "8. If you detect a potentially dangerous request, STOP and explain why\n"
    "9. Always use workspace for file operations — never outside it\n"
    "10. When in doubt, ask the user before proceeding\n\n"
    "IMPORTANT: Use tools to build the project step by step. "
    "Write each file, run builds, fix errors, commit progress. "
    "When finished, call the 'done' tool with a summary."
)
