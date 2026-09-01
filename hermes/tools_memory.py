"""Memory system tools for the Hermes agent."""
import json

from hermes.modules.memory import memory_engine
from hermes.modules.memory_store import project_id_from_path
from hermes.modules.context_builder import build_context, compress_context


async def tool_remember_fact(project_id: str, fact_type: str, content: str) -> dict:
    return await memory_engine.remember_fact(project_id, fact_type, content)


async def tool_recall_facts(project_id: str, query: str = "") -> dict:
    facts = await memory_engine.recall_facts(project_id, query)
    return {"facts": facts, "count": len(facts), "success": True}


async def tool_scan_project_memory(project_path: str) -> dict:
    meta = await memory_engine.scan_project(project_path)
    return {"success": True, "meta": meta}


async def tool_get_project_context(project_path: str, task: str = "") -> dict:
    pid = project_id_from_path(project_path)
    meta = await memory_engine.scan_project(project_path) if not memory_engine.has_scanned(pid) else None
    if meta is None:
        from hermes.modules.memory_store import load_project_meta
        meta = load_project_meta(pid)

    facts = await memory_engine.list_memories(pid)
    raw = build_context(meta, task, facts)
    compressed = compress_context(raw)
    return {"context": compressed, "project_id": pid, "success": True}


async def tool_list_memories(project_path: str) -> dict:
    pid = project_id_from_path(project_path)
    facts = await memory_engine.list_memories(pid)
    return {"facts": facts, "count": len(facts), "project_id": pid, "success": True}


MEMORY_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "remember_fact",
            "description": "Store a fact about a project. Fact types: structure, pattern, error, preference, dependency.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "description": "Project ID from scan"},
                    "fact_type": {"type": "string", "enum": ["structure", "pattern", "error", "preference", "dependency"]},
                    "content": {"type": "string", "description": "The fact to remember"},
                },
                "required": ["project_id", "fact_type", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall_facts",
            "description": "Retrieve relevant facts for a project. Optionally filter by query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "description": "Project ID"},
                    "query": {"type": "string", "description": "Optional search query to filter facts"},
                },
                "required": ["project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scan_project_memory",
            "description": "Deep scan a project directory and build a memory index of languages, frameworks, and structure.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_path": {"type": "string", "description": "Absolute or relative path to the project"},
                },
                "required": ["project_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_project_context",
            "description": "Get summarized context for a project including structure, dependencies, and stored memories.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_path": {"type": "string", "description": "Path to the project"},
                    "task": {"type": "string", "description": "Optional task description for context tailoring"},
                },
                "required": ["project_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_memories",
            "description": "List all stored memories/facts for a project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_path": {"type": "string", "description": "Path to the project"},
                },
                "required": ["project_path"],
            },
        },
    },
]

MEMORY_TOOL_MAP = {
    "remember_fact": tool_remember_fact,
    "recall_facts": tool_recall_facts,
    "scan_project_memory": tool_scan_project_memory,
    "get_project_context": tool_get_project_context,
    "list_memories": tool_list_memories,
}
