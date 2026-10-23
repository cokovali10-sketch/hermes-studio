"""Kubernetes management tools for Hermes agent."""
import asyncio
import json
# --- константы вынесены FORGE refactor ---
CONST_3000 = 3000


TOOLS = [
    {"name": "k8s_get_pods", "description": "Get Kubernetes pods", "parameters": {"type": "object", "properties": {"namespace": {"type": "string", "default": "default"}}}},
    {"name": "k8s_get_services", "description": "Get Kubernetes services", "parameters": {"type": "object", "properties": {"namespace": {"type": "string", "default": "default"}}}},
    {"name": "k8s_describe", "description": "Describe a Kubernetes resource", "parameters": {"type": "object", "properties": {"resource": {"type": "string", "description": "Resource type (pod, service, deployment)"}, "name": {"type": "string"}, "namespace": {"type": "string", "default": "default"}}, "required": ["resource", "name"]}},
    {"name": "k8s_logs", "description": "Get pod logs", "parameters": {"type": "object", "properties": {"pod": {"type": "string"}, "namespace": {"type": "string", "default": "default"}, "lines": {"type": "integer", "default": 100}}, "required": ["pod"]}},
    {"name": "k8s_exec", "description": "Execute command in a pod", "parameters": {"type": "object", "properties": {"pod": {"type": "string"}, "namespace": {"type": "string", "default": "default"}, "command": {"type": "string"}, "container": {"type": "string"}}, "required": ["pod", "command"]}},
    {"name": "k8s_scale", "description": "Scale a deployment", "parameters": {"type": "object", "properties": {"deployment": {"type": "string"}, "replicas": {"type": "integer"}, "namespace": {"type": "string", "default": "default"}}, "required": ["deployment", "replicas"]}},
    {"name": "k8s_apply", "description": "Apply a Kubernetes manifest", "parameters": {"type": "object", "properties": {"file": {"type": "string", "description": "Path to YAML/JSON manifest"}}, "required": ["file"]}},
    {"name": "k8s_delete", "description": "Delete a Kubernetes resource", "parameters": {"type": "object", "properties": {"resource": {"type": "string"}, "name": {"type": "string"}, "namespace": {"type": "string", "default": "default"}}, "required": ["resource", "name"]}},
    {"name": "k8s_events", "description": "Get cluster events", "parameters": {"type": "object", "properties": {"namespace": {"type": "string", "default": "default"}, "reason": {"type": "string"}}}},
    {"name": "k8s_context", "description": "Show current kubectl context", "parameters": {"type": "object", "properties": {}}},
]

functions = {}

async def _run_kubectl(args, *cmd):
    namespace = args.get("namespace", "default")
    full_cmd = ["kubectl", "-n", namespace] + list(cmd)
    try:
        proc = await asyncio.create_subprocess_exec(
            *full_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
        return stdout.decode(errors="ignore").strip()
    except Exception as e:
        return str(e)

async def k8s_get_pods(args):
    output = await _run_kubectl(args, "get", "pods", "-o", "json")
    try:
        data = json.loads(output)
        pods = [{"name": item["metadata"]["name"], "status": item["status"]["phase"], "ready": all(c["ready"] for c in item["status"].get("containerStatuses", [])), "restarts": sum(c["restartCount"] for c in item["status"].get("containerStatuses", []))} for item in data.get("items", [])]
        return json.dumps({"pods": pods, "count": len(pods)})
    except:
        return json.dumps({"output": output})

async def k8s_get_services(args):
    output = await _run_kubectl(args, "get", "services", "-o", "json")
    try:
        data = json.loads(output)
        services = [{"name": item["metadata"]["name"], "type": item["spec"]["type"], "cluster_ip": item["spec"]["clusterIP"], "ports": [f"{p['port']}/{p['protocol']}" for p in item["spec"]["ports"]]} for item in data.get("items", [])]
        return json.dumps({"services": services, "count": len(services)})
    except:
        return json.dumps({"output": output})

async def k8s_describe(args):
    output = await _run_kubectl(args, "describe", args["resource"], args["name"])
    return json.dumps({"resource": args["resource"], "name": args["name"], "output": output[-CONST_3000:]})

async def k8s_logs(args):
    pod = args["pod"]
    lines = args.get("lines", 100)
    container = args.get("container", "")
    cmd = ["logs", pod, f"--tail={lines}"]
    if container:
        cmd.extend(["-c", container])
    output = await _run_kubectl(args, *cmd)
    return json.dumps({"pod": pod, "logs": output[-5000:]})

async def k8s_exec(args):
    pod = args["pod"]
    command = args["command"]
    container = args.get("container", "")
    cmd = ["exec", pod]
    if container:
        cmd.extend(["-c", container])
    cmd.extend(["--", *command.split()])
    output = await _run_kubectl(args, *cmd)
    return json.dumps({"pod": pod, "command": command, "output": output[-CONST_3000:]})

async def k8s_scale(args):
    deployment = args["deployment"]
    replicas = args["replicas"]
    output = await _run_kubectl(args, "scale", f"deployment/{deployment}", f"--replicas={replicas}")
    return json.dumps({"deployment": deployment, "replicas": replicas, "output": output})

async def k8s_apply(args):
    file_path = args["file"]
    output = await _run_kubectl(args, "apply", "-f", file_path)
    return json.dumps({"file": file_path, "output": output})

async def k8s_delete(args):
    output = await _run_kubectl(args, "delete", args["resource"], args["name"])
    return json.dumps({"resource": args["resource"], "name": args["name"], "output": output})

async def k8s_events(args):
    reason = args.get("reason", "")
    cmd = ["get", "events", "-o", "json"]
    if reason:
        cmd.extend(["--field-selector", f"reason={reason}"])
    output = await _run_kubectl(args, *cmd)
    try:
        data = json.loads(output)
        events = [{"type": item["type"], "reason": item["reason"], "message": item["message"][:200], "count": item["count"]} for item in data.get("items", [])[-50:]]
        return json.dumps({"events": events, "count": len(events)})
    except:
        return json.dumps({"output": output[-CONST_3000:]})

async def k8s_context(args):
    try:
        proc = await asyncio.create_subprocess_exec(
            "kubectl", "config", "current-context",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        proc2 = await asyncio.create_subprocess_exec(
            "kubectl", "config", "view", "-o", "json",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        stdout2, _ = await asyncio.wait_for(proc2.communicate(), timeout=10)
        return json.dumps({"current_context": stdout.decode(errors="ignore").strip(), "config": stdout2.decode(errors="ignore")[-2000:]})
    except Exception as e:
        return json.dumps({"error": str(e)})

functions = {
    "k8s_get_pods": k8s_get_pods, "k8s_get_services": k8s_get_services, "k8s_describe": k8s_describe,
    "k8s_logs": k8s_logs, "k8s_exec": k8s_exec, "k8s_scale": k8s_scale,
    "k8s_apply": k8s_apply, "k8s_delete": k8s_delete, "k8s_events": k8s_events,
    "k8s_context": k8s_context,
}
