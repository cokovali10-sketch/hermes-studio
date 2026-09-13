"""DevOps tools for Hermes agent."""
import asyncio
import json
import shutil

TOOLS = [
    {"name": "terraform_init", "description": "Initialize a Terraform working directory", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Path to Terraform directory", "default": "."}}}},
    {"name": "terraform_plan", "description": "Generate and show a Terraform execution plan", "parameters": {"type": "object", "properties": {"path": {"type": "string", "default": "."}, "var_file": {"type": "string", "description": "Variable file to use"}}}},
    {"name": "terraform_apply", "description": "Apply Terraform changes", "parameters": {"type": "object", "properties": {"path": {"type": "string", "default": "."}, "auto_approve": {"type": "boolean", "default": True}, "var_file": {"type": "string"}}}},
    {"name": "ansible_playbook", "description": "Run an Ansible playbook", "parameters": {"type": "object", "properties": {"playbook": {"type": "string", "description": "Path to playbook YAML"}, "inventory": {"type": "string", "description": "Inventory file or host list"}, "tags": {"type": "string", "description": "Tags to run"}}, "required": ["playbook"]}},
    {"name": "ansible_inventory", "description": "List Ansible inventory hosts", "parameters": {"type": "object", "properties": {"inventory": {"type": "string", "description": "Inventory file path"}, "list": {"type": "boolean", "default": True}}}},
    {"name": "nginx_test", "description": "Test Nginx configuration syntax", "parameters": {"type": "object", "properties": {"config_path": {"type": "string", "description": "Path to nginx.conf (optional)"}}}},
    {"name": "nginx_reload", "description": "Reload Nginx configuration without downtime", "parameters": {"type": "object", "properties": {}}},
    {"name": "ssl_check", "description": "Check SSL certificate details for a domain", "parameters": {"type": "object", "properties": {"domain": {"type": "string", "description": "Domain to check"}, "port": {"type": "integer", "default": 443}}, "required": ["domain"]}},
    {"name": "dns_lookup", "description": "Perform DNS lookup for a domain", "parameters": {"type": "object", "properties": {"domain": {"type": "string", "description": "Domain to look up"}, "record_type": {"type": "string", "enum": ["A", "AAAA", "CNAME", "MX", "TXT", "NS"], "default": "A"}}, "required": ["domain"]}},
    {"name": "traceroute", "description": "Trace the network route to a host", "parameters": {"type": "object", "properties": {"host": {"type": "string", "description": "Target host"}, "max_hops": {"type": "integer", "default": 30}}, "required": ["host"]}},
]

functions = {}

async def _run_cmd(cmd, timeout=120):
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    return proc.returncode, stdout.decode(errors="ignore").strip()

async def terraform_init(args):
    path = args.get("path", ".")
    if not shutil.which("terraform"):
        return json.dumps({"error": "terraform not found in PATH", "success": False})
    try:
        code, output = await _run_cmd(["terraform", "init"], timeout=120)
        return json.dumps({"success": code == 0, "output": output[-3000:]})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def terraform_plan(args):
    path = args.get("path", ".")
    cmd = ["terraform", "plan"]
    if args.get("var_file"):
        cmd.extend(["-var-file", args["var_file"]])
    try:
        code, output = await _run_cmd(cmd, timeout=180)
        return json.dumps({"success": code == 0, "output": output[-5000:]})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def terraform_apply(args):
    path = args.get("path", ".")
    cmd = ["terraform", "apply"]
    if args.get("auto_approve", True):
        cmd.append("-auto-approve")
    if args.get("var_file"):
        cmd.extend(["-var-file", args["var_file"]])
    try:
        code, output = await _run_cmd(cmd, timeout=300)
        return json.dumps({"success": code == 0, "output": output[-5000:]})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def ansible_playbook(args):
    playbook = args["playbook"]
    if not shutil.which("ansible-playbook"):
        return json.dumps({"error": "ansible-playbook not found in PATH", "success": False})
    cmd = ["ansible-playbook", playbook]
    if args.get("inventory"):
        cmd.extend(["-i", args["inventory"]])
    if args.get("tags"):
        cmd.extend(["--tags", args["tags"]])
    try:
        code, output = await _run_cmd(cmd, timeout=300)
        return json.dumps({"success": code == 0, "output": output[-5000:]})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def ansible_inventory(args):
    if not shutil.which("ansible-inventory"):
        return json.dumps({"error": "ansible-inventory not found in PATH", "success": False})
    cmd = ["ansible-inventory", "--list"]
    if args.get("inventory"):
        cmd.extend(["-i", args["inventory"]])
    try:
        code, output = await _run_cmd(cmd, timeout=30)
        return json.dumps({"success": code == 0, "inventory": output[-5000:]})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def nginx_test(args):
    cmd = ["nginx", "-t"]
    if args.get("config_path"):
        cmd.extend(["-c", args["config_path"]])
    try:
        code, output = await _run_cmd(cmd, timeout=10)
        return json.dumps({"success": code == 0, "output": output})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def nginx_reload(args):
    try:
        code, output = await _run_cmd(["nginx", "-s", "reload"], timeout=10)
        return json.dumps({"success": code == 0, "output": output})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def ssl_check(args):
    import ssl
    import socket
    domain = args["domain"]
    port = args.get("port", 443)
    try:
        ctx = ssl.create_default_context()
        with ctx.wrap_socket(socket.socket(), server_hostname=domain) as s:
            s.settimeout(10)
            s.connect((domain, port))
            cert = s.getpeercert()
            return json.dumps({
                "success": True,
                "domain": domain,
                "subject": dict(x[0] for x in cert.get("subject", [])),
                "issuer": dict(x[0] for x in cert.get("issuer", [])),
                "notBefore": cert.get("notBefore"),
                "notAfter": cert.get("notAfter"),
                "serialNumber": cert.get("serialNumber"),
                "sans": [e[1] for e in cert.get("subjectAltName", [])],
            })
    except Exception as e:
        return json.dumps({"error": str(e), "domain": domain})

async def dns_lookup(args):
    import socket
    domain = args["domain"]
    record_type = args.get("record_type", "A")
    try:
        if record_type == "A":
            results = socket.getaddrinfo(domain, None, socket.AF_INET)
            addresses = list(set(r[4][0] for r in results))
        elif record_type == "AAAA":
            results = socket.getaddrinfo(domain, None, socket.AF_INET6)
            addresses = list(set(r[4][0] for r in results))
        else:
            proc = await asyncio.create_subprocess_exec(
                "nslookup", "-type=" + record_type, domain,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            return json.dumps({"success": True, "domain": domain, "type": record_type, "output": stdout.decode(errors="ignore")})
        return json.dumps({"success": True, "domain": domain, "type": record_type, "addresses": addresses})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def traceroute(args):
    host = args["host"]
    max_hops = args.get("max_hops", 30)
    try:
        cmd = ["tracert", "-d", "-h", str(max_hops), host] if shutil.which("tracert") else ["traceroute", "-m", str(max_hops), host]
        code, output = await _run_cmd(cmd, timeout=60)
        return json.dumps({"success": code == 0, "host": host, "output": output[-5000:]})
    except Exception as e:
        return json.dumps({"error": str(e)})

functions = {
    "terraform_init": terraform_init,
    "terraform_plan": terraform_plan,
    "terraform_apply": terraform_apply,
    "ansible_playbook": ansible_playbook,
    "ansible_inventory": ansible_inventory,
    "nginx_test": nginx_test,
    "nginx_reload": nginx_reload,
    "ssl_check": ssl_check,
    "dns_lookup": dns_lookup,
    "traceroute": traceroute,
}
