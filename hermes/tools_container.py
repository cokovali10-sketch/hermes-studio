"""Container management tools for Hermes agent."""
import asyncio
import json
# --- константы вынесены FORGE refactor ---
CONST_120 = 120
CONST_300 = 300
CONST_3000 = 3000
CONST_5000 = 5000


TOOLS = [
    {"name": "docker_build", "description": "Build a Docker image from a Dockerfile", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Path to Dockerfile directory"}, "tag": {"type": "string", "description": "Image tag (name:version)"}}, "required": ["path", "tag"]}},
    {"name": "docker_run", "description": "Run a Docker container", "parameters": {"type": "object", "properties": {"image": {"type": "string", "description": "Image name"}, "ports": {"type": "string", "description": "Port mappings (e.g. 8080:80)"}, "detach": {"type": "boolean", "description": "Run in background", "default": True}, "name": {"type": "string", "description": "Container name"}}, "required": ["image"]}},
    {"name": "docker_stop", "description": "Stop a running container", "parameters": {"type": "object", "properties": {"container": {"type": "string", "description": "Container ID or name"}}, "required": ["container"]}},
    {"name": "docker_logs", "description": "Get container logs", "parameters": {"type": "object", "properties": {"container": {"type": "string", "description": "Container ID or name"}, "lines": {"type": "integer", "description": "Number of recent lines", "default": 100}}, "required": ["container"]}},
    {"name": "docker_ps", "description": "List containers (running by default, or all)", "parameters": {"type": "object", "properties": {"all": {"type": "boolean", "description": "Show all containers including stopped", "default": False}}}},
    {"name": "docker_compose_up", "description": "Start services via docker compose up", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Path to docker-compose.yml directory"}, "detach": {"type": "boolean", "default": True}, "build": {"type": "boolean", "description": "Build images before starting", "default": False}}}},
    {"name": "docker_compose_down", "description": "Stop and remove docker compose services", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Path to docker-compose.yml directory"}, "volumes": {"type": "boolean", "description": "Also remove volumes", "default": False}}}},
    {"name": "docker_exec", "description": "Execute a command in a running container", "parameters": {"type": "object", "properties": {"container": {"type": "string", "description": "Container ID or name"}, "command": {"type": "string", "description": "Command to execute"}}, "required": ["container", "command"]}},
    {"name": "docker_push", "description": "Push a Docker image to a registry", "parameters": {"type": "object", "properties": {"image": {"type": "string", "description": "Image name with tag"}}, "required": ["image"]}},
    {"name": "docker_pull", "description": "Pull a Docker image from a registry", "parameters": {"type": "object", "properties": {"image": {"type": "string", "description": "Image name with tag"}}, "required": ["image"]}},
]

functions = {}

async def _run_cmd(cmd, timeout=CONST_120):
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    return proc.returncode, stdout.decode(errors="ignore").strip()

async def docker_build(args):
    path = args.get("path", ".")
    tag = args.get("tag", "myapp:latest")
    try:
        code, output = await _run_cmd(["docker", "build", "-t", tag, path], timeout=CONST_300)
        return json.dumps({"success": code == 0, "tag": tag, "output": output[-CONST_3000:]})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def docker_run(args):
    image = args["image"]
    cmd = ["docker", "run"]
    if args.get("detach", True):
        cmd.append("-d")
    if args.get("ports"):
        cmd.extend(["-p", args["ports"]])
    if args.get("name"):
        cmd.extend(["--name", args["name"]])
    cmd.append(image)
    try:
        code, output = await _run_cmd(cmd, timeout=60)
        return json.dumps({"success": code == 0, "output": output})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def docker_stop(args):
    container = args["container"]
    try:
        code, output = await _run_cmd(["docker", "stop", container])
        return json.dumps({"success": code == 0, "container": container, "output": output})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def docker_logs(args):
    container = args["container"]
    lines = args.get("lines", 100)
    try:
        code, output = await _run_cmd(["docker", "logs", "--tail", str(lines), container])
        return json.dumps({"success": code == 0, "container": container, "logs": output[-CONST_5000:]})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def docker_ps(args):
    show_all = args.get("all", False)
    cmd = ["docker", "ps", "-a"] if show_all else ["docker", "ps"]
    cmd.extend(["--format", "table {{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Image}}\t{{.Ports}}"])
    try:
        code, output = await _run_cmd(cmd)
        return json.dumps({"success": code == 0, "containers": output})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def docker_compose_up(args):
    path = args.get("path", ".")
    cmd = ["docker", "compose", "-f", f"{path}/docker-compose.yml", "up"]
    if args.get("detach", True):
        cmd.append("-d")
    if args.get("build"):
        cmd.append("--build")
    try:
        code, output = await _run_cmd(cmd, timeout=CONST_300)
        return json.dumps({"success": code == 0, "output": output[-CONST_3000:]})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def docker_compose_down(args):
    path = args.get("path", ".")
    cmd = ["docker", "compose", "-f", f"{path}/docker-compose.yml", "down"]
    if args.get("volumes"):
        cmd.append("-v")
    try:
        code, output = await _run_cmd(cmd, timeout=CONST_120)
        return json.dumps({"success": code == 0, "output": output})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def docker_exec(args):
    container = args["container"]
    command = args["command"]
    try:
        code, output = await _run_cmd(["docker", "exec", container] + command.split())
        return json.dumps({"success": code == 0, "container": container, "output": output[-CONST_5000:]})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def docker_push(args):
    image = args["image"]
    try:
        code, output = await _run_cmd(["docker", "push", image], timeout=CONST_300)
        return json.dumps({"success": code == 0, "image": image, "output": output[-CONST_3000:]})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def docker_pull(args):
    image = args["image"]
    try:
        code, output = await _run_cmd(["docker", "pull", image], timeout=CONST_300)
        return json.dumps({"success": code == 0, "image": image, "output": output[-CONST_3000:]})
    except Exception as e:
        return json.dumps({"error": str(e)})

functions = {
    "docker_build": docker_build,
    "docker_run": docker_run,
    "docker_stop": docker_stop,
    "docker_logs": docker_logs,
    "docker_ps": docker_ps,
    "docker_compose_up": docker_compose_up,
    "docker_compose_down": docker_compose_down,
    "docker_exec": docker_exec,
    "docker_push": docker_push,
    "docker_pull": docker_pull,
}
