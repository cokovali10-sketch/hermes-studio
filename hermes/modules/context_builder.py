"""Build context strings for LLM consumption."""


def build_context(project_meta: dict, task: str = "", memories: list[dict] | None = None) -> str:
    """Build a context string from project metadata, task, and memories."""
    parts = []

    if project_meta:
        parts.append(f"Project: {project_meta.get('name', 'unknown')}")
        parts.append(f"Path: {project_meta.get('path', 'unknown')}")

        langs = project_meta.get("languages", [])
        if langs:
            parts.append(f"Languages: {', '.join(langs)}")

        fws = project_meta.get("frameworks", [])
        if fws:
            parts.append(f"Frameworks: {', '.join(fws)}")

        deps = project_meta.get("dependencies", [])
        if deps:
            shown = deps[:25]
            parts.append(f"Dependencies ({len(deps)} total): {', '.join(shown)}")

        stats = project_meta.get("stats", {})
        if stats:
            parts.append(f"Files: {stats.get('total_files', 0)}, Dirs: {stats.get('total_dirs', 0)}, Size: {stats.get('total_size', 0)} bytes")

        file_index = project_meta.get("file_index", [])
        if file_index:
            parts.append(f"\nKey files ({len(file_index)} indexed):")
            for f in file_index[:30]:
                line_info = f" ({f['lines']} lines)" if f.get("lines") else ""
                parts.append(f"  {f['path']}{line_info}")

    if memories:
        by_type: dict[str, list] = {}
        for m in memories:
            by_type.setdefault(m.get("type", "unknown"), []).append(m.get("content", ""))
        for ftype, items in by_type.items():
            parts.append(f"\nStored {ftype} facts:")
            for item in items[:10]:
                parts.append(f"  - {item}")

    if task:
        parts.append(f"\nCurrent task: {task}")

    return "\n".join(parts) if parts else "No project context available."


def compress_context(context: str, max_chars: int = 8000) -> str:
    """Truncate context to fit within token limits."""
    if len(context) <= max_chars:
        return context

    lines = context.split("\n")
    header_lines = []
    detail_lines = []

    for line in lines:
        if not line.startswith("  "):
            header_lines.append(line)
        else:
            detail_lines.append(line)

    header = "\n".join(header_lines)
    remaining = max_chars - len(header) - 50

    if remaining > 0 and detail_lines:
        kept = []
        current = 0
        for line in detail_lines:
            if current + len(line) + 1 > remaining:
                break
            kept.append(line)
            current += len(line) + 1
        return header + "\n" + "\n".join(kept) + f"\n... ({len(detail_lines) - len(kept)} more lines truncated)"

    return header[:max_chars] + "\n... (truncated)"
