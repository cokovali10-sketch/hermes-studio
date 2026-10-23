"""Advanced Git tools for Hermes agent."""
import asyncio
import json
# --- константы вынесены FORGE refactor ---
CONST_3 = 3
CONST_4 = 4
CONST_20 = 20
CONST_30 = 30


TOOLS = [
    {"name": "git_log", "description": "Show git commit history with details", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "limit": {"type": "integer", "default": CONST_20}, "author": {"type": "string"}, "since": {"type": "string", "description": "Date filter (e.g. '2 weeks ago')"}}}},
    {"name": "git_diff", "description": "Show git diff (staged, unstaged, or between branches)", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "target": {"type": "string", "description": "Branch or commit to diff against"}}}},
    {"name": "git_branch", "description": "List, create, or delete branches", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "action": {"type": "string", "description": "list, create, delete, checkout"}, "name": {"type": "string"}}}},
    {"name": "git_blame", "description": "Show who changed each line of a file", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "File path"}}, "required": ["path"]}},
    {"name": "git_stash", "description": "Stash changes", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "action": {"type": "string", "description": "save, list, pop, drop"}}}},
    {"name": "git_stats", "description": "Show git statistics (commits per author, lines changed)", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "days": {"type": "integer", "default": CONST_30}}}},
    {"name": "git_search", "description": "Search git log for commits matching a pattern", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "query": {"type": "string"}, "limit": {"type": "integer", "default": CONST_20}}, "required": ["query"]}},
    {"name": "git_file_history", "description": "Show commit history for a specific file", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "File path"}, "limit": {"type": "integer", "default": 10}}, "required": ["path"]}},
]

functions = {}

async def _run_git(args, *cmd):
    path = args.get("path", ".")
    full_cmd = ["git", "-C", path] + list(cmd)
    try:
        proc = await asyncio.create_subprocess_exec(
            *full_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=CONST_30)
        return stdout.decode(errors="ignore").strip()
    except Exception as e:
        return str(e)

async def git_log(args):
    limit = args.get("limit", CONST_20)
    author = args.get("author", "")
    since = args.get("since", "")
    cmd = ["log", f"--max-count={limit}", "--pretty=format:%h|%an|%ae|%ad|%s", "--date=short"]
    if author:
        cmd.extend([f"--author={author}"])
    if since:
        cmd.extend([f"--since={since}"])
    output = await _run_git(args, *cmd)
    commits = []
    for line in output.split("\n"):
        if line:
            parts = line.split("|", CONST_4)
            if len(parts) == 5:
                commits.append({"hash": parts[0], "author": parts[1], "email": parts[2], "date": parts[CONST_3], "message": parts[CONST_4]})
    return json.dumps({"commits": commits, "count": len(commits)})

async def git_diff(args):
    target = args.get("target", "")
    if target:
        output = await _run_git(args, "diff", target)
    else:
        output = await _run_git(args, "diff")
    files = []
    for line in output.split("\n"):
        if line.startswith("diff --git"):
            parts = line.split()
            if len(parts) >= CONST_4:
                files.append(parts[CONST_3].lstrip("a/"))
    return json.dumps({"diff": output[-5000:], "files_changed": files, "lines": len(output.split("\n"))})

async def git_branch(args):
    action = args.get("action", "list")
    name = args.get("name", "")
    if action == "list":
        output = await _run_git(args, "branch", "-a")
        branches = [line.strip().strip("* ") for line in output.split("\n") if line.strip()]
        return json.dumps({"branches": branches})
    elif action == "create" and name:
        output = await _run_git(args, "checkout", "-b", name)
        return json.dumps({"success": "error" not in output.lower(), "output": output})
    elif action == "delete" and name:
        output = await _run_git(args, "branch", "-D", name)
        return json.dumps({"success": "error" not in output.lower(), "output": output})
    elif action == "checkout" and name:
        output = await _run_git(args, "checkout", name)
        return json.dumps({"success": "error" not in output.lower(), "output": output})
    return json.dumps({"error": f"Invalid action: {action}"})

async def git_blame(args):
    path = args["path"]
    output = await _run_git(args, "blame", "--line-porcelain", path)
    lines = []
    current = {}
    for line in output.split("\n"):
        if line.startswith("author "):
            current["author"] = line[7:]
        elif line.startswith("author-time "):
            current["time"] = line[12:]
        elif line.startswith("\t"):
            current["code"] = line[1:]
            lines.append(current)
            current = {}
    return json.dumps({"file": path, "lines": lines[-200:], "count": len(lines)})

async def git_stash(args):
    action = args.get("action", "save")
    if action == "save":
        output = await _run_git(args, "stash", "push", "-m", "Hermes stash")
    elif action == "list":
        output = await _run_git(args, "stash", "list")
    elif action == "pop":
        output = await _run_git(args, "stash", "pop")
    elif action == "drop":
        output = await _run_git(args, "stash", "drop")
    else:
        output = await _run_git(args, "stash")
    return json.dumps({"action": action, "output": output})

async def git_stats(args):
    days = args.get("days", CONST_30)
    since = f"{days} days ago"
    author_output = await _run_git(args, "shortlog", "-sn", f"--since={since}")
    authors = []
    for line in author_output.split("\n"):
        line = line.strip()
        if line:
            parts = line.split("\t", 1)
            if len(parts) == 2:
                authors.append({"commits": int(parts[0].strip()), "author": parts[1].strip()})
    stat_output = await _run_git(args, "diff", "--shortstat", f"HEAD~{min(days, 50)}")
    return json.dumps({"period_days": days, "authors": authors, "stat": stat_output})

async def git_search(args):
    query = args["query"]
    limit = args.get("limit", CONST_20)
    output = await _run_git(args, "log", f"--max-count={limit}", f"--grep={query}", "--pretty=format:%h|%ad|%s", "--date=short")
    results = []
    for line in output.split("\n"):
        if line:
            parts = line.split("|", 2)
            if len(parts) == CONST_3:
                results.append({"hash": parts[0], "date": parts[1], "message": parts[2]})
    return json.dumps({"query": query, "results": results, "count": len(results)})

async def git_file_history(args):
    path = args["path"]
    limit = args.get("limit", 10)
    output = await _run_git(args, "log", f"--max-count={limit}", "--pretty=format:%h|%an|%ad|%s", "--date=short", "--", path)
    history = []
    for line in output.split("\n"):
        if line:
            parts = line.split("|", CONST_3)
            if len(parts) == CONST_4:
                history.append({"hash": parts[0], "author": parts[1], "date": parts[2], "message": parts[CONST_3]})
    return json.dumps({"file": path, "history": history, "count": len(history)})

functions = {
    "git_log": git_log, "git_diff": git_diff, "git_branch": git_branch,
    "git_blame": git_blame, "git_stash": git_stash, "git_stats": git_stats,
    "git_search": git_search, "git_file_history": git_file_history,
}
