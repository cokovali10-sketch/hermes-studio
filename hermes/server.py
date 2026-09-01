"""Hermes HTTP server — all endpoints and app setup."""
import asyncio
import json
import os
import subprocess
import time
import uuid
from base64 import b64decode

import aiohttp
import aiohttp_cors
from aiohttp import web

from hermes.core import (
    ROOT, CFG, PORT, OLLAMA_HOST, OLLAMA_DIR, OLLAMA_EXE, OLLAMA_MODELS,
    MODEL_REASONING, MODEL_CODING, MODEL_AGENT, MODEL_VISION,
    UPLOAD_DIR, WORKSPACE_DIR, BACKUP_DIR, FRONTEND_DIR, PLUGINS_DIR,
    MAX_TOOL_STEPS, SHELL_TIMEOUT, MAX_PROMPT_CHARS, AGENT_SYSTEM, MAX_ITERATIONS,
)
from hermes.bus import bus
from hermes.ollama import ollama
from hermes.tools import TOOLS_SCHEMA, TOOL_MAP, call_tool
from hermes.router import route_request, SYSTEM_CODING, SYSTEM_VISION, SYSTEM_REASONING
from hermes.agent import AgentLoop
from hermes.safety import safety_check, SafetyViolation
from hermes.tools import _build_tree

try:
    from PIL import ImageGrab
    PILLOW_OK = True
except ImportError:
    PILLOW_OK = False

START_TIME = time.time()

_tool_call_count = 0
_tool_calls_by_name = {}
_tool_call_times = []


async def ensure_ollama():
    if await ollama.is_available():
        return True
    if not CFG["ollama"].get("auto_start", True):
        return False

    print("[Hermes] Ollama not running, starting...")
    if not OLLAMA_EXE.exists():
        print(f"[Hermes] Ollama not found at {OLLAMA_EXE}")
        return False

    try:
        os.environ["OLLAMA_HOST"] = "127.0.0.1:11434"
        os.environ["OLLAMA_MODELS"] = OLLAMA_MODELS
        subprocess.Popen(
            [str(OLLAMA_EXE), "serve"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as e:
        print(f"[Hermes] Failed to start Ollama: {e}")
        return False

    for _ in range(20):
        await asyncio.sleep(0.5)
        if await ollama.is_available():
            print("[Hermes] Ollama started.")
            return True

    print("[Hermes] Ollama did not start in time.")
    return False


async def _stream_text(request, text):
    resp = web.StreamResponse(
        headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
    await resp.prepare(request)
    await resp.write(f"data: {json.dumps({'text': text, 'done': False}, ensure_ascii=False)}\n\n".encode())
    await resp.write(f"data: {json.dumps({'text': '', 'done': True}, ensure_ascii=False)}\n\n".encode())
    return resp


async def index_handler(request):
    html_path = FRONTEND_DIR / "index.html"
    if html_path.exists():
        return web.FileResponse(html_path)
    return web.Response(text="Frontend not found", status=404)


async def health_handler(request):
    ollama_ok = await ollama.is_available()
    return web.json_response({
        "status": "ok",
        "version": "5.0.0",
        "port": PORT,
        "ollama": {"available": ollama_ok},
        "workspace": str(WORKSPACE_DIR),
        "pillow": PILLOW_OK,
    })


async def models_handler(request):
    ollama_ok = await ollama.is_available()
    models = await ollama.list_models() if ollama_ok else []
    return web.json_response({
        "ollama": {"available": ollama_ok, "models": models},
        "reasoning": {"model": MODEL_REASONING, "installed": ollama.model_installed(MODEL_REASONING, models)},
        "coding": {"model": MODEL_CODING, "installed": ollama.model_installed(MODEL_CODING, models)},
        "agent": {"model": MODEL_AGENT, "installed": ollama.model_installed(MODEL_AGENT, models)},
        "vision": {"model": MODEL_VISION, "installed": ollama.model_installed(MODEL_VISION, models)},
    })


async def tools_handler(request):
    return web.json_response({"tools": TOOLS_SCHEMA})


async def workspace_handler(request):
    tree = _build_tree(WORKSPACE_DIR, max_depth=5)
    return web.json_response({"workspace": str(WORKSPACE_DIR), "tree": tree})


async def chat_handler(request):
    body = await request.json()
    prompt = (body.get("prompt") or "").strip()
    history = body.get("history", [])
    images = body.get("images")
    use_stream = request.query.get("stream") == "1"

    if not prompt and not images:
        return web.json_response({"error": "empty prompt"}, status=400)

    model, route_type = route_request(prompt)
    system = SYSTEM_CODING if route_type == "coding" else SYSTEM_VISION if route_type == "vision" else SYSTEM_REASONING

    if history:
        recent = history[-6:]
        lines = []
        for m in recent:
            role = "User" if m.get("role") == "user" else "Assistant"
            lines.append(f"{role}: {m.get('content', '')}")
        system += "\n\nRecent context:\n" + "\n".join(lines)

    bus.emit("chat.request", {"prompt": prompt[:200], "model": model, "route": route_type})

    if not await ensure_ollama():
        msg = "Ollama not running. Install: https://ollama.com | Then: ollama serve"
        if use_stream:
            return await _stream_text(request, msg)
        return web.json_response({"text": msg, "model": "unavailable"})

    installed = await ollama.list_models()
    if not ollama.model_installed(model, installed):
        fallback = MODEL_CODING if ollama.model_installed(MODEL_CODING, installed) else MODEL_REASONING
        if not ollama.model_installed(fallback, installed):
            msg = f"Model {model} not installed. Run: python setup_models.py"
            if use_stream:
                return await _stream_text(request, msg)
            return web.json_response({"text": msg, "model": "missing"})
        model = fallback

    if use_stream:
        bus.emit("chat.stream_start", {"model": model, "route": route_type})
        resp = web.StreamResponse(
            headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )
        await resp.prepare(request)

        async def send_sse(data):
            await resp.write(f"data: {json.dumps(data, ensure_ascii=False)}\n\n".encode())

        try:
            async for text in ollama.stream(prompt, model=model, system=system, images=images):
                await send_sse({"text": text, "done": False, "model": model, "route": route_type})
            await send_sse({"text": "", "done": True, "model": model, "route": route_type})
            bus.emit("chat.done", {"model": model, "route": route_type})
        except Exception as e:
            await send_sse({"text": f"\n\n[Error: {e}]", "done": True})
        return resp

    bus.emit("chat.generate", {"model": model, "route": route_type})
    text = await ollama.generate(prompt, model=model, system=system, images=images)
    if text:
        bus.emit("chat.done", {"model": model, "route": route_type})
        return web.json_response({"text": text, "model": model, "route": route_type})

    return web.json_response({"text": "Failed to get response. Try again.", "model": "error"})


async def agent_handler(request):
    body = await request.json()
    task = (body.get("task") or "").strip()
    model = body.get("model")

    if not task:
        return web.json_response({"error": "empty task"}, status=400)

    if not await ensure_ollama():
        return web.json_response({"error": "Ollama not running"}, status=503)

    installed = await ollama.list_models()
    use_model = model or MODEL_AGENT
    if not ollama.model_installed(use_model, installed):
        use_model = MODEL_CODING if ollama.model_installed(MODEL_CODING, installed) else MODEL_REASONING
        if not ollama.model_installed(use_model, installed):
            return web.json_response({"error": "No suitable model installed"}, status=503)

    agent = AgentLoop(task=task, model=use_model)

    resp = web.StreamResponse(
        headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
    await resp.prepare(request)

    async def send_sse(data):
        await resp.write(f"data: {json.dumps(data, ensure_ascii=False)}\n\n".encode())

    async def on_step(step):
        await send_sse({
            "type": "step",
            "step": step["step"],
            "tool": step["tool"],
            "args": step["args"],
            "result_summary": json.dumps(step["result"], ensure_ascii=False)[:300],
        })

    try:
        result = await agent.run(on_step=on_step)
        await send_sse({"type": "done", "result": result})
    except Exception as e:
        await send_sse({"type": "error", "error": str(e)})

    return resp


async def analyze_image_handler(request):
    body = await request.json()
    image_b64 = body.get("image")
    prompt = body.get("prompt", "Describe this image in detail.")
    save_path = body.get("save_path")

    if not image_b64:
        return web.json_response({"error": "No image provided"}, status=400)

    if save_path:
        save_target = WORKSPACE_DIR / save_path
        save_target.parent.mkdir(parents=True, exist_ok=True)
        save_target.write_bytes(b64decode(image_b64))

    result = await ollama.vision_analyze(prompt, image_b64)
    if result:
        return web.json_response({"description": result, "model": MODEL_VISION})

    return web.json_response({"error": "Vision analysis failed"}, status=500)


async def upload_handler(request):
    reader = await request.multipart()
    field = await reader.next()
    if not field or field.name != "file":
        return web.json_response({"error": "no file field"}, status=400)

    filename = field.filename or "upload.bin"
    filename = "".join(c for c in filename if c.isalnum() or c in "._- ")[:60].strip()
    if not filename:
        filename = "upload.bin"

    dest = UPLOAD_DIR / f"{uuid.uuid4().hex[:8]}_{filename}"
    max_bytes = CFG["limits"]["max_upload_mb"] * 1024 * 1024
    size = 0

    with open(dest, "wb") as f:
        while True:
            chunk = await field.read_chunk(8192)
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                return web.json_response({"error": f"Too large (max {CFG['limits']['max_upload_mb']}MB)"}, status=413)
            f.write(chunk)

    bus.emit("upload.done", {"filename": filename, "size": size})
    return web.json_response({"path": str(dest).replace("\\", "/"), "size": size, "filename": filename})


async def events_handler(request):
    q = bus.subscribe()
    resp = web.StreamResponse(
        headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}
    )
    await resp.prepare(request)
    try:
        async for chunk in bus.stream(q):
            await resp.write(chunk.encode())
    except asyncio.CancelledError:
        pass
    finally:
        bus.unsubscribe(q)
    return resp


async def stats_handler(request):
    ollama_ok = await ollama.is_available()
    models_list = await ollama.list_models() if ollama_ok else []

    stats = {
        "server": {
            "version": "5.0.0",
            "port": PORT,
            "uptime": time.time() - START_TIME,
        },
        "tools": {
            "total": len(TOOL_MAP),
            "available": list(TOOL_MAP.keys()),
            "total_calls": _tool_call_count,
            "calls_by_name": _tool_calls_by_name,
        },
        "models": {
            "ollama": ollama_ok,
            "reasoning": {"model": MODEL_REASONING, "installed": ollama.model_installed(MODEL_REASONING, models_list)},
            "coding": {"model": MODEL_CODING, "installed": ollama.model_installed(MODEL_CODING, models_list)},
            "agent": {"model": MODEL_AGENT, "installed": ollama.model_installed(MODEL_AGENT, models_list)},
            "vision": {"model": MODEL_VISION, "installed": ollama.model_installed(MODEL_VISION, models_list)},
        },
        "workspace": str(WORKSPACE_DIR),
        "pillow": PILLOW_OK,
    }
    return web.json_response(stats)


async def stats_dashboard_handler(request):
    html_path = FRONTEND_DIR / "stats.html"
    if html_path.exists():
        return web.FileResponse(html_path)
    return web.Response(text="Stats dashboard not found", status=404)


async def on_startup(app):
    bus.emit("system.started", {"time": time.time(), "version": "5.0.0"})

    ollama_ok = await ensure_ollama()
    models = await ollama.list_models() if ollama_ok else []
    reasoning_ok = ollama.model_installed(MODEL_REASONING, models)
    coding_ok = ollama.model_installed(MODEL_CODING, models)
    agent_ok = ollama.model_installed(MODEL_AGENT, models)
    vision_ok = ollama.model_installed(MODEL_VISION, models)

    bus.emit("models.status", {
        "ollama": ollama_ok, "reasoning": reasoning_ok,
        "coding": coding_ok, "agent": agent_ok, "vision": vision_ok,
    })

    print()
    print(f"  Hermes Studio v5.0.0 — Agentic Tool Suite")
    print(f"  http://127.0.0.1:{PORT}")
    print(f"  Ollama:      {'ON' if ollama_ok else 'OFF'}")
    print(f"  Reasoning:   {MODEL_REASONING} {'ready' if reasoning_ok else 'NOT INSTALLED'}")
    print(f"  Coding:      {MODEL_CODING} {'ready' if coding_ok else 'NOT INSTALLED'}")
    print(f"  Agent:       {MODEL_AGENT} {'ready' if agent_ok else 'NOT INSTALLED'}")
    print(f"  Vision:      {MODEL_VISION} {'ready' if vision_ok else 'NOT INSTALLED'}")
    print(f"  Pillow:      {'YES' if PILLOW_OK else 'NO (pip install Pillow)'}")
    print(f"  Workspace:   {WORKSPACE_DIR}")
    print(f"  Safety:      ACTIVE (30+ rules)")
    print(f"  Plugins:     {PLUGINS_DIR}")

    from hermes.plugins import _load_plugins
    _load_plugins()
    print(f"  Tools:       {len(TOOLS_SCHEMA)} available")
    if not reasoning_ok or not coding_ok:
        print()
        print("  Run:  python setup_models.py")
    print()


async def on_cleanup(app):
    bus.emit("system.shutdown", {"time": time.time()})
    print("[Hermes] Server shutting down...")


def create_app():
    app = web.Application()

    cors = aiohttp_cors.setup(
        app,
        defaults={
            "*": aiohttp_cors.ResourceOptions(
                allow_credentials=True,
                expose_headers="*",
                allow_headers="*",
                allow_methods="*",
            )
        },
    )

    from hermes.plugins import plugins_handler, reload_plugins_handler

    routes = [
        web.get("/", index_handler),
        web.get("/stats", stats_dashboard_handler),
        web.get("/api/health", health_handler),
        web.get("/api/models", models_handler),
        web.get("/api/tools", tools_handler),
        web.get("/api/stats", stats_handler),
        web.get("/api/workspace", workspace_handler),
        web.get("/api/plugins", plugins_handler),
        web.post("/api/plugins/reload", reload_plugins_handler),
        web.post("/api/chat", chat_handler),
        web.post("/api/agent", agent_handler),
        web.post("/api/analyze_image", analyze_image_handler),
        web.post("/api/upload", upload_handler),
        web.get("/api/events", events_handler),
    ]
    for route in routes:
        cors.add(app.router.add_route(route.method, route.path, route.handler))

    if UPLOAD_DIR.exists():
        app.router.add_static("/uploads", str(UPLOAD_DIR), show_index=False)

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    return app


app = create_app()

if __name__ == "__main__":
    web.run_app(app, host="127.0.0.1", port=PORT)
