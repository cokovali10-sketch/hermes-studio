"""Docker management tools for Hermes agent."""
import asyncio
import json
import os
# --- константы вынесены FORGE refactor ---
CONST_3 = 3
CONST_4 = 4
CONST_15 = 15
CONST_50 = 50
CONST_60 = 60
CONST_2000 = 2000


TOOLS = [
    {"name": "docker_build", "description": "Build a Docker image from a Dockerfile", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Path to Dockerfile directory"}, "tag": {"type": "string", "description": "Image tag (name:version)"}}, "required": ["path", "tag"]}},
    {"name": "docker_run", "description": "Run a Docker container", "parameters": {"type": "object", "properties": {"image": {"type": "string", "description": "Image name"}, "ports": {"type": "string", "description": "Port mappings (e.g. 8080:80)"}, "detach": {"type": "boolean", "description": "Run in background", "default": True}}, "required": ["image"]}},
    {"name": "docker_stop", "description": "Stop a running container", "parameters": {"type": "object", "properties": {"container": {"type": "string", "description": "Container ID or name"}}, "required": ["container"]}},
    {"name": "docker_list", "description": "List Docker containers (running or all)", "parameters": {"type": "object", "properties": {"all": {"type": "boolean", "description": "Show all containers", "default": False}}}},
    {"name": "docker_logs", "description": "Get container logs", "parameters": {"type": "object", "properties": {"container": {"type": "string", "description": "Container ID or name"}, "lines": {"type": "integer", "description": "Number of lines to show", "default": CONST_50}}, "required": ["container"]}},
    {"name": "docker_compose", "description": "Run docker-compose commands", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Path to docker-compose.yml"}, "command": {"type": "string", "description": "Compose command (up, down, ps, logs)"}}, "required": ["command"]}},
    {"name": "docker_images", "description": "List Docker images", "parameters": {"type": "object", "properties": {}}},
    {"name": "docker_exec", "description": "Execute command in running container", "parameters": {"type": "object", "properties": {"container": {"type": "string", "description": "Container ID"}, "command": {"type": "string", "description": "Command to execute"}}, "required": ["container", "command"]}},
    {"name": "docker_stats", "description": "Show container resource usage", "parameters": {"type": "object", "properties": {"container": {"type": "string", "description": "Container ID (optional, shows all if empty)"}}}},
    {"name": "docker_clean", "description": "Clean up unused Docker resources", "parameters": {"type": "object", "properties": {"all": {"type": "boolean", "description": "Remove all unused images, not just dangling", "default": False}}}},
]

functions = {}

async def docker_build(args):
    path = args.get("path", ".")
    tag = args.get("tag", "myapp:latest")
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "build", "-t", tag, path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=300)
        output = stdout.decode(errors="ignore")[-CONST_2000:]
        return json.dumps({"success": proc.returncode == 0, "tag": tag, "output": output})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def docker_run(args):
    image = args["image"]
    ports = args.get("ports", "")
    detach = args.get("detach", True)
    cmd = ["docker", "run", "-d" if detach else "-it"]
    if ports:
        cmd.extend(["-p", ports])
    cmd.append(image)
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=CONST_60)
        return json.dumps({"success": proc.returncode == 0, "output": stdout.decode(errors="ignore").strip()})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def docker_stop(args):
    container = args["container"]
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "stop", container,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
        return json.dumps({"success": proc.returncode == 0, "output": stdout.decode(errors="ignore").strip()})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def docker_list(args):
    show_all = args.get("all", False)
    cmd = ["docker", "ps", "-a" if show_all else "", "--format", "{{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Image}}"]
    cmd = [c for c in cmd if c]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=CONST_15)
        containers = []
        for line in stdout.decode(errors="ignore").strip().split("\n"):
            if line:
                parts = line.split("\t")
                if len(parts) >= CONST_4:
                    containers.append({"id": parts[0], "name": parts[1], "status": parts[2], "image": parts[CONST_3]})
        return json.dumps({"containers": containers, "count": len(containers)})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def docker_logs(args):
    container = args["container"]
    lines = args.get("lines", CONST_50)
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "logs", "--tail", str(lines), container,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=CONST_15)
        return json.dumps({"container": container, "logs": stdout.decode(errors="ignore")[-3000:]})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def docker_compose(args):
    path = args.get("path", ".")
    command = args["command"]
    cmd_parts = command.split()
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker-compose", "-f", os.path.join(path, "docker-compose.yml"), *cmd_parts,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
        return json.dumps({"success": proc.returncode == 0, "output": stdout.decode(errors="ignore")[-CONST_2000:]})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def docker_images(args):
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "images", "--format", "{{.Repository}}:{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=CONST_15)
        images = []
        for line in stdout.decode(errors="ignore").strip().split("\n"):
            if line:
                parts = line.split("\t")
                if len(parts) >= CONST_3:
                    images.append({"image": parts[0], "size": parts[1], "created": parts[2]})
        return json.dumps({"images": images, "count": len(images)})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def docker_exec(args):
    container = args["container"]
    command = args["command"]
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "exec", container, *command.split(),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=CONST_60)
        return json.dumps({"success": proc.returncode == 0, "output": stdout.decode(errors="ignore")[-CONST_2000:]})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def docker_stats(args):
    container = args.get("container", "")
    cmd = ["docker", "stats", "--no-stream", "--format", "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}"]
    if container:
        cmd.append(container)
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=CONST_15)
        stats = []
        for line in stdout.decode(errors="ignore").strip().split("\n"):
            if line:
                parts = line.split("\t")
                if len(parts) >= CONST_4:
                    stats.append({"name": parts[0], "cpu": parts[1], "memory": parts[2], "network": parts[CONST_3]})
        return json.dumps({"stats": stats})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def docker_clean(args):
    all_resources = args.get("all", False)
    cmd = ["docker", "system", "prune", "-f"]
    if all_resources:
        cmd.append("-a")
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=CONST_60)
        return json.dumps({"success": proc.returncode == 0, "output": stdout.decode(errors="ignore")})
    except Exception as e:
        return json.dumps({"error": str(e)})

functions = {
    "docker_build": docker_build, "docker_run": docker_run, "docker_stop": docker_stop,
    "docker_list": docker_list, "docker_logs": docker_logs, "docker_compose": docker_compose,
    "docker_images": docker_images, "docker_exec": docker_exec, "docker_stats": docker_stats,
    "docker_clean": docker_clean,
}
