"""Documentation generation tools for Hermes agent."""
import asyncio
import json
import os
import re
import ast

TOOLS = [
    {"name": "generate_readme", "description": "Generate README.md for a project", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Project root"}, "title": {"type": "string", "description": "Project title"}}, "required": ["path"]}},
    {"name": "generate_changelog", "description": "Generate CHANGELOG from git commits", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "limit": {"type": "integer", "default": 50}}}},
    {"name": "generate_api_docs", "description": "Generate API documentation from code", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Source file or directory"}, "format": {"type": "string", "default": "markdown"}}}},
    {"name": "generate_docstring", "description": "Generate docstrings for Python functions", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Python file"}}, "required": ["path"]}},
    {"name": "analyze_code_quality", "description": "Analyze code quality metrics", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "language": {"type": "string"}}}},
    {"name": "find_todos", "description": "Find all TODO/FIXME/HACK comments in codebase", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}},
    {"name": "count_lines", "description": "Count lines of code by language", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}},
    {"name": "generate_type_hints", "description": "Suggest Python type hints for a file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
]

functions = {}

async def generate_readme(args):
    path = args.get("path", ".")
    title = args.get("title", os.path.basename(os.path.abspath(path)))
    readme = f"# {title}\n\n"
    readme += "## Description\n\n[Project description]\n\n"
    if os.path.exists(os.path.join(path, "requirements.txt")):
        readme += "## Installation\n\n```bash\npip install -r requirements.txt\n```\n\n"
    elif os.path.exists(os.path.join(path, "package.json")):
        readme += "## Installation\n\n```bash\nnpm install\n```\n\n"
    readme += "## Usage\n\n[Usage instructions]\n\n"
    readme += "## Project Structure\n\n```\n"
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in {'.git', 'node_modules', '__pycache__', '.venv'}]
        level = root.replace(path, '').count(os.sep)
        if level > 2:
            continue
        indent = "  " * level
        readme += f"{indent}{os.path.basename(root)}/\n"
        subindent = "  " * (level + 1)
        for file in files[:5]:
            readme += f"{subindent}{file}\n"
        if len(files) > 5:
            readme += f"{subindent}... and {len(files) - 5} more\n"
    readme += "```\n\n"
    readme += "## License\n\n[License]\n"
    readme_path = os.path.join(path, "README.md")
    with open(readme_path, "w") as f:
        f.write(readme)
    return json.dumps({"success": True, "path": readme_path, "length": len(readme)})

async def generate_changelog(args):
    path = args.get("path", ".")
    limit = args.get("limit", 50)
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "log", f"--oneline", f"-{limit}",
            cwd=path, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        changelog = "# Changelog\n\n"
        for line in stdout.decode(errors="ignore").strip().split("\n"):
            if line:
                parts = line.split(" ", 1)
                if len(parts) == 2:
                    changelog += f"- {parts[1]} (`{parts[0]}`)\n"
        return json.dumps({"changelog": changelog, "commits": len(stdout.decode().strip().split("\n"))})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def generate_api_docs(args):
    path = args.get("path", ".")
    docs = []
    if os.path.isfile(path):
        files = [path]
    else:
        files = []
        for root, dirs, filenames in os.walk(path):
            dirs[:] = [d for d in dirs if d not in {'.git', 'node_modules'}]
            for f in filenames:
                if f.endswith(('.py', '.js', '.ts')):
                    files.append(os.path.join(root, f))
    for fpath in files[:50]:
        try:
            with open(fpath, 'r', errors='ignore') as f:
                content = f.read()
            if fpath.endswith('.py'):
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        docstring = ast.get_docstring(node)
                        args_list = [arg.arg for arg in node.args.args if arg.arg != 'self']
                        docs.append({
                            "file": fpath, "name": node.name, "type": "function",
                            "args": args_list, "docstring": docstring,
                        })
                    elif isinstance(node, ast.ClassDef):
                        docstring = ast.get_docstring(node)
                        methods = [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                        docs.append({
                            "file": fpath, "name": node.name, "type": "class",
                            "methods": methods, "docstring": docstring,
                        })
        except Exception:
            continue
    return json.dumps({"items": docs, "count": len(docs)})

async def generate_docstring(args):
    path = args["path"]
    try:
        with open(path, 'r') as f:
            content = f.read()
        tree = ast.parse(content)
        additions = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not ast.get_docstring(node):
                    args_list = [arg.arg for arg in node.args.args if arg.arg != 'self']
                    docstring = f'    """TODO: Add description.\n\n    Args:\n'
                    for a in args_list:
                        docstring += f"        {a}: TODO.\n"
                    docstring += '    """\n'
                    additions.append({"line": node.lineno, "name": node.name, "docstring": docstring})
        return json.dumps({"file": path, "missing_docstrings": len(additions), "suggestions": additions[:50]})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def analyze_code_quality(args):
    path = args.get("path", ".")
    metrics = {"files": 0, "total_lines": 0, "blank_lines": 0, "comment_lines": 0, "code_lines": 0, "avg_function_length": 0, "long_functions": [], "large_files": []}
    exts = {'.py': 'python', '.js': 'javascript', '.ts': 'typescript', '.go': 'go', '.rs': 'rust'}
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in {'.git', 'node_modules', '__pycache__'}]
        for fname in files:
            ext = os.path.splitext(fname)[1]
            if ext not in exts:
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, 'r', errors='ignore') as f:
                    lines = f.readlines()
                metrics["files"] += 1
                metrics["total_lines"] += len(lines)
                for line in lines:
                    stripped = line.strip()
                    if not stripped:
                        metrics["blank_lines"] += 1
                    elif stripped.startswith('#') or stripped.startswith('//') or stripped.startswith('/*'):
                        metrics["comment_lines"] += 1
                    else:
                        metrics["code_lines"] += 1
                if len(lines) > 500:
                    metrics["large_files"].append({"file": fpath, "lines": len(lines)})
            except Exception:
                continue
    return json.dumps(metrics)

async def find_todos(args):
    path = args.get("path", ".")
    todos = []
    patterns = [r'TODO', r'FIXME', r'HACK', r'XXX', r'BUG', r'NOTE']
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in {'.git', 'node_modules', '__pycache__'}]
        for fname in files:
            if fname.endswith(('.py', '.js', '.ts', '.jsx', '.tsx', '.go', '.rs', '.java', '.c', '.cpp', '.h')):
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, 'r', errors='ignore') as f:
                        for i, line in enumerate(f, 1):
                            for pattern in patterns:
                                if re.search(rf'\b{pattern}\b', line, re.IGNORECASE):
                                    todos.append({"file": fpath, "line": i, "type": pattern, "text": line.strip()[:120]})
                except Exception:
                    continue
    return json.dumps({"todos": todos, "count": len(todos)})

async def count_lines(args):
    path = args.get("path", ".")
    lang_map = {'.py': 'Python', '.js': 'JavaScript', '.ts': 'TypeScript', '.jsx': 'JSX', '.tsx': 'TSX', '.go': 'Go', '.rs': 'Rust', '.java': 'Java', '.c': 'C', '.cpp': 'C++', '.h': 'C Header', '.rb': 'Ruby', '.php': 'PHP', '.sh': 'Shell', '.sql': 'SQL', '.html': 'HTML', '.css': 'CSS', '.json': 'JSON', '.yaml': 'YAML', '.yml': 'YAML', '.md': 'Markdown', '.toml': 'TOML'}
    stats = {}
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in {'.git', 'node_modules', '__pycache__', 'venv', '.venv'}]
        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            lang = lang_map.get(ext, ext)
            if lang:
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, 'r', errors='ignore') as f:
                        lines = len(f.readlines())
                    stats[lang] = stats.get(lang, {"files": 0, "lines": 0})
                    stats[lang]["files"] += 1
                    stats[lang]["lines"] += lines
                except Exception:
                    continue
    return json.dumps({"languages": stats, "total_files": sum(v["files"] for v in stats.values()), "total_lines": sum(v["lines"] for v in stats.values())})

async def generate_type_hints(args):
    path = args["path"]
    suggestions = []
    try:
        with open(path, 'r') as f:
            content = f.read()
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for arg in node.args.args:
                    if arg.arg != 'self' and arg.annotation is None:
                        suggestions.append({"function": node.name, "argument": arg.arg, "line": node.lineno, "suggestion": "Any"})
                if node.returns is None:
                    suggestions.append({"function": node.name, "argument": "return", "line": node.lineno, "suggestion": "Any"})
    except Exception as e:
        return json.dumps({"error": str(e)})
    return json.dumps({"file": path, "suggestions": suggestions, "count": len(suggestions)})

functions = {
    "generate_readme": generate_readme, "generate_changelog": generate_changelog,
    "generate_api_docs": generate_api_docs, "generate_docstring": generate_docstring,
    "analyze_code_quality": analyze_code_quality, "find_todos": find_todos,
    "count_lines": count_lines, "generate_type_hints": generate_type_hints,
}
