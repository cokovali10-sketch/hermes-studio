"""File-based memory storage under ~/.hermes/memory/."""
import hashlib
import json
import pathlib

_MEMORY_ROOT = pathlib.Path.home() / ".hermes" / "memory"


def _ensure_dirs(project_id: str):
    (_MEMORY_ROOT / project_id).mkdir(parents=True, exist_ok=True)


def project_id_from_path(path: str) -> str:
    normalized = pathlib.Path(path).resolve().as_posix()
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def save_project_meta(project_id: str, meta: dict):
    _ensure_dirs(project_id)
    p = _MEMORY_ROOT / project_id / "meta.json"
    p.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def load_project_meta(project_id: str) -> dict:
    p = _MEMORY_ROOT / project_id / "meta.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_facts(project_id: str, facts: list[dict]):
    _ensure_dirs(project_id)
    p = _MEMORY_ROOT / project_id / "facts.json"
    p.write_text(json.dumps(facts, indent=2, ensure_ascii=False), encoding="utf-8")


def load_facts(project_id: str) -> list[dict]:
    p = _MEMORY_ROOT / project_id / "facts.json"
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def save_error_patterns(patterns: list[dict]):
    _MEMORY_ROOT.mkdir(parents=True, exist_ok=True)
    p = _MEMORY_ROOT / "error_patterns.json"
    p.write_text(json.dumps(patterns, indent=2, ensure_ascii=False), encoding="utf-8")


def load_error_patterns() -> list[dict]:
    p = _MEMORY_ROOT / "error_patterns.json"
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
