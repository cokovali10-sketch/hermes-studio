"""Performance profiling tools for Hermes agent."""
import asyncio
import json
import os
import time
import cProfile
import pstats
import io
# --- константы вынесены FORGE refactor ---
CONST_3 = 3
CONST_5 = 5
CONST_30 = 30
CONST_120 = 120
CONST_1000 = 1000
CONST_1024 = 1024


TOOLS = [
    {"name": "profile_function", "description": "Profile a Python function's performance", "parameters": {"type": "object", "properties": {"code": {"type": "string", "description": "Python code to profile"}, "iterations": {"type": "integer", "description": "Number of iterations", "default": 100}}, "required": ["code"]}},
    {"name": "benchmark_file", "description": "Benchmark file I/O operations", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "File or directory to benchmark"}, "operations": {"type": "integer", "description": "Number of operations", "default": CONST_1000}}}},
    {"name": "measure_time", "description": "Measure execution time of a command", "parameters": {"type": "object", "properties": {"command": {"type": "string", "description": "Shell command to time"}}, "required": ["command"]}},
    {"name": "memory_usage", "description": "Check current memory usage of a process", "parameters": {"type": "object", "properties": {"pid": {"type": "integer", "description": "Process ID (current if empty)"}}}},
    {"name": "cpu_info", "description": "Get CPU information and load", "parameters": {"type": "object", "properties": {}}},
    {"name": "disk_speed", "description": "Test disk read/write speed", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Path for temp file", "default": "/tmp"}, "size_mb": {"type": "integer", "description": "Test file size in MB", "default": 100}}}},
    {"name": "network_latency", "description": "Measure network latency to a host", "parameters": {"type": "object", "properties": {"host": {"type": "string", "description": "Target host"}, "count": {"type": "integer", "description": "Number of pings", "default": CONST_5}}, "required": ["host"]}},
    {"name": "find_slow_code", "description": "Find slow functions in a Python file", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Python file to analyze"}, "threshold_ms": {"type": "number", "description": "Slow threshold in ms", "default": 100}}, "required": ["path"]}},
]

functions = {}

async def profile_function(args):
    code = args["code"]
    iterations = args.get("iterations", 100)

    full_code = f"""
import time, cProfile, pstats, io
pr = cProfile.Profile()
pr.enable()
for _ in range({iterations}):
    {code}
pr.disable()
s = io.StringIO()
ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
ps.print_stats(20)
print(s.getvalue())
print(f"Total time: {{pr.getstats()[-1].totaltime if pr.getstats() else 0:.4f}}s")
"""
    try:
        proc = await asyncio.create_subprocess_exec(
            "python", "-c", full_code,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=CONST_30)
        return json.dumps({"success": proc.returncode == 0, "output": stdout.decode(errors="ignore")[-3000:], "iterations": iterations})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def benchmark_file(args):
    path = args.get("path", "/tmp")
    ops = args.get("operations", CONST_1000)

    test_file = os.path.join(path, "hermes_bench_test.tmp")
    data = b"x" * 4096

    start = time.time()
    for _ in range(ops):
        with open(test_file, 'wb') as f:
            f.write(data)
    write_time = time.time() - start

    start = time.time()
    for _ in range(ops):
        with open(test_file, 'rb') as f:
            f.read()
    read_time = time.time() - start

    try:
        os.remove(test_file)
    except:
        pass

    return json.dumps({
        "write_ops": ops, "write_time": round(write_time, CONST_3),
        "read_ops": ops, "read_time": round(read_time, CONST_3),
        "write_ops_sec": round(ops / write_time) if write_time > 0 else 0,
        "read_ops_sec": round(ops / read_time) if read_time > 0 else 0,
    })

async def measure_time(args):
    command = args["command"]
    start = time.time()
    try:
        proc = await asyncio.create_subprocess_shell(
            command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
        elapsed = time.time() - start
        return json.dumps({"command": command, "elapsed_seconds": round(elapsed, CONST_3), "exit_code": proc.returncode, "output": stdout.decode(errors="ignore")[-2000:]})
    except Exception as e:
        return json.dumps({"error": str(e), "elapsed_seconds": round(time.time() - start, CONST_3)})

async def memory_usage(args):
    pid = args.get("pid", os.getpid())
    try:
        proc = await asyncio.create_subprocess_exec(
            "python", "-c", f"""
import psutil, json
p = psutil.Process({pid})
mem = p.memory_info()
print(json.dumps({{
    'pid': {pid},
    'rss_mb': round(mem.rss / 1024 / 1024, 2),
    'vms_mb': round(mem.vms / 1024 / 1024, 2),
    'percent': p.memory_percent(),
    'name': p.name(),
}}))
""",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        return stdout.decode(errors="ignore").strip()
    except Exception as e:
        return json.dumps({"error": str(e)})

async def cpu_info(args):
    try:
        proc = await asyncio.create_subprocess_exec(
            "python", "-c", """
import psutil, json, platform
print(json.dumps({
    'cpu_count': psutil.cpu_count(),
    'cpu_count_physical': psutil.cpu_count(logical=False),
    'cpu_percent': psutil.cpu_percent(interval=1),
    'cpu_freq': dict(psutil.cpu_freq()._asdict()) if psutil.cpu_freq() else None,
    'memory_total_gb': round(psutil.virtual_memory().total / 1024**3, 2),
    'memory_available_gb': round(psutil.virtual_memory().available / 1024**3, 2),
    'memory_percent': psutil.virtual_memory().percent,
    'platform': platform.platform(),
    'processor': platform.processor(),
}))
""",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        return stdout.decode(errors="ignore").strip()
    except Exception as e:
        return json.dumps({"error": str(e)})

async def disk_speed(args):
    path = args.get("path", "/tmp")
    size_mb = args.get("size_mb", 100)
    test_file = os.path.join(path, "hermes_disk_speed_test.tmp")
    data = os.urandom(CONST_1024 * CONST_1024)  # 1MB

    start = time.time()
    with open(test_file, 'wb') as f:
        for _ in range(size_mb):
            f.write(data)
    write_time = time.time() - start

    start = time.time()
    with open(test_file, 'rb') as f:
        while f.read(CONST_1024 * CONST_1024):
            pass
    read_time = time.time() - start

    try:
        os.remove(test_file)
    except:
        pass

    return json.dumps({
        "size_mb": size_mb,
        "write_time": round(write_time, CONST_3),
        "read_time": round(read_time, CONST_3),
        "write_speed_mbps": round(size_mb / write_time, 1) if write_time > 0 else 0,
        "read_speed_mbps": round(size_mb / read_time, 1) if read_time > 0 else 0,
    })

async def network_latency(args):
    host = args["host"]
    count = args.get("count", CONST_5)
    try:
        proc = await asyncio.create_subprocess_exec(
            "ping", "-n", str(count), host,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=CONST_30)
        output = stdout.decode(errors="ignore")

        times = []
        for line in output.split("\n"):
            if "time=" in line.lower():
                import re
                match = re.search(r'time[=<](\d+)', line.lower())
                if match:
                    times.append(int(match.group(1)))

        return json.dumps({
            "host": host, "packets_sent": count, "times_ms": times,
            "avg_ms": round(sum(times) / len(times), 2) if times else 0,
            "min_ms": min(times) if times else 0,
            "max_ms": max(times) if times else 0,
        })
    except Exception as e:
        return json.dumps({"error": str(e)})

async def find_slow_code(args):
    path = args["path"]
    threshold_ms = args.get("threshold_ms", 100)
    issues = []

    try:
        with open(path, 'r', errors='ignore') as f:
            lines = f.readlines()

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if any(kw in stripped for kw in ['time.sleep', 'requests.get', 'requests.post', 'urllib', 'subprocess.run']):
                issues.append({"line": i, "code": stripped[:CONST_120], "reason": "Blocking I/O call"})
            if 'for' in stripped and 'range(1000' in stripped:
                issues.append({"line": i, "code": stripped[:CONST_120], "reason": "Large loop iteration"})
            if stripped.startswith('def ') and 'async' not in stripped:
                if i < len(lines) - 1:
                    next_line = lines[i].strip() if i < len(lines) else ""
                    if not next_line.startswith('async') and any(kw in next_line for kw in ['open(', 'requests.', 'urllib.']):
                        issues.append({"line": i, "code": stripped[:CONST_120], "reason": "Sync function with I/O"})
    except Exception as e:
        return json.dumps({"error": str(e)})

    return json.dumps({"file": path, "issues": issues, "count": len(issues), "threshold_ms": threshold_ms})

functions = {
    "profile_function": profile_function, "benchmark_file": benchmark_file,
    "measure_time": measure_time, "memory_usage": memory_usage, "cpu_info": cpu_info,
    "disk_speed": disk_speed, "network_latency": network_latency, "find_slow_code": find_slow_code,
}
