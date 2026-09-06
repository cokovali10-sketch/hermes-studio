# Hermes v5.0 — Changelog

## v5.0 (2026-09-06)

### Что нового: 100 инструментов

Hermes обновлён до **100 инструментов** — от 15 до 100 (+567%).

---

### Категории инструментов

#### Core (15 инструментов)
Базовые инструменты агента для работы с файлами, командной строкой, git, поиском, vision.

| Инструмент | Описание |
|------------|----------|
| `workspace_file_ops` | Чтение, запись, создание, удаление, список, grep, search_replace, read_lines |
| `execute_shell_command` | Запуск команд с таймаутом |
| `git_checkpoint` | Автокоммит после каждого шага |
| `analyze_project_structure` | Сканирование дерева файлов |
| `capture_screenshot` | Скриншоты экрана |
| `read_image` | Чтение изображений для vision |
| `search_code` | Regex-поиск по коду |
| `run_python` | Запуск Python-кода |
| `fetch_url` | HTTP GET/POST запросы |
| `diff_apply` | Применение unified diff |
| `kill_process` | Убийство процессов |
| `env_info` | Информация о системе |
| `list_templates` | Список шаблонов |
| `scaffold_project` | Создание проекта из шаблона |
| `done` | Завершение задачи |

#### Docker (10 инструментов)
Полное управление жизненным циклом Docker-контейнеров.

| Инструмент | Описание |
|------------|----------|
| `docker_build` | Сборка Docker-образа |
| `docker_run` | Запуск контейнера |
| `docker_stop` | Остановка контейнера |
| `docker_list` | Список контейнеров |
| `docker_logs` | Логи контейнера |
| `docker_compose` | Управление docker-compose |
| `docker_images` | Список образов |
| `docker_exec` | Выполнение команды в контейнере |
| `docker_stats` | Статистика ресурсов |
| `docker_clean` | Очистка неиспользуемых ресурсов |

#### Security (10 инструментов)
Сканирование секретов, проверка SSL, анализ уязвимостей.

| Инструмент | Описание |
|------------|----------|
| `scan_secrets` | Поиск секретов в коде |
| `scan_dependencies` | Проверка зависимостей |
| `check_ssl` | Проверка SSL-сертификатов |
| `port_scan` | Сканирование портов |
| `hash_file` | Хеширование файлов |
| `check_headers` | Проверка HTTP-заголовков |
| `vuln_scan` | Сканирование уязвимостей |
| `check_permissions` | Проверка прав доступа |
| `generate_secret` | Генерация секретных ключей |
| `audit_env` | Аудит окружения |

#### Profiling (8 инструментов)
Профилирование производительности и поиск узких мест.

| Инструмент | Описание |
|------------|----------|
| `profile_function` | Профилирование функции |
| `benchmark_file` | Бенчмаркинг файла |
| `measure_time` | Измерение времени выполнения |
| `memory_usage` | Анализ использования памяти |
| `cpu_info` | Информация о CPU |
| `disk_speed` | Тест скорости диска |
| `network_latency` | Измерение сетевой задержки |
| `find_slow_code` | Поиск медленного кода |

#### Database (8 инструментов)
Работа с SQL-базами данных, экспорт в CSV.

| Инструмент | Описание |
|------------|----------|
| `db_query` | Выполнение SQL-запросов |
| `db_schema` | Просмотр схемы БД |
| `db_backup` | Бэкап базы данных |
| `db_analyze` | Анализ БД |
| `db_create_table` | Создание таблиц |
| `db_insert` | Вставка данных |
| `db_export_csv` | Экспорт в CSV |
| `db_optimize` | Оптимизация БД |

#### API Testing (10 инструментов)
Тестирование REST, GraphQL, WebSocket API.

| Инструмент | Описание |
|------------|----------|
| `api_get` | GET-запрос |
| `api_post` | POST-запрос |
| `api_put` | PUT-запрос |
| `api_delete` | DELETE-запрос |
| `api_patch` | PATCH-запрос |
| `api_benchmark` | Бенчмаркинг API |
| `api_validate` | Валидация ответа |
| `graphql_query` | GraphQL-запрос |
| `websocket_test` | Тест WebSocket |
| `api_mock` | Мок-сервер |

#### Documentation (8 инструментов)
Автогенерация документации и анализ качества кода.

| Инструмент | Описание |
|------------|----------|
| `generate_readme` | Генерация README.md |
| `generate_changelog` | Генерация CHANGELOG.md |
| `generate_api_docs` | Генерация API-документации |
| `generate_docstring` | Генерация docstring |
| `analyze_code_quality` | Анализ качества кода |
| `find_todos` | Поиск TODO/FIXME |
| `count_lines` | Подсчёт строк кода |
| `generate_type_hints` | Генерация type hints |

#### Git Advanced (8 инструментов)
Продвинутая работа с git — история, blame, статистика.

| Инструмент | Описание |
|------------|----------|
| `git_log` | История коммитов |
| `git_diff` | Разница между коммитами |
| `git_branch` | Управление ветками |
| `git_blame` | Кто изменил строку |
| `git_stash` | Stash операции |
| `git_stats` | Статистика репозитория |
| `git_search` | Поиск в коммитах |
| `git_file_history` | История файла |

#### Backup (6 инструментов)
Бэкапы, синхронизация, дедупликация.

| Инструмент | Описание |
|------------|----------|
| `backup_directory` | Бэкап директории |
| `restore_backup` | Восстановление из бэкапа |
| `list_backups` | Список бэкапов |
| `sync_directories` | Синхронизация директорий |
| `cleanup_old_files` | Очистка старых файлов |
| `find_duplicates` | Поиск дубликатов |

#### Migration (7 инструментов)
Конвертация данных между форматами.

| Инструмент | Описание |
|------------|----------|
| `csv_to_json` | CSV → JSON |
| `json_to_csv` | JSON → CSV |
| `xml_to_json` | XML → JSON |
| `json_transform` | Трансформация JSON |
| `merge_json` | Слияние JSON |
| `split_file` | Разделение файла |
| `encode_decode` | Кодирование/декодирование |

#### Kubernetes (10 инструментов)
Управление кластером Kubernetes.

| Инструмент | Описание |
|------------|----------|
| `k8s_get_pods` | Список подов |
| `k8s_get_services` | Список сервисов |
| `k8s_describe` | Описание ресурса |
| `k8s_logs` | Логи пода |
| `k8s_exec` | Выполнение команды в поде |
| `k8s_scale` | Масштабирование |
| `k8s_apply` | Применение манифеста |
| `k8s_delete` | Удаление ресурса |
| `k8s_events` | События кластера |
| `k8s_context` | Переключение контекста |

---

### Архитектура обновления

```
hermes/tools.py          — реестр 100 инструментов + диспетчер
hermes/tools_docker.py   — 10 инструментов Docker
hermes/tools_security.py — 10 инструментов безопасности
hermes/tools_profiling.py — 8 инструментов профилирования
hermes/tools_database.py — 8 инструментов БД
hermes/tools_apitest.py  — 10 инструментов тестирования API
hermes/tools_docs.py     — 8 инструментов документации
hermes/tools_git_advanced.py — 8 продвинутых git-инструментов
hermes/tools_backup.py   — 6 инструментов бэкапов
hermes/tools_migration.py — 7 инструментов миграции
hermes/tools_kubernetes.py — 10 инструментов Kubernetes
```

Динамическая регистрация модулей через `_register_tool_module()` — каждый модуль экспортирует `TOOLS` (схема) и `functions` (реализация). Обёртка `_wrap_module_tool()` адаптирует вызовы: `(args dict) → JSON string` → `(kwargs) → dict`.

---

### Итого

| Метрика | Было | Стало |
|---------|------|-------|
| Инструментов | 15 | **100** |
| Категорий | 3 | **11** |
| Python-модулей | 1 | **12** |
| Строк кода | ~899 | **~2800** |
