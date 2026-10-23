"""System monitoring tools for Hermes agent."""
import asyncio
import json
import os
import platform
import sys
# --- константы вынесены FORGE refactor ---
CONST_3 = 3
CONST_4 = 4
CONST_5 = 5
CONST_6 = 6
CONST_7 = 7
CONST_15 = 15
CONST_30 = 30


TOOLS = [
    {"name": "monitor_processes", "description": "List running processes with CPU/memory usage", "parameters": {"type": "object", "properties": {"filter": {"type": "string", "description": "Filter by process name"}, "sort_by": {"type": "string", "enum": ["cpu", "memory", "name", "pid"], "description": "Sort results", "default": "cpu"}, "limit": {"type": "integer", "description": "Max processes to return", "default": CONST_30}}}},
    {"name": "monitor_network", "description": "Show network connections and traffic stats", "parameters": {"type": "object", "properties": {"connections_only": {"type": "boolean", "description": "Show only connections (no stats)", "default": False}}}},
    {"name": "monitor_disk_io", "description": "Show disk read/write speeds and I/O stats", "parameters": {"type": "object", "properties": {"interval": {"type": "integer", "description": "Sampling interval in seconds", "default": CONST_3}}}},
    {"name": "monitor_gpu", "description": "Show GPU usage via nvidia-smi", "parameters": {"type": "object", "properties": {}}},
    {"name": "monitor_docker", "description": "Show Docker container resource stats", "parameters": {"type": "object", "properties": {}}},
    {"name": "monitor_services", "description": "Show Windows/Linux services status", "parameters": {"type": "object", "properties": {"filter": {"type": "string", "description": "Filter services by name"}, "running_only": {"type": "boolean", "description": "Show only running services", "default": False}}}},
    {"name": "monitor_scheduled_tasks", "description": "Show cron jobs (Linux) or scheduled tasks (Windows)", "parameters": {"type": "object", "properties": {}}},
    {"name": "monitor_open_ports", "description": "Show listening ports and associated processes", "parameters": {"type": "object", "properties": {"filter_port": {"type": "integer", "description": "Filter by specific port"}}}},
    {"name": "monitor_env_vars", "description": "Show environment variables (optionally filtered)", "parameters": {"type": "object", "properties": {"filter": {"type": "string", "description": "Filter variable names containing this string"}, "show_values": {"type": "boolean", "description": "Show variable values", "default": True}}}},
    {"name": "monitor_system_info", "description": "Show detailed system information (OS, CPU, RAM, disk, network)", "parameters": {"type": "object", "properties": {}}},
]

functions = {}

async def monitor_processes(args):
    sort_by = args.get("sort_by", "cpu")
    limit = args.get("limit", CONST_30)
    filt = args.get("filter", "")
    try:
        code = f"""
import psutil, json
procs = []
for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'memory_info', 'status', 'username', 'create_time']):
    try:
        info = p.info
        procs.append({{
            'pid': info['pid'],
            'name': info['name'],
            'cpu_percent': round(info['cpu_percent'] or 0, 1),
            'memory_percent': round(info['memory_percent'] or 0, 1),
            'memory_mb': round((info['memory_info'].rss if info['memory_info'] else 0) / 1024 / 1024, 1),
            'status': info['status'],
            'user': info.get('username', ''),
        }})
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
procs.sort(key=lambda x: x.get('{sort_by}', x.get('cpu_percent', 0)) or 0, reverse=True)
print(json.dumps(procs[:{limit}]))
"""
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-c", code,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        data = json.loads(stdout.decode(errors="ignore").strip())
        if filt:
            data = [p for p in data if filt.lower() in p["name"].lower()]
        return json.dumps({"processes": data, "count": len(data), "sort_by": sort_by})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def monitor_network(args):
    conns_only = args.get("connections_only", False)
    try:
        code = """
import psutil, json
conns = []
for c in psutil.net_connections(kind='inet'):
    try:
        conns.append({
            'fd': c.fd,
            'family': str(c.family),
            'type': str(c.type),
            'laddr': f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else "",
            'raddr': f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else "",
            'status': c.status,
            'pid': c.pid,
        })
    except Exception:
        pass

io = psutil.net_io_counters()
stats = {
    'bytes_sent': io.bytes_sent,
    'bytes_recv': io.bytes_recv,
    'packets_sent': io.packets_sent,
    'packets_recv': io.packets_recv,
    'errin': io.errin,
    'errout': io.errout,
}

print(json.dumps({'connections': conns, 'stats': stats, 'total_connections': len(conns)}))
"""
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-c", code,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        data = json.loads(stdout.decode(errors="ignore").strip())
        if conns_only:
            data.pop("stats", None)
        return json.dumps(data)
    except Exception as e:
        return json.dumps({"error": str(e)})

async def monitor_disk_io(args):
    interval = args.get("interval", CONST_3)
    try:
        code = f"""
import psutil, json, time
d1 = psutil.disk_io_counters()
time.sleep({interval})
d2 = psutil.disk_io_counters()
result = {{
    'read_speed_mbps': round((d2.read_bytes - d1.read_bytes) / {interval} / 1024 / 1024, 2) if d1 and d2 else 0,
    'write_speed_mbps': round((d2.write_bytes - d1.write_bytes) / {interval} / 1024 / 1024, 2) if d1 and d2 else 0,
    'total_read_gb': round(d2.read_bytes / 1024**3, 2) if d2 else 0,
    'total_written_gb': round(d2.write_bytes / 1024**3, 2) if d2 else 0,
    'read_count': d2.read_count if d2 else 0,
    'write_count': d2.write_count if d2 else 0,
    'read_time_ms': d2.read_time if d2 else 0,
    'write_time_ms': d2.write_time if d2 else 0,
}}
partitions = []
for p in psutil.disk_partitions(all=False):
    try:
        usage = psutil.disk_usage(p.mountpoint)
        partitions.append({{
            'device': p.device,
            'mountpoint': p.mountpoint,
            'fstype': p.fstype,
            'total_gb': round(usage.total / 1024**3, 2),
            'used_gb': round(usage.used / 1024**3, 2),
            'free_gb': round(usage.free / 1024**3, 2),
            'percent': usage.percent,
        }})
    except Exception:
        pass
result['partitions'] = partitions
print(json.dumps(result))
"""
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-c", code,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=CONST_30)
        return stdout.decode(errors="ignore").strip()
    except Exception as e:
        return json.dumps({"error": str(e)})

async def monitor_gpu(args):
    try:
        proc = await asyncio.create_subprocess_exec(
            "nvidia-smi", "--query-gpu=name,temperature.gpu,utilization.gpu,utilization.memory,memory.total,memory.used,memory.free,power.draw",
            "--format=csv,noheader,nounits",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        output = stdout.decode(errors="ignore").strip()
        if proc.returncode != 0:
            return json.dumps({"error": "nvidia-smi not available or no GPU detected", "output": output, "success": False})
        gpus = []
        for line in output.split("\n"):
            if line.strip():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 8:
                    gpus.append({
                        "name": parts[0],
                        "temperature_c": parts[1],
                        "gpu_utilization": parts[2],
                        "memory_utilization": parts[CONST_3],
                        "memory_total_mb": parts[CONST_4],
                        "memory_used_mb": parts[CONST_5],
                        "memory_free_mb": parts[CONST_6],
                        "power_draw_w": parts[CONST_7],
                    })
        return json.dumps({"gpus": gpus, "count": len(gpus)})
    except FileNotFoundError:
        return json.dumps({"error": "nvidia-smi not found. Is NVIDIA driver installed?"})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def monitor_docker(args):
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "stats", "--no-stream", "--format",
            "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.NetIO}}\t{{.BlockIO}}\t{{.PIDs}}",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=CONST_15)
        output = stdout.decode(errors="ignore").strip()
        if proc.returncode != 0:
            return json.dumps({"error": "Docker not running or no containers", "success": False})
        containers = []
        for line in output.split("\n"):
            if line.strip():
                parts = line.split("\t")
                if len(parts) >= CONST_7:
                    containers.append({
                        "name": parts[0],
                        "cpu": parts[1],
                        "memory": parts[2],
                        "memory_percent": parts[CONST_3],
                        "network_io": parts[CONST_4],
                        "block_io": parts[CONST_5],
                        "pids": parts[CONST_6],
                    })
        return json.dumps({"containers": containers, "count": len(containers)})
    except FileNotFoundError:
        return json.dumps({"error": "Docker not installed"})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def monitor_services(args):
    filt = args.get("filter", "")
    running_only = args.get("running_only", False)
    try:
        if sys.platform == "win32":
            cmd = 'powershell -Command "Get-Service | Select-Object Name,Status,DisplayName | ConvertTo-Json"'
            if filt:
                cmd = f'powershell -Command "Get-Service -Name *{filt}* | Select-Object Name,Status,DisplayName | ConvertTo-Json"'
            proc = await asyncio.create_subprocess_shell(
                cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=CONST_15)
            data = json.loads(stdout.decode(errors="ignore").strip())
            if isinstance(data, dict):
                data = [data]
            services = [{"name": s["Name"], "status": s["Status"], "display_name": s["DisplayName"]} for s in data]
        else:
            proc = await asyncio.create_subprocess_exec(
                "systemctl", "list-units", "--type=service", "--all", "--no-pager", "--plain", "--no-legend",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=CONST_15)
            services = []
            for line in stdout.decode(errors="ignore").strip().split("\n"):
                parts = line.split()
                if len(parts) >= CONST_4:
                    name = parts[0].replace(".service", "")
                    if filt and filt.lower() not in name.lower():
                        continue
                    services.append({"name": name, "status": parts[2], "display_name": " ".join(parts[CONST_3:])})
        if running_only:
            services = [s for s in services if s["status"].lower() in ("running", "active")]
        return json.dumps({"services": services, "count": len(services)})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def monitor_scheduled_tasks(args):
    try:
        if sys.platform == "win32":
            proc = await asyncio.create_subprocess_shell(
                'powershell -Command "Get-ScheduledTask | Where-Object {$_.State -ne \'Disabled\'} | Select-Object TaskName,TaskPath,State,@{N=\'Actions\';E={($_.Actions | ForEach-Object {$_.Execute}) -join \',\'}} | ConvertTo-Json"',
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=CONST_15)
            data = json.loads(stdout.decode(errors="ignore").strip())
            if isinstance(data, dict):
                data = [data]
            tasks = [{"name": t["TaskName"], "path": t["TaskPath"], "state": t["State"], "actions": t.get("Actions", "")} for t in data]
        else:
            proc = await asyncio.create_subprocess_exec(
                "crontab", "-l", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=CONST_5)
            tasks = []
            for line in stdout.decode(errors="ignore").strip().split("\n"):
                line = line.strip()
                if line and not line.startswith("#"):
                    tasks.append({"raw": line})
        return json.dumps({"tasks": tasks, "count": len(tasks)})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def monitor_open_ports(args):
    filter_port = args.get("filter_port")
    try:
        code = """
import psutil, json
listeners = []
for c in psutil.net_connections(kind='inet'):
    if c.status == 'LISTEN':
        listeners.append({
            'port': c.laddr.port,
            'ip': c.laddr.ip,
            'protocol': 'TCP' if c.type == 1 else 'UDP',
            'pid': c.pid,
            'status': c.status,
        })
print(json.dumps(listeners))
"""
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-c", code,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        ports = json.loads(stdout.decode(errors="ignore").strip())
        if filter_port is not None:
            ports = [p for p in ports if p["port"] == filter_port]
        return json.dumps({"listening_ports": ports, "count": len(ports)})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def monitor_env_vars(args):
    filt = args.get("filter", "")
    show_values = args.get("show_values", True)
    try:
        env_vars = {}
        for k, v in sorted(os.environ.items()):
            if filt and filt.lower() not in k.lower():
                continue
            env_vars[k] = v if show_values else "***"
        sensitive = {"password", "secret", "key", "token", "credential"}
        masked = {}
        for k, v in env_vars.items():
            if any(s in k.lower() for s in sensitive) and show_values:
                masked[k] = v[:CONST_4] + "***" if len(v) > CONST_4 else "***"
            else:
                masked[k] = v
        return json.dumps({"variables": masked, "count": len(masked), "total_env_vars": len(os.environ)})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def monitor_system_info(args):
    try:
        code = """
import psutil, json, platform, os
disk = psutil.disk_usage('/')
mem = psutil.virtual_memory()
net = psutil.net_if_addrs()
result = {
    'os': platform.platform(),
    'os_type': sys.platform if 'sys' in dir() else platform.system(),
    'architecture': platform.machine(),
    'processor': platform.processor(),
    'python_version': platform.python_version(),
    'hostname': platform.node(),
    'cpu_count_logical': psutil.cpu_count(),
    'cpu_count_physical': psutil.cpu_count(logical=False),
    'cpu_percent': psutil.cpu_percent(interval=1),
    'cpu_freq_mhz': dict(psutil.cpu_freq()._asdict()) if psutil.cpu_freq() else None,
    'memory_total_gb': round(mem.total / 1024**3, 2),
    'memory_available_gb': round(mem.available / 1024**3, 2),
    'memory_used_gb': round(mem.used / 1024**3, 2),
    'memory_percent': mem.percent,
    'disk_total_gb': round(disk.total / 1024**3, 2),
    'disk_used_gb': round(disk.used / 1024**3, 2),
    'disk_free_gb': round(disk.free / 1024**3, 2),
    'disk_percent': disk.percent,
    'boot_time': psutil.boot_time(),
    'uptime_seconds': psutil.time.time() - psutil.boot_time(),
    'network_interfaces': {},
}
for iface, addrs in net.items():
    result['network_interfaces'][iface] = [{'address': a.address, 'family': str(a.family)} for a in addrs]
print(json.dumps(result))
"""
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-c", code,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        return stdout.decode(errors="ignore").strip()
    except Exception as e:
        return json.dumps({"error": str(e)})

functions = {
    "monitor_processes": monitor_processes,
    "monitor_network": monitor_network,
    "monitor_disk_io": monitor_disk_io,
    "monitor_gpu": monitor_gpu,
    "monitor_docker": monitor_docker,
    "monitor_services": monitor_services,
    "monitor_scheduled_tasks": monitor_scheduled_tasks,
    "monitor_open_ports": monitor_open_ports,
    "monitor_env_vars": monitor_env_vars,
    "monitor_system_info": monitor_system_info,
}
