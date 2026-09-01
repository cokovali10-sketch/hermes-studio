"""Multi-language AST parser using stdlib only."""
import ast
import re
import pathlib
import html.parser
from typing import Any


def parse_file(path: str) -> dict[str, Any]:
    p = pathlib.Path(path)
    if not p.exists():
        return {"error": f"File not found: {path}"}

    ext = p.suffix.lower()
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"error": f"Cannot read file: {e}"}

    if ext == ".py":
        return _parse_python(content, str(p))
    elif ext in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"):
        return _parse_javascript(content, str(p))
    elif ext in (".html", ".htm"):
        return _parse_html(content, str(p))
    elif ext in (".css", ".scss", ".less"):
        return _parse_css(content, str(p))
    else:
        return {"error": f"Unsupported file type: {ext}", "path": str(p)}


def _parse_python(content: str, path: str) -> dict[str, Any]:
    try:
        tree = ast.parse(content, filename=path)
    except SyntaxError as e:
        return {"error": f"Syntax error: {e}", "path": path}

    nodes = []
    for node in ast.iter_child_nodes(tree):
        parsed = _python_node_to_dict(node)
        if parsed:
            nodes.append(parsed)

    return {
        "language": "python",
        "path": path,
        "nodes": nodes,
        "lines": content.count("\n") + 1,
    }


def _python_node_to_dict(node: ast.AST) -> dict[str, Any] | None:
    if isinstance(node, ast.FunctionDef):
        return {
            "type": "function",
            "name": node.name,
            "line": node.lineno,
            "end_line": getattr(node, "end_lineno", node.lineno),
            "args": [a.arg for a in node.args.args],
            "decorators": [_expr_to_str(d) for d in node.decorator_list],
            "docstring": ast.get_docstring(node) or "",
        }
    elif isinstance(node, ast.AsyncFunctionDef):
        return {
            "type": "async_function",
            "name": node.name,
            "line": node.lineno,
            "end_line": getattr(node, "end_lineno", node.lineno),
            "args": [a.arg for a in node.args.args],
            "decorators": [_expr_to_str(d) for d in node.decorator_list],
            "docstring": ast.get_docstring(node) or "",
        }
    elif isinstance(node, ast.ClassDef):
        return {
            "type": "class",
            "name": node.name,
            "line": node.lineno,
            "end_line": getattr(node, "end_lineno", node.lineno),
            "bases": [_expr_to_str(b) for b in node.bases],
            "decorators": [_expr_to_str(d) for d in node.decorator_list],
            "docstring": ast.get_docstring(node) or "",
        }
    elif isinstance(node, ast.Import):
        return {
            "type": "import",
            "names": [a.name for a in node.names],
            "line": node.lineno,
        }
    elif isinstance(node, ast.ImportFrom):
        return {
            "type": "import_from",
            "module": node.module or "",
            "names": [a.name for a in node.names],
            "line": node.lineno,
        }
    elif isinstance(node, ast.Assign):
        names = []
        for target in node.targets:
            if isinstance(target, ast.Name):
                names.append(target.id)
            elif isinstance(target, ast.Tuple):
                names.extend(e.id for e in target.elts if isinstance(e, ast.Name))
        return {
            "type": "assignment",
            "names": names,
            "line": node.lineno,
        }
    elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return {
            "type": "annotated_assignment",
            "name": node.target.id,
            "annotation": _expr_to_str(node.annotation) if node.annotation else "",
            "line": node.lineno,
        }
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return {
            "type": type(node).__name__.lower(),
            "name": node.name,
            "line": node.lineno,
        }
    return None


def _expr_to_str(expr: ast.expr) -> str:
    if isinstance(expr, ast.Name):
        return expr.id
    elif isinstance(expr, ast.Attribute):
        return f"{_expr_to_str(expr.value)}.{expr.attr}"
    elif isinstance(expr, ast.Call):
        return f"{_expr_to_str(expr.func)}(...)"
    elif isinstance(expr, ast.Constant):
        return repr(expr.value)
    elif isinstance(expr, ast.Subscript):
        return f"{_expr_to_str(expr.value)}[{_expr_to_str(expr.slice)}]"
    elif isinstance(expr, ast.Index):
        return _expr_to_str(expr.value)
    else:
        return ast.dump(expr)[:50]


def _parse_javascript(content: str, path: str) -> dict[str, Any]:
    nodes = []

    func_pattern = re.compile(
        r'(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)',
        re.MULTILINE,
    )
    for m in func_pattern.finditer(content):
        line_num = content[:m.start()].count("\n") + 1
        nodes.append({
            "type": "function",
            "name": m.group(1),
            "args": [a.strip() for a in m.group(2).split(",") if a.strip()],
            "line": line_num,
        })

    arrow_pattern = re.compile(
        r'(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>',
        re.MULTILINE,
    )
    for m in arrow_pattern.finditer(content):
        line_num = content[:m.start()].count("\n") + 1
        nodes.append({
            "type": "arrow_function",
            "name": m.group(1),
            "args": [a.strip() for a in m.group(2).split(",") if a.strip()],
            "line": line_num,
        })

    single_arrow = re.compile(
        r'(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?(\w+)\s*=>',
        re.MULTILINE,
    )
    for m in single_arrow.finditer(content):
        line_num = content[:m.start()].count("\n") + 1
        nodes.append({
            "type": "arrow_function",
            "name": m.group(1),
            "args": [m.group(2)],
            "line": line_num,
        })

    class_pattern = re.compile(
        r'(?:export\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?',
        re.MULTILINE,
    )
    for m in class_pattern.finditer(content):
        line_num = content[:m.start()].count("\n") + 1
        nodes.append({
            "type": "class",
            "name": m.group(1),
            "extends": m.group(2) or "",
            "line": line_num,
        })

    method_pattern = re.compile(
        r'^\s+(?:async\s+)?(\w+)\s*\(([^)]*)\)\s*\{',
        re.MULTILINE,
    )
    for m in method_pattern.finditer(content):
        name = m.group(1)
        if name in ("if", "for", "while", "switch", "catch", "return", "else", "try", "import", "export"):
            continue
        line_num = content[:m.start()].count("\n") + 1
        nodes.append({
            "type": "method",
            "name": name,
            "args": [a.strip() for a in m.group(2).split(",") if a.strip()],
            "line": line_num,
        })

    import_pattern = re.compile(
        r'(?:import\s+\{([^}]+)\}\s+from\s+[\'"]([^\'"]+)[\'"]'
        r'|import\s+(\w+)\s+from\s+[\'"]([^\'"]+)[\'"]'
        r'|import\s+[\'"]([^\'"]+)[\'"]'
        r'|const\s+(\w+)\s*=\s*require\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\))',
        re.MULTILINE,
    )
    for m in import_pattern.finditer(content):
        line_num = content[:m.start()].count("\n") + 1
        if m.group(1):
            names = [n.strip().split(" as ")[0] for n in m.group(1).split(",")]
            nodes.append({"type": "import", "names": names, "source": m.group(2), "line": line_num})
        elif m.group(3):
            nodes.append({"type": "import", "names": [m.group(3)], "source": m.group(4), "line": line_num})
        elif m.group(5):
            nodes.append({"type": "import_side_effect", "source": m.group(5), "line": line_num})
        elif m.group(6):
            nodes.append({"type": "require", "name": m.group(6), "source": m.group(7), "line": line_num})

    export_pattern = re.compile(
        r'export\s+(?:default\s+)?(?:function|class|const|let|var)\s+(\w+)',
        re.MULTILINE,
    )
    for m in export_pattern.finditer(content):
        line_num = content[:m.start()].count("\n") + 1
        nodes.append({"type": "export", "name": m.group(1), "line": line_num})

    return {
        "language": "javascript",
        "path": path,
        "nodes": nodes,
        "lines": content.count("\n") + 1,
    }


def _parse_html(content: str, path: str) -> dict[str, Any]:
    nodes = []

    class _HTMLParser(html.parser.HTMLParser):
        def handle_starttag(self, tag, attrs):
            attr_dict = dict(attrs)
            nodes.append({
                "type": "element",
                "tag": tag,
                "attrs": attr_dict,
                "line": self.getpos()[0],
            })

    parser = _HTMLParser()
    try:
        parser.feed(content)
    except Exception:
        pass

    script_pattern = re.compile(r'<script[^>]*>(.*?)</script>', re.DOTALL | re.IGNORECASE)
    for m in script_pattern.finditer(content):
        line_num = content[:m.start()].count("\n") + 1
        script_content = m.group(1).strip()
        if script_content:
            js_result = _parse_javascript(script_content, path)
            for node in js_result.get("nodes", []):
                node["line"] = line_num + node.get("line", 1) - 1
                node["in_script"] = True
                nodes.append(node)

    style_pattern = re.compile(r'<style[^>]*>(.*?)</style>', re.DOTALL | re.IGNORECASE)
    for m in style_pattern.finditer(content):
        line_num = content[:m.start()].count("\n") + 1
        css_content = m.group(1).strip()
        if css_content:
            css_result = _parse_css(css_content, path)
            for node in css_result.get("nodes", []):
                node["line"] = line_num + node.get("line", 1) - 1
                node["in_style"] = True
                nodes.append(node)

    meta_pattern = re.compile(r'<meta\s+([^>]*?)(?:/|)>', re.IGNORECASE)
    for m in meta_pattern.finditer(content):
        line_num = content[:m.start()].count("\n") + 1
        attrs = dict(re.findall(r'(\w[\w-]*)=["\']([^"\']*)["\']', m.group(1)))
        nodes.append({
            "type": "meta",
            "attrs": attrs,
            "line": line_num,
        })

    return {
        "language": "html",
        "path": path,
        "nodes": nodes,
        "lines": content.count("\n") + 1,
    }


def _parse_css(content: str, path: str) -> dict[str, Any]:
    nodes = []

    rule_pattern = re.compile(
        r'([^{]+)\{([^}]*)\}',
        re.DOTALL,
    )
    for m in rule_pattern.finditer(content):
        selectors = [s.strip() for s in m.group(1).strip().split(",") if s.strip()]
        declarations = []
        for line in m.group(2).strip().split("\n"):
            line = line.strip().rstrip(";")
            if ":" in line:
                prop, _, val = line.partition(":")
                declarations.append({"property": prop.strip(), "value": val.strip()})

        line_num = content[:m.start()].count("\n") + 1
        nodes.append({
            "type": "rule",
            "selectors": selectors,
            "declarations": declarations,
            "line": line_num,
        })

    media_pattern = re.compile(r'@media\s+([^{]+)\{', re.IGNORECASE)
    for m in media_pattern.finditer(content):
        line_num = content[:m.start()].count("\n") + 1
        nodes.append({
            "type": "at_rule",
            "name": "@media",
            "query": m.group(1).strip(),
            "line": line_num,
        })

    keyframe_pattern = re.compile(r'@keyframes\s+(\w+)\s*\{', re.IGNORECASE)
    for m in keyframe_pattern.finditer(content):
        line_num = content[:m.start()].count("\n") + 1
        nodes.append({
            "type": "at_rule",
            "name": "@keyframes",
            "animation_name": m.group(1),
            "line": line_num,
        })

    import_pattern = re.compile(r'@import\s+(?:url\()?["\']?([^"\')\s]+)["\']?\)?', re.IGNORECASE)
    for m in import_pattern.finditer(content):
        line_num = content[:m.start()].count("\n") + 1
        nodes.append({
            "type": "import",
            "source": m.group(1),
            "line": line_num,
        })

    return {
        "language": "css",
        "path": path,
        "nodes": nodes,
        "lines": content.count("\n") + 1,
    }
