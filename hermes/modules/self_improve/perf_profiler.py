"""Performance profiler — track model performance and recommend best models."""
from __future__ import annotations

import json
import pathlib
import time

from hermes.core import ROOT

PERF_FILE = ROOT / ".hermes" / "model_performance.json"
PERF_FILE.parent.mkdir(parents=True, exist_ok=True)


class PerfProfiler:
    def __init__(self):
        self._records: list[dict] = []
        self._load()

    def _load(self):
        if PERF_FILE.exists():
            try:
                self._records = json.loads(PERF_FILE.read_text(encoding="utf-8"))
            except Exception:
                self._records = []

    def _save(self):
        try:
            PERF_FILE.write_text(json.dumps(self._records[-1000:], indent=2), encoding="utf-8")
        except Exception:
            pass

    def track_model_performance(self, model: str, task_type: str, success: bool, elapsed_ms: float):
        entry = {
            "model": model,
            "task_type": task_type,
            "success": success,
            "elapsed_ms": round(elapsed_ms, 2),
            "timestamp": time.time(),
        }
        self._records.append(entry)
        self._save()

    def get_model_scores(self) -> dict:
        scores: dict[str, dict] = {}
        for rec in self._records:
            model = rec["model"]
            if model not in scores:
                scores[model] = {"total": 0, "successes": 0, "total_ms": 0, "task_types": {}}
            s = scores[model]
            s["total"] += 1
            if rec["success"]:
                s["successes"] += 1
            s["total_ms"] += rec["elapsed_ms"]
            task = rec["task_type"]
            if task not in s["task_types"]:
                s["task_types"][task] = {"total": 0, "successes": 0, "total_ms": 0}
            ts = s["task_types"][task]
            ts["total"] += 1
            if rec["success"]:
                ts["successes"] += 1
            ts["total_ms"] += rec["elapsed_ms"]

        result = {}
        for model, s in scores.items():
            avg_ms = s["total_ms"] / s["total"] if s["total"] > 0 else 0
            success_rate = s["successes"] / s["total"] if s["total"] > 0 else 0
            task_scores = {}
            for task, ts in s["task_types"].items():
                task_scores[task] = {
                    "success_rate": round(ts["successes"] / ts["total"], 3) if ts["total"] > 0 else 0,
                    "avg_ms": round(ts["total_ms"] / ts["total"], 2) if ts["total"] > 0 else 0,
                    "count": ts["total"],
                }
            result[model] = {
                "success_rate": round(success_rate, 3),
                "avg_ms": round(avg_ms, 2),
                "total_calls": s["total"],
                "task_types": task_scores,
            }
        return result

    def get_recommendation(self, task_type: str) -> str:
        scores = self.get_model_scores()
        best_model = None
        best_score = -1

        for model, info in scores.items():
            task_info = info["task_types"].get(task_type)
            if task_info and task_info["count"] >= 2:
                score = task_info["success_rate"] * 1000 - task_info["avg_ms"] / 100
                if score > best_score:
                    best_score = score
                    best_model = model

        return best_model or ""


perf_profiler = PerfProfiler()
