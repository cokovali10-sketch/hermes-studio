<div align="center">

# ◆ Hermes Studio

### Hermes Studio — Agentic Tool Suite with Vision

**No cloud. No API keys. No subscription. Just your machine.**

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Ollama](https://img.shields.io/badge/Ollama-Local%20Models-000?style=flat-square&logo=ollama&logoColor=white)](https://ollama.com)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078D4?style=flat-square&logo=windows&logoColor=white)]()

<br/>

![Hermes Studio](screenshots/main.png)

</div>

---

## What is this?

Hermes Studio v5 is an **autonomous AI agent** that builds complete software projects on your disk. External or local AI is the "brain", Hermes is its "hands".

| Model | Purpose | Size |
|-------|---------|------|
| **deepseek-r1:1.5b** | Reasoning, analysis, conversation | ~1.1 GB |
| **qwen2.5-coder:1.5b** | Code generation, HTML/CSS/JS, agent loop | ~986 MB |
| **llava:1.6-mistral** | Vision — analyze screenshots, images, UI | ~4.1 GB |

**Two modes:**
- **Chat** — ask anything, get answers (like a normal AI assistant)
- **Agent** — describe a project, Hermes builds it step by step with tools

---

## Features

### Agent Toolkit — 100 Tools

| Category | Tools | Description |
|----------|-------|-------------|
| **Core (15)** | `workspace_file_ops`, `execute_shell_command`, `git_checkpoint`, `analyze_project_structure`, `capture_screenshot`, `read_image`, `search_code`, `run_python`, `fetch_url`, `diff_apply`, `kill_process`, `env_info`, `list_templates`, `scaffold_project`, `done` | File ops, shell, git, search, vision |
| **Docker (10)** | `docker_build`, `docker_run`, `docker_stop`, `docker_list`, `docker_logs`, `docker_compose`, `docker_images`, `docker_exec`, `docker_stats`, `docker_clean` | Full container lifecycle management |
| **Security (10)** | `scan_secrets`, `scan_dependencies`, `check_ssl`, `port_scan`, `hash_file`, `check_headers`, `vuln_scan`, `check_permissions`, `generate_secret`, `audit_env` | Secret scanning, SSL checks, vuln analysis |
| **Profiling (8)** | `profile_function`, `benchmark_file`, `measure_time`, `memory_usage`, `cpu_info`, `disk_speed`, `network_latency`, `find_slow_code` | Performance profiling & bottleneck detection |
| **Database (8)** | `db_query`, `db_schema`, `db_backup`, `db_analyze`, `db_create_table`, `db_insert`, `db_export_csv`, `db_optimize` | SQL query, schema inspection, CSV export |
| **API Testing (10)** | `api_get`, `api_post`, `api_put`, `api_delete`, `api_patch`, `api_benchmark`, `api_validate`, `graphql_query`, `websocket_test`, `api_mock` | REST/GraphQL/WebSocket testing & mocking |
| **Documentation (8)** | `generate_readme`, `generate_changelog`, `generate_api_docs`, `generate_docstring`, `analyze_code_quality`, `find_todos`, `count_lines`, `generate_type_hints` | Auto-generate docs, analyze code quality |
| **Git Advanced (8)** | `git_log`, `git_diff`, `git_branch`, `git_blame`, `git_stash`, `git_stats`, `git_search`, `git_file_history` | Deep git history, blame, stats, search |
| **Backup (6)** | `backup_directory`, `restore_backup`, `list_backups`, `sync_directories`, `cleanup_old_files`, `find_duplicates` | Backup, sync, deduplication |
| **Migration (7)** | `csv_to_json`, `json_to_csv`, `xml_to_json`, `json_transform`, `merge_json`, `split_file`, `encode_decode` | Data format conversion & transformation |
| **Kubernetes (10)** | `k8s_get_pods`, `k8s_get_services`, `k8s_describe`, `k8s_logs`, `k8s_exec`, `k8s_scale`, `k8s_apply`, `k8s_delete`, `k8s_events`, `k8s_context` | K8s cluster management & introspection |

**Total: 100 tools** across 11 categories — extensible via plugin system.

### Core
- **Agent Loop** — iterative tool calling with OpenAI/Ollama compatible JSON Schema
- **Output Parser** — works even with small models that don't use function calling
- **Live Execution Stream** — real-time panel showing which tool is running
- **Smart Router** — automatic prompt classification (reasoning vs coding vs vision)
- **Vision Support** — analyze screenshots, images, UI elements with llava model
- **Screenshot Capture** — take screenshots directly from the agent
- **Code Search** — regex search across codebase with context
- **Project Templates** — scaffold React, FastAPI, Express, Static sites
- **Plugin System** — add custom tools via Python files in `plugins/`
- **Safety Protocol** — 30+ rules blocking dangerous commands, system file access, malicious code
- **Streaming responses** — text appears token by token
- **File upload** — attach images for vision analysis
- **100% offline** — works without internet, no data leaves your PC
- **D: drive storage** — models, workspace, backups on D:
- **One-click launch** — double-click `Hermes.bat` and done
- **Glassmorphism UI** — dark theme, Linear/Vercel style

---

## Что умеет Hermes v5.0

### Автономная разработка ПО

Hermes — это **автономный AI-агент**, который пишет код, запускает команды, делает коммиты и строит целые проекты без участия человека. Описываете задачу на естественном языке — Hermes выполняет её пошагово, используя 100 инструментов.

**Пример:**
```
Пользователь: "Создай React-приложение для задач с TypeScript и Tailwind"
  ↓
Hermes: пишет package.json, компоненты, стили, запускает npm install, делает коммит
```

### Что изменилось в v5.0

| Было (v3) | Стало (v5.0) |
|-----------|--------------|
| 15 инструментов | **100 инструментов** (+567%) |
| 3 категории | **11 категорий** |
| 1 Python-модуль | **12 Python-модулей** |
| ~899 строк кода | **~2800 строк** |

### Новые возможности

**Docker (10 инструментов)** — полное управление контейнерами: сборка образов, запуск/остановка контейнеров, docker-compose, статистика ресурсов, очистка.

**Безопасность (10 инструментов)** — сканирование секретов в коде, проверка SSL-сертификатов, сканирование портов, анализ уязвимостей, генерация секретных ключей, аудит окружения.

**Профилирование (8 инструментов)** — поиск узких мест: профилирование функций, бенчмаркинг файлов, анализ памяти, тест скорости диска, измерение сетевой задержки.

**Базы данных (8 инструментов)** — SQL-запросы, просмотр схемы, бэкап, экспорт в CSV, оптимизация.

**Тестирование API (10 инструментов)** — REST (GET/POST/PUT/DELETE/PATCH), GraphQL, WebSocket, бенчмаркинг, мок-серверы.

**Документация (8 инструментов)** — автогенерация README, CHANGELOG, API-документации, docstring, анализ качества кода, поиск TODO/FIXME, подсчёт строк, генерация type hints.

**Git (8 инструментов)** — история коммитов, diff, blame (кто изменил строку), stash, статистика репозитория, поиск по коммитам, история файлов.

**Бэкапы (6 инструментов)** — бэкап директорий, восстановление, синхронизация, очистка старых файлов, поиск дубликатов.

**Миграция данных (7 инструментов)** — конвертация CSV ↔ JSON, XML → JSON, трансформация, слияние, разделение файлов, кодирование/декодирование.

**Kubernetes (10 инструментов)** — управление подами, сервисами, описание ресурсов, логи, выполнение команд, масштабирование, применение манифестов, события кластера.

### Как это работает

Hermes загружает модули динамически через `_register_tool_module()`. Каждый модуль экспортирует схему инструментов (`TOOLS`) и реализацию (`functions`). Обёртка `_wrap_module_tool()` адаптирует вызовы — агент получает 100 инструментов в едином формате OpenAI Function Calling.

```
hermes/tools.py          ← реестр 100 инструментов
hermes/tools_docker.py   ← 10 инструментов Docker
hermes/tools_security.py ← 10 инструментов безопасности
hermes/tools_profiling.py ← 8 инструментов профилирования
hermes/tools_database.py ← 8 инструментов БД
hermes/tools_apitest.py  ← 10 инструментов тестирования API
hermes/tools_docs.py     ← 8 инструментов документации
hermes/tools_git_advanced.py ← 8 продвинутых git-инструментов
hermes/tools_backup.py   ← 6 инструментов бэкапов
hermes/tools_migration.py ← 7 инструментов миграции
hermes/tools_kubernetes.py ← 10 инструментов Kubernetes
```

---

## Quick Start

### 1. Install

```bash
git clone https://github.com/cokovali10-sketch/hermes-studio.git
cd hermes-studio
pip install -r requirements.txt
```

### 2. Download models

```bash
ollama pull deepseek-r1:1.5b
ollama pull qwen2.5-coder:1.5b
```

### 3. Launch

```bash
# Option A: double-click
Hermes.bat

# Option B: terminal
python launch.py
```

Browser opens automatically → **http://127.0.0.1:8765**

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│                    Browser                       │
│              (Edge / Chrome app)                 │
│  ┌──────────┐  ┌────────────────────────────┐   │
│  │  Chat UI  │  │  Live Execution Stream      │   │
│  └──────────┘  └────────────────────────────┘   │
└──────────────────────┬──────────────────────────┘
                       │ HTTP
┌──────────────────────▼──────────────────────────┐
│               server.py (:8765)                  │
│  ┌─────────────┐  ┌─────────────────────────┐   │
│  │ Smart Router │  │     Event Bus (SSE)     │   │
│  └──────┬──────┘  └─────────────────────────┘   │
│  ┌──────▼──────┐  ┌─────────────────────────┐   │
│  │ Agent Loop   │  │   Tool Dispatcher       │   │
│  │ (iterative)  │  │   ├─ file_ops           │   │
│  └──────┬──────┘  │   ├─ shell_command      │   │
│         │         │   ├─ git_checkpoint      │   │
│         │         │   ├─ project_analysis    │   │
│         │         │   └─ done                │   │
└─────────┼─────────┴─────────────────────────┘
          │ HTTP
┌─────────▼───────────────────────────────────────┐
│             Ollama (:11434)                     │
│  ┌──────────────┐  ┌─────────────────────────┐  │
│  │ deepseek-r1  │  │   qwen2.5-coder          │  │
│  │  (reasoning) │  │   (coding + agent)        │  │
│  └──────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

**How Agent Loop works:**

```
User: "Create a React todo app with TypeScript"
  ↓
Agent calls: workspace_file_ops(action="write", path="package.json", content=...)
Agent calls: workspace_file_ops(action="write", path="src/App.tsx", content=...)
Agent calls: execute_shell_command(command="npm install")
Agent calls: execute_shell_command(command="npm run build")
Agent calls: git_checkpoint(message="feat: initial todo app")
Agent calls: done(summary="React todo app created with TypeScript, Tailwind CSS")
```

---

## Project Structure

```
hermes-studio/
├── launch.py              # Single-instance launcher
├── server.py              # Backend + Agent Loop + Tool Dispatcher
├── setup_models.py        # Model downloader
├── config.json            # Configuration
├── requirements.txt       # Python dependencies
├── Hermes.bat             # One-click launcher
├── frontend/
│   └── index.html         # Glassmorphism UI + Agent Stream
├── hermes/                # Core package (12 modules)
│   ├── server.py          # aiohttp server, 30+ API endpoints
│   ├── agent.py           # Agent loop engine
│   ├── tools.py           # 100 tool registry + dispatcher
│   ├── tools_docker.py    # 10 Docker management tools
│   ├── tools_security.py  # 10 security scanning tools
│   ├── tools_profiling.py # 8 performance profiling tools
│   ├── tools_database.py  # 8 database operation tools
│   ├── tools_apitest.py   # 10 API testing tools
│   ├── tools_docs.py      # 8 documentation generation tools
│   ├── tools_git_advanced.py # 8 advanced git tools
│   ├── tools_backup.py    # 6 backup & sync tools
│   ├── tools_migration.py # 7 data migration tools
│   ├── tools_kubernetes.py # 10 Kubernetes management tools
│   ├── core.py            # Config, constants, paths
│   ├── router.py          # Request routing
│   ├── ollama.py          # Ollama client
│   ├── safety.py          # Safety rules engine
│   ├── bus.py             # Event bus (SSE)
│   └── templates.py       # Project templates
├── workspace/             # Agent builds projects here
├── backups/               # Auto-backups before file overwrites
└── screenshots/
    └── main.png           # App screenshot
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | HTML5 + CSS3 + Vanilla JS (Glassmorphism) |
| Backend | Python 3.10+ / aiohttp |
| AI Engine | Ollama (local inference) |
| Models | DeepSeek-R1 1.5B, Qwen2.5-Coder 1.5B |
| Agent | OpenAI/Ollama compatible Function Calling |
| Streaming | Server-Sent Events (SSE) |
| Storage | D: drive (models + workspace + backups) |

---

## System Requirements

- **OS:** Windows 10/11
- **RAM:** 8 GB minimum (16 GB recommended)
- **Disk:** 3 GB free (2 GB models + 1 GB app)
- **GPU:** Optional (CPU inference works fine for 1.5B models)

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Frontend UI |
| `GET` | `/stats` | Stats Dashboard |
| `GET` | `/api/health` | Health check + version |
| `GET` | `/api/models` | Installed models status |
| `GET` | `/api/tools` | Tool schemas (JSON Schema) |
| `GET` | `/api/stats` | Usage statistics |
| `GET` | `/api/workspace` | Workspace file tree |
| `GET` | `/api/plugins` | List loaded plugins |
| `POST` | `/api/plugins/reload` | Hot-reload plugins |
| `POST` | `/api/chat` | Chat (`?stream=1` for SSE) |
| `POST` | `/api/agent` | Agent loop with tool calling (SSE) |
| `POST` | `/api/analyze_image` | Vision analysis of uploaded image |
| `POST` | `/api/upload` | File upload |
| `GET` | `/api/events` | SSE event stream |

---

## Tool Schema (OpenAI Compatible)

```json
{
  "type": "function",
  "function": {
    "name": "workspace_file_ops",
    "description": "Read, write, create, delete, or list files",
    "parameters": {
      "type": "object",
      "properties": {
        "action": {"type": "string", "enum": ["read", "write", "create", "delete", "list", "list_tree"]},
        "path": {"type": "string"},
        "content": {"type": "string"}
      },
      "required": ["action", "path"]
    }
  }
}
```

---

## Configuration

Edit `config.json`:

```json
{
  "models": {
    "reasoning": "deepseek-r1:1.5b",
    "coding": "qwen2.5-coder:1.5b",
    "agent": "qwen2.5-coder:1.5b"
  },
  "server": { "port": 8765 },
  "paths": {
    "workspace": "D:/PortfolioProjects/Hermes/workspace",
    "backups": "D:/PortfolioProjects/Hermes/backups"
  },
  "tools": {
    "git_auto_commit": true,
    "backup_on_write": true
  }
}
```

---

## License

MIT — use it however you want.

---

<div align="center">

**Built with care. Runs on your machine. Your data stays yours.**

</div>
