"""Code intelligence tools for the Hermes agent."""
import json

from hermes.modules.code_intel.parser import parse_file
from hermes.modules.code_intel.semantic import semantic_search
from hermes.modules.code_intel.refactor import (
    rename_symbol,
    extract_function,
    find_definitions,
    find_references,
)
from hermes.modules.code_intel.deps import dep_graph
from hermes.modules.code_intel.api_discovery import discover_api_endpoints


async def tool_ast_parse(path: str) -> dict:
    result = parse_file(path)
    result["success"] = "error" not in result
    return result


async def tool_semantic_search(query: str, path: str = "", max_results: int = 10) -> dict:
    try:
        results = semantic_search.search(query, path, max_results)
        return {
            "success": True,
            "results": results,
            "count": len(results),
            "query": query,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def tool_find_definitions(name: str, path: str) -> dict:
    results = find_definitions(name, path)
    has_error = any("error" in r for r in results)
    return {
        "success": not has_error,
        "definitions": results,
        "count": len(results),
    }


async def tool_find_references(name: str, path: str) -> dict:
    results = find_references(name, path)
    has_error = any("error" in r for r in results)
    return {
        "success": not has_error,
        "references": results,
        "count": len(results),
    }


async def tool_rename_symbol(path: str, old_name: str, new_name: str) -> dict:
    try:
        changes = rename_symbol(path, old_name, new_name)
        has_error = any("error" in c for c in changes)
        total_edits = sum(len(c.get("changes", [])) for c in changes)
        return {
            "success": not has_error,
            "changes": changes,
            "files_modified": len(changes),
            "total_edits": total_edits,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def tool_extract_function(path: str, start_line: int, end_line: int, func_name: str) -> dict:
    try:
        result = extract_function(path, start_line, end_line, func_name)
        result["success"] = "error" not in result
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


async def tool_get_dependency_graph(path: str) -> dict:
    try:
        result = dep_graph.build_graph(path)
        result["success"] = "error" not in result
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


async def tool_discover_api_endpoints(path: str) -> dict:
    try:
        endpoints = discover_api_endpoints(path)
        return {
            "success": True,
            "endpoints": endpoints,
            "count": len(endpoints),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


CODE_INTEL_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "ast_parse",
            "description": "Parse a source file into an AST representation. Supports Python, JS/TS, HTML, CSS.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the source file"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "semantic_search",
            "description": "Search codebase by semantic similarity using TF-IDF scoring. Indexes files automatically.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "path": {"type": "string", "description": "Directory to search in"},
                    "max_results": {"type": "integer", "default": 10},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_definitions",
            "description": "Find where a symbol (function, class, variable) is defined across the codebase.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Symbol name to find"},
                    "path": {"type": "string", "description": "Root directory to search"},
                },
                "required": ["name", "path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_references",
            "description": "Find all usages/references to a symbol across the codebase.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Symbol name to find references for"},
                    "path": {"type": "string", "description": "Root directory to search"},
                },
                "required": ["name", "path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rename_symbol",
            "description": "Rename a symbol across all files in a directory. Creates backups before modifying.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Root directory or file to rename in"},
                    "old_name": {"type": "string", "description": "Current symbol name"},
                    "new_name": {"type": "string", "description": "New symbol name"},
                },
                "required": ["path", "old_name", "new_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "extract_function",
            "description": "Extract a block of code into a new function. Replaces the block with a function call.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File to modify"},
                    "start_line": {"type": "integer", "description": "First line to extract (1-indexed)"},
                    "end_line": {"type": "integer", "description": "Last line to extract (inclusive)"},
                    "func_name": {"type": "string", "description": "Name for the new function"},
                },
                "required": ["path", "start_line", "end_line", "func_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_dependency_graph",
            "description": "Build a dependency graph showing imports between files in a project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Project root directory"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "discover_api_endpoints",
            "description": "Discover API route endpoints in a project (FastAPI, Flask, Express).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Project root directory"},
                },
                "required": ["path"],
            },
        },
    },
]

CODE_INTEL_TOOL_MAP = {
    "ast_parse": tool_ast_parse,
    "semantic_search": tool_semantic_search,
    "find_definitions": tool_find_definitions,
    "find_references": tool_find_references,
    "rename_symbol": tool_rename_symbol,
    "extract_function": tool_extract_function,
    "get_dependency_graph": tool_get_dependency_graph,
    "discover_api_endpoints": tool_discover_api_endpoints,
}
