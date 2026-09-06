"""Security scanning tools for Hermes agent."""
import asyncio
import hashlib
import json
import os
import re
import pathlib

TOOLS = [
    {"name": "scan_secrets", "description": "Scan codebase for secrets, API keys, and tokens", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Directory to scan"}, "patterns": {"type": "array", "items": {"type": "string"}, "description": "Custom patterns to search for"}}, "required": ["path"]}},
    {"name": "scan_dependencies", "description": "Check dependencies for known vulnerabilities", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Path to project root"}, "language": {"type": "string", "description": "Language (python, javascript, go)"}}}},
    {"name": "check_ssl", "description": "Check SSL certificate validity for a domain", "parameters": {"type": "object", "properties": {"domain": {"type": "string", "description": "Domain to check"}}, "required": ["domain"]}},
    {"name": "port_scan", "description": "Quick port scan on a target", "parameters": {"type": "object", "properties": {"host": {"type": "string", "description": "Target host"}, "ports": {"type": "string", "description": "Port range (e.g. 1-1000)"}}, "required": ["host"]}},
    {"name": "hash_file", "description": "Calculate file hash (MD5, SHA1, SHA256)", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "File path"}, "algorithm": {"type": "string", "description": "Hash algorithm (md5, sha1, sha256)", "default": "sha256"}}, "required": ["path"]}},
    {"name": "check_headers", "description": "Check HTTP security headers for a URL", "parameters": {"type": "object", "properties": {"url": {"type": "string", "description": "URL to check"}}, "required": ["url"]}},
    {"name": "vuln_scan", "description": "Scan for common web vulnerabilities (XSS, SQLi patterns)", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Source code directory"}}}},
    {"name": "check_permissions", "description": "Check file permissions for security issues", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Directory to check"}}}},
    {"name": "generate_secret", "description": "Generate a cryptographically secure random secret", "parameters": {"type": "object", "properties": {"length": {"type": "integer", "description": "Secret length in bytes", "default": 32}, "format": {"type": "string", "description": "Output format (hex, base64)", "default": "hex"}}}},
    {"name": "audit_env", "description": "Audit environment for security misconfigurations", "parameters": {"type": "object", "properties": {}}},
]

SECRET_PATTERNS = [
    (r'(?i)(api[_-]?key|apikey)\s*[=:]\s*["\']([^"\']{8,})["\']', "API Key"),
    (r'(?i)(secret[_-]?key|secretkey)\s*[=:]\s*["\']([^"\']{8,})["\']', "Secret Key"),
    (r'(?i)(password|passwd|pwd)\s*[=:]\s*["\']([^"\']{6,})["\']', "Password"),
    (r'(?i)(token)\s*[=:]\s*["\']([^"\']{8,})["\']', "Token"),
    (r'(?i)(aws[_-]?access[_-]?key[_-]?id)\s*[=:]\s*["\']([A-Z0-9]{16,})["\']', "AWS Access Key"),
    (r'(?i)(aws[_-]?secret[_-]?access[_-]?key)\s*[=:]\s*["\']([A-Za-z0-9/+=]{40})["\']', "AWS Secret Key"),
    (r'(?i)(github[_-]?token|gh[_-]?token|ghp_[A-Za-z0-9]{36})', "GitHub Token"),
    (r'(?i)(private[_-]?key)\s*[=:]\s*["\']-----BEGIN', "Private Key"),
    (r'(?i)(slack[_-]?token|xox[bpsar]-[0-9]{10,})', "Slack Token"),
    (r'(?i)(mysql|postgres|mongodb)://[^\s]+', "Database Connection String"),
]

functions = {}

async def scan_secrets(args):
    path = args.get("path", ".")
    findings = []
    custom_patterns = args.get("patterns", [])

    all_patterns = SECRET_PATTERNS[:]
    for p in custom_patterns:
        all_patterns.append((p, "Custom Pattern"))

    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in {'.git', 'node_modules', '__pycache__', '.venv', 'venv', '.env'}]
        for fname in files:
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, 'r', errors='ignore') as f:
                    content = f.read()
                for pattern, ptype in all_patterns:
                    for match in re.finditer(pattern, content):
                        line_num = content[:match.start()].count('\n') + 1
                        findings.append({
                            "file": fpath, "line": line_num, "type": ptype,
                            "match": match.group()[:100],
                        })
            except (PermissionError, OSError):
                continue

    return json.dumps({"findings": findings, "count": len(findings), "scanned_path": path})

async def scan_dependencies(args):
    path = args.get("path", ".")
    language = args.get("language", "auto")
    vulns = []

    if language == "auto" or language == "python":
        req_files = ["requirements.txt", "setup.py", "pyproject.toml"]
        for rf in req_files:
            fpath = os.path.join(path, rf)
            if os.path.exists(fpath):
                with open(fpath, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and not line.startswith('-'):
                            pkg = line.split('==')[0].split('>=')[0].split('<=')[0].split('~=')[0].strip()
                            if pkg:
                                vulns.append({"package": pkg, "file": rf, "status": "check_manually", "language": "python"})

    if language == "auto" or language == "javascript":
        pkg_files = ["package.json"]
        for pf in pkg_files:
            fpath = os.path.join(path, pf)
            if os.path.exists(fpath):
                try:
                    with open(fpath, 'r') as f:
                        pkg = json.load(f)
                    for dep_type in ["dependencies", "devDependencies"]:
                        for name, ver in pkg.get(dep_type, {}).items():
                            vulns.append({"package": name, "version": ver, "file": pf, "status": "check_manually", "language": "javascript"})
                except json.JSONDecodeError:
                    pass

    return json.dumps({"dependencies": vulns, "count": len(vulns), "language": language})

async def check_ssl(args):
    domain = args["domain"]
    try:
        proc = await asyncio.create_subprocess_exec(
            "python", "-c", f"""
import ssl, socket, json
ctx = ssl.create_default_context()
with ctx.wrap_socket(socket.socket(), server_hostname='{domain}') as s:
    s.connect(('{domain}', 443))
    cert = s.getpeercert()
    print(json.dumps({{
        'subject': dict(x[0] for x in cert.get('subject', [])),
        'issuer': dict(x[0] for x in cert.get('issuer', [])),
        'notBefore': cert.get('notBefore', ''),
        'notAfter': cert.get('notAfter', ''),
        'serialNumber': cert.get('serialNumber', ''),
        'san': [x[1] for x in cert.get('subjectAltName', [])],
    }}))
""",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        return stdout.decode(errors="ignore").strip()
    except Exception as e:
        return json.dumps({"error": str(e), "domain": domain})

async def port_scan(args):
    host = args["host"]
    ports_str = args.get("ports", "1-100")
    open_ports = []

    if "-" in ports_str:
        start, end = map(int, ports_str.split("-"))
        ports = range(start, min(end + 1, start + 1000))
    else:
        ports = [int(p.strip()) for p in ports_str.split(",")][:100]

    for port in ports:
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=0.3
            )
            writer.close()
            await writer.wait_closed()
            open_ports.append(port)
        except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
            continue

    return json.dumps({"host": host, "open_ports": open_ports, "scanned": len(list(ports))})

async def hash_file(args):
    path = args["path"]
    algo = args.get("algorithm", "sha256")
    try:
        h = hashlib.new(algo)
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                h.update(chunk)
        return json.dumps({"file": path, "hash": h.hexdigest(), "algorithm": algo, "size": os.path.getsize(path)})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def check_headers(args):
    url = args["url"]
    try:
        proc = await asyncio.create_subprocess_exec(
            "python", "-c", f"""
import urllib.request, json
req = urllib.request.Request('{url}', method='HEAD')
req.add_header('User-Agent', 'Hermes-Security-Scanner/1.0')
try:
    resp = urllib.request.urlopen(req, timeout=5)
    headers = dict(resp.headers)
    security = {{}}
    checks = {{
        'Strict-Transport-Security': 'HSTS',
        'X-Content-Type-Options': 'MIME sniffing protection',
        'X-Frame-Options': 'Clickjacking protection',
        'X-XSS-Protection': 'XSS protection',
        'Content-Security-Policy': 'CSP',
        'Referrer-Policy': 'Referrer policy',
        'Permissions-Policy': 'Permissions policy',
    }}
    for h, desc in checks.items():
        security[h] = {{'present': h in headers, 'value': headers.get(h, 'MISSING'), 'description': desc}}
    print(json.dumps({{'status': resp.status, 'headers': dict(headers), 'security': security}}))
except Exception as e:
    print(json.dumps({{'error': str(e)}}))
""",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        return stdout.decode(errors="ignore").strip()
    except Exception as e:
        return json.dumps({"error": str(e)})

async def vuln_scan(args):
    path = args.get("path", ".")
    vulns = []
    xss_patterns = [r'dangerouslySetInnerHTML', r'innerHTML\s*=', r'v-html', r'eval\(', r'innerHTML']
    sqli_patterns = [r'execute\(.*\+', r'query\(.*\+', r'f".*SELECT.*{', r'f".*INSERT.*{', r'f".*DELETE.*{']
    cmdi_patterns = [r'os\.system\(', r'subprocess\.call\(.*shell\s*=\s*True', r'os\.popen\(', r'exec\(', r'eval\(']

    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in {'.git', 'node_modules', '__pycache__'}]
        for fname in files:
            if not fname.endswith(('.py', '.js', '.ts', '.jsx', '.tsx', '.php', '.rb', '.go')):
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, 'r', errors='ignore') as f:
                    lines = f.readlines()
                for i, line in enumerate(lines, 1):
                    for pattern in xss_patterns:
                        if re.search(pattern, line):
                            vulns.append({"file": fpath, "line": i, "type": "XSS", "pattern": pattern, "code": line.strip()[:120]})
                    for pattern in sqli_patterns:
                        if re.search(pattern, line):
                            vulns.append({"file": fpath, "line": i, "type": "SQLi", "pattern": pattern, "code": line.strip()[:120]})
                    for pattern in cmdi_patterns:
                        if re.search(pattern, line):
                            vulns.append({"file": fpath, "line": i, "type": "CMDi", "pattern": pattern, "code": line.strip()[:120]})
            except (PermissionError, OSError):
                continue

    return json.dumps({"vulnerabilities": vulns, "count": len(vulns)})

async def check_permissions(args):
    path = args.get("path", ".")
    issues = []
    sensitive_files = {'.env', '.ssh', 'id_rsa', 'id_ed25519', '.htpasswd', '.netrc'}

    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in {'.git', 'node_modules'}]
        for fname in files + dirs:
            fpath = os.path.join(root, fname)
            try:
                stat_info = os.stat(fpath)
                mode = oct(stat_info.st_mode)[-3:]
                if fname in sensitive_files:
                    issues.append({"path": fpath, "permissions": mode, "issue": "Sensitive file may have overly permissive access"})
                if mode in ('777', '776', '775', '766'):
                    issues.append({"path": fpath, "permissions": mode, "issue": f"World-writable permissions ({mode})"})
                if fname in ('.env', 'config.json', 'secrets.json') and mode[2] not in ('0', '4'):
                    issues.append({"path": fpath, "permissions": mode, "issue": "Config/secrets file readable by others"})
            except (PermissionError, OSError):
                continue

    return json.dumps({"issues": issues, "count": len(issues)})

async def generate_secret(args):
    length = args.get("length", 32)
    fmt = args.get("format", "hex")
    try:
        import secrets
        raw = secrets.token_bytes(length)
        if fmt == "base64":
            import base64
            secret = base64.b64encode(raw).decode()
        else:
            secret = raw.hex()
        return json.dumps({"secret": secret, "length": length, "format": fmt})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def audit_env(args):
    issues = []

    sensitive_vars = ['AWS_SECRET_ACCESS_KEY', 'DATABASE_PASSWORD', 'API_SECRET', 'PRIVATE_KEY']
    for var in sensitive_vars:
        val = os.environ.get(var, '')
        if val:
            issues.append({"variable": var, "issue": "Secret exposed in environment", "severity": "high"})

    debug_vars = ['DEBUG', 'FLASK_DEBUG', 'DJANGO_DEBUG']
    for var in debug_vars:
        if os.environ.get(var, '').lower() in ('1', 'true', 'yes'):
            issues.append({"variable": var, "issue": "Debug mode enabled in production", "severity": "medium"})

    if not os.environ.get('HTTPS'):
        issues.append({"variable": "HTTPS", "issue": "HTTPS not configured", "severity": "medium"})

    return json.dumps({"issues": issues, "count": len(issues)})

functions = {
    "scan_secrets": scan_secrets, "scan_dependencies": scan_dependencies, "check_ssl": check_ssl,
    "port_scan": port_scan, "hash_file": hash_file, "check_headers": check_headers,
    "vuln_scan": vuln_scan, "check_permissions": check_permissions, "generate_secret": generate_secret,
    "audit_env": audit_env,
}
