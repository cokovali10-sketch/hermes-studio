"""Memory engine for project context and fact storage."""
import json
import pathlib
import time

from hermes.modules.memory_store import (
    load_facts,
    load_project_meta,
    save_facts,
    save_project_meta,
)
from hermes.modules.project_scanner import scan_project_structure

FACT_TYPES = {"structure", "pattern", "error", "preference", "dependency"}


class MemoryEngine:
    def __init__(self):
        self._scanned: set[str] = set()

    async def scan_project(self, project_path: str) -> dict:
        meta = scan_project_structure(project_path)
        project_id = meta["project_id"]
        save_project_meta(project_id, meta)
        self._scanned.add(project_id)
        return meta

    async def remember_fact(self, project_id: str, fact_type: str, content: str) -> dict:
        if fact_type not in FACT_TYPES:
            return {"error": f"Invalid fact_type: {fact_type}. Must be one of: {FACT_TYPES}"}

        facts = load_facts(project_id)
        fact = {
            "id": f"{project_id}_{len(facts)}_{int(time.time())}",
            "type": fact_type,
            "content": content,
            "created_at": time.time(),
        }
        facts.append(fact)
        save_facts(project_id, facts)
        return {"success": True, "fact": fact}

    async def recall_facts(self, project_id: str, query: str) -> list[dict]:
        facts = load_facts(project_id)
        if not query:
            return facts

        query_lower = query.lower()
        scored = []
        for f in facts:
            score = 0
            content_lower = f["content"].lower()
            if query_lower in content_lower:
                score += 10
            for word in query_lower.split():
                if word in content_lower:
                    score += 2
            if f["type"] == "error":
                score += 1
            if score > 0:
                scored.append((score, f))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [s[1] for s in scored]

    async def get_project_context(self, project_id: str) -> str:
        meta = load_project_meta(project_id)
        facts = load_facts(project_id)

        parts = []
        if meta:
            parts.append(f"Project: {meta.get('name', project_id)}")
            if meta.get("languages"):
                parts.append(f"Languages: {', '.join(meta['languages'])}")
            if meta.get("frameworks"):
                parts.append(f"Frameworks: {', '.join(meta['frameworks'])}")
            if meta.get("dependencies"):
                deps = meta["dependencies"]
                if isinstance(deps, list):
                    parts.append(f"Dependencies: {', '.join(deps[:20])}")

        if facts:
            by_type: dict[str, list] = {}
            for f in facts:
                by_type.setdefault(f["type"], []).append(f["content"])
            for ftype, items in by_type.items():
                parts.append(f"\n{ftype.upper()} facts:")
                for item in items[:10]:
                    parts.append(f"  - {item}")

        return "\n".join(parts) if parts else "No context available for this project."

    async def list_memories(self, project_id: str) -> list[dict]:
        return load_facts(project_id)

    def has_scanned(self, project_id: str) -> bool:
        return project_id in self._scanned


memory_engine = MemoryEngine()
