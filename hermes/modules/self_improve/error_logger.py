"""Error logger — stores and retrieves errors, detects recurring patterns."""
from __future__ import annotations

import json
import pathlib
import time

from hermes.core import ROOT
from hermes.bus import bus

ERRORS_DIR = ROOT / ".hermes" / "errors"
ERRORS_DIR.mkdir(parents=True, exist_ok=True)

ERROR_FILE = ERRORS_DIR / "error_log.json"


class ErrorLogger:
    def __init__(self):
        self._errors: list[dict] = []
        self._load()

    def _load(self):
        if ERROR_FILE.exists():
            try:
                self._errors = json.loads(ERROR_FILE.read_text(encoding="utf-8"))
            except Exception:
                self._errors = []

    def _save(self):
        try:
            ERROR_FILE.write_text(json.dumps(self._errors[-500:], indent=2), encoding="utf-8")
        except Exception:
            pass

    def log_error(self, error_type: str, context: str, traceback_str: str = "") -> dict:
        entry = {
            "error_type": error_type,
            "context": context[:500],
            "traceback": traceback_str[:1000],
            "timestamp": time.time(),
            "count": 1,
        }
        for existing in self._errors:
            if existing["error_type"] == error_type and existing["context"] == context[:500]:
                existing["count"] += 1
                existing["last_seen"] = time.time()
                bus.emit("error.recurring", {"error_type": error_type, "count": existing["count"]})
                self._save()
                return {"success": True, "recurring": True, "count": existing["count"]}

        self._errors.append(entry)
        self._save()
        bus.emit("error.logged", {"error_type": error_type})
        return {"success": True, "recurring": False, "count": 1}

    def get_errors(self, limit: int = 100) -> list[dict]:
        return list(reversed(self._errors[-limit:]))

    def get_error_patterns(self) -> list[dict]:
        patterns: dict[str, dict] = {}
        for err in self._errors:
            key = err["error_type"]
            if key not in patterns:
                patterns[key] = {
                    "error_type": key,
                    "total_occurrences": 0,
                    "first_seen": err.get("timestamp", 0),
                    "last_seen": err.get("timestamp", 0),
                    "sample_context": err["context"],
                }
            patterns[key]["total_occurrences"] += err.get("count", 1)
            patterns[key]["last_seen"] = max(patterns[key]["last_seen"], err.get("last_seen", err.get("timestamp", 0)))

        sorted_patterns = sorted(patterns.values(), key=lambda p: p["total_occurrences"], reverse=True)
        return sorted_patterns

    def clear(self):
        self._errors.clear()
        self._save()


error_logger = ErrorLogger()
