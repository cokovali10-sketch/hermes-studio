"""Web development tools for Hermes agent."""
import asyncio
import json
import os
import re
import sys

TOOLS = [
    {"name": "create_html", "description": "Create an HTML file with a template", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Output file path"}, "title": {"type": "string", "description": "Page title", "default": "Page"}, "template": {"type": "string", "enum": ["blank", "landing", "dashboard", "blog", "form", "portfolio"], "description": "Template type", "default": "blank"}, "content": {"type": "string", "description": "Main content for blank template"}}, "required": ["path"]}},
    {"name": "create_css", "description": "Create a CSS file", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Output file path"}, "framework": {"type": "string", "enum": ["none", "reset", "modern", "responsive-grid", "utility"], "description": "CSS framework/base", "default": "none"}}, "required": ["path"]}},
    {"name": "create_js", "description": "Create a JavaScript file", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Output file path"}, "module_type": {"type": "string", "enum": ["esm", "commonjs", "browser"], "description": "Module system", "default": "esm"}, "content": {"type": "string", "description": "Custom JS code"}}, "required": ["path"]}},
    {"name": "minify_css", "description": "Minify CSS content", "parameters": {"type": "object", "properties": {"content": {"type": "string", "description": "CSS content to minify"}, "path": {"type": "string", "description": "Or path to CSS file"}}, "required": ["content"]}},
    {"name": "minify_js", "description": "Minify JavaScript content", "parameters": {"type": "object", "properties": {"content": {"type": "string", "description": "JS content to minify"}, "path": {"type": "string", "description": "Or path to JS file"}}, "required": ["content"]}},
    {"name": "validate_html", "description": "Validate HTML for errors", "parameters": {"type": "object", "properties": {"content": {"type": "string", "description": "HTML content to validate"}, "path": {"type": "string", "description": "Or path to HTML file"}}, "required": ["content"]}},
    {"name": "generate_sitemap", "description": "Generate a sitemap.xml for a website", "parameters": {"type": "object", "properties": {"urls": {"type": "array", "items": {"type": "object", "properties": {"loc": {"type": "string"}, "lastmod": {"type": "string"}, "priority": {"type": "number"}, "changefreq": {"type": "string"}}}, "description": "URL entries"}, "base_url": {"type": "string", "description": "Base URL"}, "output": {"type": "string", "description": "Output file path"}}, "required": ["base_url", "output"]}},
    {"name": "optimize_image", "description": "Optimize/compress image files", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Image file path"}, "quality": {"type": "integer", "description": "Compression quality (1-100)", "default": 80}, "max_width": {"type": "integer", "description": "Max width in pixels"}, "format": {"type": "string", "description": "Output format (png, jpg, webp)"}}, "required": ["path"]}},
    {"name": "create_api_mock", "description": "Create a mock API server with endpoints", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Output directory"}, "endpoints": {"type": "array", "items": {"type": "object", "properties": {"route": {"type": "string"}, "method": {"type": "string"}, "response": {"type": "object"}, "status": {"type": "integer"}}}, "description": "API endpoints"}, "port": {"type": "integer", "description": "Server port", "default": 3001}}}},
    {"name": "generate_swagger", "description": "Generate OpenAPI/Swagger specification", "parameters": {"type": "object", "properties": {"title": {"type": "string", "description": "API title"}, "version": {"type": "string", "description": "API version", "default": "1.0.0"}, "paths": {"type": "array", "items": {"type": "object", "properties": {"path": {"type": "string"}, "method": {"type": "string"}, "summary": {"type": "string"}, "parameters": {"type": "array"}}}, "description": "API paths"}, "output": {"type": "string", "description": "Output file path"}}, "required": ["title", "output"]}},
]

functions = {}

HTML_TEMPLATES = {
    "blank": lambda title, content: f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 0 20px; }}
    </style>
</head>
<body>
    <div class="container">
        {content or '<h1>' + title + '</h1><p>Welcome to ' + title + '</p>'}
    </div>
</body>
</html>""",
    "landing": lambda title, content: f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
        .hero {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; text-align: center; padding: 100px 20px; }}
        .hero h1 {{ font-size: 3em; margin-bottom: 20px; }}
        .hero p {{ font-size: 1.2em; margin-bottom: 30px; opacity: 0.9; }}
        .btn {{ display: inline-block; padding: 15px 30px; background: white; color: #667eea; text-decoration: none; border-radius: 5px; font-weight: bold; }}
        .features {{ padding: 60px 20px; text-align: center; max-width: 1000px; margin: 0 auto; }}
        .feature {{ display: inline-block; width: 30%; margin: 1.5%; vertical-align: top; }}
        .feature h3 {{ margin: 15px 0 10px; }}
    </style>
</head>
<body>
    <div class="hero">
        <h1>{title}</h1>
        <p>{content or 'Build something amazing today.'}</p>
        <a href="#" class="btn">Get Started</a>
    </div>
    <div class="features">
        <div class="feature"><h3>Fast</h3><p>Lightning quick performance</p></div>
        <div class="feature"><h3>Reliable</h3><p>Built to last and scale</p></div>
        <div class="feature"><h3>Secure</h3><p>Enterprise-grade security</p></div>
    </div>
</body>
</html>""",
    "dashboard": lambda title, content: f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f0f2f5; }}
        .sidebar {{ width: 250px; height: 100vh; background: #1a1a2e; color: white; position: fixed; padding: 20px; }}
        .sidebar h2 {{ margin-bottom: 30px; font-size: 1.4em; }}
        .sidebar a {{ display: block; padding: 12px 15px; color: #aaa; text-decoration: none; border-radius: 6px; margin-bottom: 5px; }}
        .sidebar a:hover, .sidebar a.active {{ background: #16213e; color: white; }}
        .main {{ margin-left: 250px; padding: 30px; }}
        .header {{ margin-bottom: 30px; }}
        .header h1 {{ font-size: 1.8em; color: #1a1a2e; }}
        .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; }}
        .card {{ background: white; border-radius: 10px; padding: 25px; box-shadow: 0 2px 10px rgba(0,0,0,0.08); }}
        .card h3 {{ color: #666; font-size: 0.9em; text-transform: uppercase; margin-bottom: 10px; }}
        .card .value {{ font-size: 2em; font-weight: bold; color: #1a1a2e; }}
    </style>
</head>
<body>
    <div class="sidebar">
        <h2>{title}</h2>
        <a href="#" class="active">Dashboard</a>
        <a href="#">Analytics</a>
        <a href="#">Settings</a>
        <a href="#">Users</a>
    </div>
    <div class="main">
        <div class="header"><h1>Dashboard</h1></div>
        <div class="cards">
            <div class="card"><h3>Total Users</h3><div class="value">1,234</div></div>
            <div class="card"><h3>Revenue</h3><div class="value">$45,678</div></div>
            <div class="card"><h3>Orders</h3><div class="value">567</div></div>
            <div class="card"><h3>Growth</h3><div class="value">+23%</div></div>
        </div>
    </div>
</body>
</html>""",
    "blog": lambda title, content: f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: Georgia, 'Times New Roman', serif; background: #fafafa; color: #333; }}
        nav {{ background: white; border-bottom: 1px solid #eee; padding: 15px 0; }}
        nav .container {{ max-width: 800px; margin: 0 auto; padding: 0 20px; display: flex; justify-content: space-between; align-items: center; }}
        nav h1 {{ font-size: 1.5em; }}
        nav a {{ color: #666; text-decoration: none; }}
        .post {{ max-width: 800px; margin: 40px auto; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 5px rgba(0,0,0,0.1); }}
        .post-content {{ padding: 40px; }}
        .post-content h2 {{ font-size: 2em; margin-bottom: 15px; }}
        .post-meta {{ color: #999; margin-bottom: 20px; font-size: 0.9em; }}
        .post-content p {{ margin-bottom: 20px; line-height: 1.8; }}
    </style>
</head>
<body>
    <nav><div class="container"><h1>{title}</h1><a href="#">Subscribe</a></div></nav>
    <article class="post">
        <div class="post-content">
            <h2>Welcome to {title}</h2>
            <div class="post-meta">Published today</div>
            <p>{content or 'This is your first blog post. Share your thoughts with the world.'}</p>
        </div>
    </article>
</body>
</html>""",
    "form": lambda title, content: f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; display: flex; justify-content: center; align-items: center; min-height: 100vh; }}
        .form-container {{ background: white; border-radius: 10px; padding: 40px; width: 100%; max-width: 500px; box-shadow: 0 10px 40px rgba(0,0,0,0.1); }}
        .form-container h2 {{ margin-bottom: 25px; text-align: center; color: #333; }}
        .form-group {{ margin-bottom: 20px; }}
        .form-group label {{ display: block; margin-bottom: 6px; font-weight: 500; color: #555; }}
        .form-group input, .form-group textarea, .form-group select {{ width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 6px; font-size: 1em; }}
        .form-group textarea {{ height: 120px; resize: vertical; }}
        .btn-submit {{ width: 100%; padding: 14px; background: #667eea; color: white; border: none; border-radius: 6px; font-size: 1em; cursor: pointer; }}
        .btn-submit:hover {{ background: #5a6fd6; }}
    </style>
</head>
<body>
    <div class="form-container">
        <h2>{title}</h2>
        <form>
            <div class="form-group"><label>Name</label><input type="text" name="name" required></div>
            <div class="form-group"><label>Email</label><input type="email" name="email" required></div>
            <div class="form-group"><label>Message</label><textarea name="message" required></textarea></div>
            <button type="submit" class="btn-submit">Send</button>
        </form>
    </div>
</body>
</html>""",
    "portfolio": lambda title, content: f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
        .hero {{ background: #1a1a2e; color: white; padding: 80px 20px; text-align: center; }}
        .hero h1 {{ font-size: 3em; margin-bottom: 15px; }}
        .hero p {{ font-size: 1.2em; opacity: 0.8; }}
        .projects {{ padding: 60px 20px; max-width: 1000px; margin: 0 auto; }}
        .projects h2 {{ text-align: center; margin-bottom: 40px; font-size: 2em; }}
        .project-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 25px; }}
        .project {{ background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .project-img {{ height: 200px; background: linear-gradient(135deg, #667eea, #764ba2); }}
        .project-info {{ padding: 20px; }}
        .project-info h3 {{ margin-bottom: 10px; }}
        .project-info p {{ color: #666; font-size: 0.95em; }}
    </style>
</head>
<body>
    <div class="hero">
        <h1>{title}</h1>
        <p>{content or 'Developer | Designer | Creator'}</p>
    </div>
    <div class="projects">
        <h2>Projects</h2>
        <div class="project-grid">
            <div class="project"><div class="project-img"></div><div class="project-info"><h3>Project One</h3><p>A brief description of this amazing project.</p></div></div>
            <div class="project"><div class="project-img"></div><div class="project-info"><h3>Project Two</h3><p>Another great project showcasing innovation.</p></div></div>
            <div class="project"><div class="project-img"></div><div class="project-info"><h3>Project Three</h3><p>Creative solutions for modern challenges.</p></div></div>
        </div>
    </div>
</body>
</html>""",
}

async def create_html(args):
    path = args["path"]
    title = args.get("title", "Page")
    template = args.get("template", "blank")
    content = args.get("content", "")
    try:
        tmpl_fn = HTML_TEMPLATES.get(template, HTML_TEMPLATES["blank"])
        html = tmpl_fn(title, content)
        target = os.path.abspath(path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(html)
        return json.dumps({"success": True, "path": path, "template": template, "size": len(html), "lines": html.count("\n") + 1})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def create_css(args):
    path = args["path"]
    framework = args.get("framework", "none")
    try:
        css = ""
        if framework == "reset":
            css = """*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{-moz-text-size-adjust:none;-webkit-text-size-adjust:none;text-size-adjust:none}
body{min-height:100vh;line-height:1.5;-webkit-font-smoothing:antialiased}
img,picture,video,canvas,svg{display:block;max-width:100%}
input,button,textarea,select{font:inherit}
p,h1,h2,h3,h4,h5,h6{overflow-wrap:break-word}
"""
        elif framework == "modern":
            css = """:root{--primary:#667eea;--primary-dark:#5a6fd6;--secondary:#764ba2;--bg:#f8f9fa;--text:#333;--text-light:#666;--border:#e0e0e0;--shadow:0 2px 10px rgba(0,0,0,0.08);--radius:8px;--max-width:1200px}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:var(--bg);color:var(--text);line-height:1.6}
.container{max-width:var(--max-width);margin:0 auto;padding:0 20px}
a{color:var(--primary);text-decoration:none}
a:hover{color:var(--primary-dark)}
.btn{display:inline-block;padding:10px 24px;border-radius:var(--radius);font-weight:500;cursor:pointer;border:none;transition:all .2s}
.btn-primary{background:var(--primary);color:white}
.btn-primary:hover{background:var(--primary-dark)}
.card{background:white;border-radius:var(--radius);box-shadow:var(--shadow);padding:24px}
.grid{display:grid;gap:20px}
@media(min-width:768px){.grid-2{grid-template-columns:repeat(2,1fr)}.grid-3{grid-template-columns:repeat(3,1fr)}}
"""
        elif framework == "responsive-grid":
            css = """.row{display:flex;flex-wrap:wrap;margin:0 -10px}
.col{flex:1;padding:0 10px}
.col-2{flex:0 0 16.666%}
.col-3{flex:0 0 25%}
.col-4{flex:0 0 33.333%}
.col-6{flex:0 0 50%}
.col-12{flex:0 0 100%}
@media(max-width:768px){.col,.col-2,.col-3,.col-4,.col-6{flex:0 0 100%}}
"""
        elif framework == "utility":
            css = """.m-0{margin:0}.m-1{margin:8px}.m-2{margin:16px}.m-3{margin:24px}
.p-0{padding:0}.p-1{padding:8px}.p-2{padding:16px}.p-3{padding:24px}
.text-center{text-align:center}.text-left{text-align:left}.text-right{text-align:right}
.font-bold{font-weight:700}.font-normal{font-weight:400}
.text-sm{font-size:.875rem}.text-lg{font-size:1.125rem}.text-xl{font-size:1.25rem}
.flex{display:flex}.flex-col{flex-direction:column}.items-center{align-items:center}.justify-between{justify-content:space-between}
.bg-white{background:#fff}.bg-gray{background:#f3f4f6}.bg-primary{background:#667eea;color:#fff}
.rounded{border-radius:8px}.shadow{box-shadow:0 2px 10px rgba(0,0,0,0.08)}
.w-full{width:100%}.h-full{height:100%}
.hidden{display:none}.block{display:block}.inline-block{display:inline-block}
"""
        target = os.path.abspath(path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(css)
        return json.dumps({"success": True, "path": path, "framework": framework, "size": len(css)})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def create_js(args):
    path = args["path"]
    module_type = args.get("module_type", "esm")
    content = args.get("content", "")
    try:
        if content:
            js = content
        elif module_type == "esm":
            js = """// ES Module
export function init() {
  console.log('Module initialized');
}

export default { init };
"""
        elif module_type == "commonjs":
            js = """// CommonJS Module
function init() {
  console.log('Module initialized');
}

module.exports = { init };
"""
        else:
            js = """// Browser Script
(function() {
  'use strict';

  function init() {
    console.log('Script loaded');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
"""
        target = os.path.abspath(path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(js)
        return json.dumps({"success": True, "path": path, "module_type": module_type, "size": len(js)})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def minify_css(args):
    content = args.get("content", "")
    path = args.get("path", "")
    try:
        if path and not content:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        if not content:
            return json.dumps({"error": "No content or path provided", "success": False})
        original_size = len(content)
        minified = content
        minified = re.sub(r'/\*.*?\*/', '', minified, flags=re.DOTALL)
        minified = re.sub(r'\s+', ' ', minified)
        minified = re.sub(r'\s*([{}:;,>+~])\s*', r'\1', minified)
        minified = re.sub(r';}', '}', minified)
        minified = minified.strip()
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(minified)
        saved = original_size - len(minified)
        return json.dumps({
            "success": True, "original_size": original_size,
            "minified_size": len(minified), "saved_bytes": saved,
            "compression_ratio": f"{round((1 - len(minified)/original_size)*100, 1)}%",
            "minified": minified[:5000],
        })
    except Exception as e:
        return json.dumps({"error": str(e)})

async def minify_js(args):
    content = args.get("content", "")
    path = args.get("path", "")
    try:
        if path and not content:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        if not content:
            return json.dumps({"error": "No content or path provided", "success": False})
        original_size = len(content)
        minified = content
        minified = re.sub(r'//.*?\n', '\n', minified)
        minified = re.sub(r'/\*.*?\*/', '', minified, flags=re.DOTALL)
        minified = re.sub(r'\s+', ' ', minified)
        minified = re.sub(r'\s*([{}();,=+\-<>!&|?:])\s*', r'\1', minified)
        minified = minified.strip()
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(minified)
        saved = original_size - len(minified)
        return json.dumps({
            "success": True, "original_size": original_size,
            "minified_size": len(minified), "saved_bytes": saved,
            "compression_ratio": f"{round((1 - len(minified)/original_size)*100, 1)}%",
            "minified": minified[:5000],
        })
    except Exception as e:
        return json.dumps({"error": str(e)})

async def validate_html(args):
    content = args.get("content", "")
    path = args.get("path", "")
    try:
        if path and not content:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        if not content:
            return json.dumps({"error": "No content or path provided", "success": False})
        issues = []
        if "<!DOCTYPE" not in content and "<!doctype" not in content:
            issues.append({"severity": "warning", "message": "Missing DOCTYPE declaration"})
        if "<html" not in content.lower():
            issues.append({"severity": "error", "message": "Missing <html> tag"})
        else:
            lang_match = re.search(r'<html[^>]*lang=["\']([^"\']+)["\']', content)
            if not lang_match:
                issues.append({"severity": "warning", "message": "Missing lang attribute on <html>"})
        if "<head" not in content.lower():
            issues.append({"severity": "error", "message": "Missing <head> section"})
        else:
            if "<title" not in content.lower():
                issues.append({"severity": "warning", "message": "Missing <title> tag"})
            if 'charset="utf-8"' not in content.lower() and "charset='utf-8'" not in content.lower() and 'charset=utf-8' not in content.lower():
                issues.append({"severity": "warning", "message": "Missing charset UTF-8 declaration"})
            if "viewport" not in content.lower():
                issues.append({"severity": "info", "message": "Missing viewport meta tag (recommended for responsive)"})
        if "<body" not in content.lower():
            issues.append({"severity": "error", "message": "Missing <body> tag"})
        tags = re.findall(r'<([a-zA-Z][a-zA-Z0-9]*)\b', content)
        self_closing = {"img", "br", "hr", "input", "meta", "link", "area", "base", "col", "embed", "source", "track", "wbr"}
        open_tags = []
        for tag in tags:
            if tag.lower() in self_closing:
                continue
            if tag.lower().startswith("!--"):
                continue
            open_tags.append(tag)
        errors_count = sum(1 for i in issues if i["severity"] == "error")
        warnings_count = sum(1 for i in issues if i["severity"] == "warning")
        return json.dumps({
            "success": True, "valid": errors_count == 0,
            "errors": errors_count, "warnings": warnings_count,
            "issues": issues, "lines": content.count("\n") + 1,
        })
    except Exception as e:
        return json.dumps({"error": str(e)})

async def generate_sitemap(args):
    base_url = args["base_url"].rstrip("/")
    output = args["output"]
    urls = args.get("urls", [])
    try:
        today = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
        xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        for url_entry in urls:
            loc = url_entry.get("loc", "")
            if not loc.startswith("http"):
                loc = f"{base_url}/{loc.lstrip('/')}"
            lastmod = url_entry.get("lastmod", today)
            priority = url_entry.get("priority", 0.5)
            changefreq = url_entry.get("changefreq", "monthly")
            xml += "  <url>\n"
            xml += f"    <loc>{loc}</loc>\n"
            xml += f"    <lastmod>{lastmod}</lastmod>\n"
            xml += f"    <changefreq>{changefreq}</changefreq>\n"
            xml += f"    <priority>{priority}</priority>\n"
            xml += "  </url>\n"
        xml += "</urlset>\n"
        target = os.path.abspath(output)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(xml)
        return json.dumps({"success": True, "path": output, "urls": len(urls), "size": len(xml)})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def optimize_image(args):
    path = args["path"]
    quality = args.get("quality", 80)
    max_width = args.get("max_width")
    output_format = args.get("format")
    try:
        try:
            from PIL import Image
        except ImportError:
            return json.dumps({"error": "Pillow not installed. Run: pip install Pillow", "success": False})
        src = os.path.abspath(path)
        if not os.path.exists(src):
            return json.dumps({"error": f"Image not found: {path}", "success": False})
        img = Image.open(src)
        original_size = os.path.getsize(src)
        if max_width and img.width > max_width:
            ratio = max_width / img.width
            new_height = int(img.height * ratio)
            img = img.resize((max_width, new_height), Image.LANCZOS)
        ext = os.path.splitext(src)[1].lower()
        if output_format:
            ext = f".{output_format.lstrip('.')}"
        out_path = src.replace(os.path.splitext(src)[1], f"_optimized{ext}")
        save_kwargs = {}
        if ext in (".jpg", ".jpeg"):
            save_kwargs = {"quality": quality, "optimize": True}
        elif ext == ".png":
            save_kwargs = {"optimize": True}
        elif ext == ".webp":
            save_kwargs = {"quality": quality}
        img.save(out_path, **save_kwargs)
        new_size = os.path.getsize(out_path)
        return json.dumps({
            "success": True, "original_size": original_size, "optimized_size": new_size,
            "saved_bytes": original_size - new_size,
            "compression_ratio": f"{round((1 - new_size/original_size)*100, 1)}%",
            "output_path": out_path, "dimensions": f"{img.width}x{img.height}",
        })
    except Exception as e:
        return json.dumps({"error": str(e)})

async def create_api_mock(args):
    path = args.get("path", ".")
    endpoints = args.get("endpoints", [])
    port = args.get("port", 3001)
    try:
        target = os.path.abspath(path)
        os.makedirs(target, exist_ok=True)
        server_js = f"""const http = require('http');

const PORT = {port};
const routes = {{}};

"""
        for ep in endpoints:
            route = ep.get("route", "/")
            method = ep.get("method", "GET").upper()
            response = ep.get("response", {"message": "ok"})
            status = ep.get("status", 200)
            server_js += f"""routes['{method} {route}'] = {{ status: {status}, body: {json.dumps(response)} }};
"""
        server_js += """
const server = http.createServer((req, res) => {
  const key = `${req.method} ${req.url}`;
  const route = routes[key] || routes[`${req.method} /`] || { status: 404, body: { error: 'Not found' } };

  res.writeHead(route.status, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(route.body));
  console.log(`${req.method} ${req.url} -> ${route.status}`);
});

server.listen(PORT, () => console.log(`Mock API running on http://localhost:${PORT}`));
"""
        server_path = os.path.join(target, "mock-server.js")
        with open(server_path, "w", encoding="utf-8") as f:
            f.write(server_js)
        pkg = {"name": "mock-api", "version": "1.0.0", "scripts": {"start": "node mock-server.js"}}
        with open(os.path.join(target, "package.json"), "w", encoding="utf-8") as f:
            json.dump(pkg, f, indent=2)
        return json.dumps({"success": True, "path": target, "endpoints": len(endpoints), "port": port, "server_file": server_path})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def generate_swagger(args):
    title = args["title"]
    version = args.get("version", "1.0.0")
    paths = args.get("paths", [])
    output = args["output"]
    try:
        spec = {
            "openapi": "3.0.3",
            "info": {"title": title, "version": version},
            "paths": {},
        }
        for p in paths:
            path = p.get("path", "/")
            method = p.get("method", "get").lower()
            summary = p.get("summary", "")
            parameters = p.get("parameters", [])
            if path not in spec["paths"]:
                spec["paths"][path] = {}
            operation = {"summary": summary, "responses": {"200": {"description": "Success"}}}
            if parameters:
                operation["parameters"] = []
                for param in parameters:
                    operation["parameters"].append({
                        "name": param.get("name", ""),
                        "in": param.get("in", "query"),
                        "required": param.get("required", False),
                        "schema": {"type": param.get("type", "string")},
                    })
            spec["paths"][path][method] = operation
        target = os.path.abspath(output)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            json.dump(spec, f, indent=2)
        return json.dumps({"success": True, "path": output, "paths": len(spec["paths"]), "spec": spec})
    except Exception as e:
        return json.dumps({"error": str(e)})

functions = {
    "create_html": create_html,
    "create_css": create_css,
    "create_js": create_js,
    "minify_css": minify_css,
    "minify_js": minify_js,
    "validate_html": validate_html,
    "generate_sitemap": generate_sitemap,
    "optimize_image": optimize_image,
    "create_api_mock": create_api_mock,
    "generate_swagger": generate_swagger,
}
