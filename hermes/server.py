"""Hermes HTTP server — all endpoints and app setup."""
import asyncio
import json
import os
import subprocess
import time
import uuid
from base64 import b64decode

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
from hermes.tools import TOOLS_SCHEMA, TOOL_MAP
from hermes.router import route_request, SYSTEM_CODING, SYSTEM_VISION, SYSTEM_REASONING
from hermes.agent import AgentLoop
from hermes.tools import _build_tree
# --- константы вынесены FORGE refactor ---
CONST_8 = 8
CONST_400 = 400
CONST_404 = 404
CONST_503 = 503
CONST_1024 = 1024


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
    return web.Response(text="Frontend not found", status=CONST_404)


async def classify_handler(request):
    data = await request.json()
    prompt = data.get("prompt", "")
    from hermes.tool_router import classify_request, get_relevant_tools
    classification = classify_request(prompt)
    tools = get_relevant_tools(prompt)
    return web.json_response({"classification": classification, "tools": tools})


async def workflows_handler(request):
    from hermes.workflows import get_all_workflows
    return web.json_response({"workflows": get_all_workflows()})


async def workflow_match_handler(request):
    data = await request.json()
    prompt = data.get("prompt", "")
    from hermes.workflows import match_workflow, render_workflow_for_model
    wf = match_workflow(prompt)
    if wf:
        return web.json_response({
            "matched": True,
            "id": wf["id"],
            "name": wf["name"],
            "description": wf["description"],
            "steps": len(wf["steps"]),
            "instructions": render_workflow_for_model(wf),
        })
    return web.json_response({"matched": False})


async def plan_handler(request):
    data = await request.json()
    prompt = data.get("prompt", "")
    from hermes.planner import create_plan, render_plan_for_model
    plan = create_plan(prompt)
    return web.json_response({
        "plan": plan,
        "rendered": render_plan_for_model(plan, prompt),
    })


async def tools_filtered_handler(request):
    data = await request.json()
    prompt = data.get("prompt", "")
    from hermes.tool_router import get_tool_schemas
    schemas = get_tool_schemas(prompt, TOOLS_SCHEMA)
    return web.json_response({"tools": schemas, "count": len(schemas)})


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
        return web.json_response({"error": "empty prompt"}, status=CONST_400)

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
        return web.json_response({"error": "empty task"}, status=CONST_400)

    if not await ensure_ollama():
        return web.json_response({"error": "Ollama not running"}, status=CONST_503)

    installed = await ollama.list_models()
    use_model = model or MODEL_AGENT
    if not ollama.model_installed(use_model, installed):
        use_model = MODEL_CODING if ollama.model_installed(MODEL_CODING, installed) else MODEL_REASONING
        if not ollama.model_installed(use_model, installed):
            return web.json_response({"error": "No suitable model installed"}, status=CONST_503)

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
        return web.json_response({"error": "No image provided"}, status=CONST_400)

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
        return web.json_response({"error": "no file field"}, status=CONST_400)

    filename = field.filename or "upload.bin"
    filename = "".join(c for c in filename if c.isalnum() or c in "._- ")[:60].strip()
    if not filename:
        filename = "upload.bin"

    dest = UPLOAD_DIR / f"{uuid.uuid4().hex[:CONST_8]}_{filename}"
    max_bytes = CFG["limits"]["max_upload_mb"] * CONST_1024 * CONST_1024
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
    return web.Response(text="Stats dashboard not found", status=CONST_404)


# ─── Phase 2: Persistence Handlers ────────────────────────────────────────────

async def list_conversations_handler(request):
    from hermes.storage.conversations import list_conversations
    convs = list_conversations()
    return web.json_response({"conversations": convs})


async def create_conversation_handler(request):
    from hermes.storage.conversations import create_conversation
    data = await request.json()
    conv_id = create_conversation(
        title=data.get("title", "New Conversation"),
        model=data.get("model"),
        mode=data.get("mode", "chat"),
    )
    return web.json_response({"conversation_id": conv_id})


async def get_conversation_handler(request):
    from hermes.storage.conversations import get_conversation
    conv_id = request.match_info["id"]
    conv = get_conversation(conv_id)
    if not conv:
        return web.json_response({"error": "Not found"}, status=CONST_404)
    return web.json_response(conv)


async def delete_conversation_handler(request):
    from hermes.storage.conversations import delete_conversation
    conv_id = request.match_info["id"]
    delete_conversation(conv_id)
    return web.json_response({"success": True})


# ─── Phase 3: Memory Handlers ─────────────────────────────────────────────────

async def list_memory_projects_handler(request):
    from hermes.modules.memory import MemoryEngine
    engine = MemoryEngine()
    projects = engine.list_projects()
    return web.json_response({"projects": projects})


async def scan_memory_handler(request):
    from hermes.modules.memory import MemoryEngine
    data = await request.json()
    engine = MemoryEngine()
    result = engine.scan_project(data.get("path", str(WORKSPACE_DIR)))
    return web.json_response(result)


async def get_memory_project_handler(request):
    from hermes.modules.memory import MemoryEngine
    project_id = request.match_info["id"]
    engine = MemoryEngine()
    result = engine.get_project_context(project_id)
    return web.json_response({"context": result})


async def remember_fact_handler(request):
    from hermes.modules.memory import MemoryEngine
    project_id = request.match_info["id"]
    data = await request.json()
    engine = MemoryEngine()
    result = engine.remember_fact(project_id, data.get("type", "info"), data.get("content", ""))
    return web.json_response(result)


async def recall_facts_handler(request):
    from hermes.modules.memory import MemoryEngine
    project_id = request.match_info["id"]
    query = request.query.get("q", "")
    engine = MemoryEngine()
    facts = engine.recall_facts(project_id, query)
    return web.json_response({"facts": facts})


# ─── Phase 4: Planning Handlers ───────────────────────────────────────────────

async def list_plans_handler(request):
    from hermes.modules.planning import PlanningEngine
    engine = PlanningEngine()
    plans = engine.list_plans()
    return web.json_response({"plans": plans})


async def create_plan_handler(request):
    from hermes.modules.planning import PlanningEngine
    data = await request.json()
    engine = PlanningEngine()
    plan = engine.create_plan(data.get("task", ""), data.get("context", ""))
    return web.json_response(plan)


async def get_plan_handler(request):
    from hermes.modules.planning import PlanningEngine
    plan_id = request.match_info["id"]
    engine = PlanningEngine()
    plan = engine.get_plan_status(plan_id)
    if not plan:
        return web.json_response({"error": "Not found"}, status=CONST_404)
    return web.json_response(plan)


async def execute_plan_handler(request):
    from hermes.modules.planning import PlanningEngine
    plan_id = request.match_info["id"]
    data = await request.json()
    engine = PlanningEngine()
    result = engine.execute_plan_step(plan_id, data.get("step_id"))
    return web.json_response(result)


# ─── Phase 5: Code Intelligence Handlers ──────────────────────────────────────

async def parse_file_handler(request):
    from hermes.modules.code_intel.parser import parse_file
    data = await request.json()
    result = parse_file(data.get("path", ""))
    return web.json_response(result)


async def semantic_search_handler(request):
    from hermes.modules.code_intel.semantic import SemanticSearch
    data = await request.json()
    searcher = SemanticSearch()
    results = searcher.search(data.get("query", ""), data.get("path", str(WORKSPACE_DIR)))
    return web.json_response({"results": results})


async def dependency_graph_handler(request):
    from hermes.modules.code_intel.deps import DependencyGraph
    data = await request.json()
    graph = DependencyGraph()
    result = graph.build_graph(data.get("path", str(WORKSPACE_DIR)))
    return web.json_response(result)


async def api_discovery_handler(request):
    from hermes.modules.code_intel.api_discovery import discover_api_endpoints
    data = await request.json()
    endpoints = discover_api_endpoints(data.get("path", str(WORKSPACE_DIR)))
    return web.json_response({"endpoints": endpoints})


# ─── Phase 6: Agent-to-Agent Handlers ─────────────────────────────────────────

_agents = {}  # Active agents


async def list_agents_handler(request):
    agents_list = [{"id": aid, "status": a.get("status", "unknown")} for aid, a in _agents.items()]
    return web.json_response({"agents": agents_list})


async def spawn_agent_handler(request):
    from hermes.modules.agents.coordinator import CoordinatorAgent
    data = await request.json()
    agent_id = f"agent_{uuid.uuid4().hex[:CONST_8]}"
    agent = CoordinatorAgent(agent_id, data.get("task", ""), model=data.get("model"))
    _agents[agent_id] = {"agent": agent, "status": "idle", "task": data.get("task", "")}
    return web.json_response({"agent_id": agent_id, "status": "spawned"})


async def get_agent_handler(request):
    agent_id = request.match_info["id"]
    agent_info = _agents.get(agent_id)
    if not agent_info:
        return web.json_response({"error": "Not found"}, status=CONST_404)
    return web.json_response({"id": agent_id, "status": agent_info["status"], "task": agent_info["task"]})


async def stop_agent_handler(request):
    agent_id = request.match_info["id"]
    if agent_id in _agents:
        _agents[agent_id]["status"] = "stopped"
        return web.json_response({"success": True})
    return web.json_response({"error": "Not found"}, status=CONST_404)


# ─── Phase 7: Vision + 3D Handlers ────────────────────────────────────────────

async def vision_analyze_handler(request):
    from hermes.modules.vision.analysis import analyze_ui_screenshot
    data = await request.json()
    image_b64 = data.get("image", "")
    result = analyze_ui_screenshot(image_b64)
    return web.json_response(result)


async def generate_3d_handler(request):
    from hermes.modules.vision.threejs_gen import generate_threejs_scene
    data = await request.json()
    scene_html = generate_threejs_scene(data.get("description", ""), data.get("objects", []))
    return web.json_response({"html": scene_html})


# ─── Phase 8: Self-Improve + Orchestration Handlers ───────────────────────────

async def performance_handler(request):
    from hermes.modules.self_improve.perf_profiler import PerfProfiler
    profiler = PerfProfiler()
    return web.json_response({"scores": profiler.get_model_scores()})


async def error_patterns_handler(request):
    from hermes.modules.self_improve.error_logger import ErrorLogger
    logger = ErrorLogger()
    patterns = logger.get_error_patterns()
    return web.json_response({"patterns": patterns})


async def model_score_handler(request):
    from hermes.modules.self_improve.perf_profiler import PerfProfiler
    profiler = PerfProfiler()
    return web.json_response({"scores": profiler.get_model_scores()})


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
        # Phase 2: Persistence
        web.get("/api/conversations", list_conversations_handler),
        web.post("/api/conversations", create_conversation_handler),
        web.get("/api/conversations/{id}", get_conversation_handler),
        web.delete("/api/conversations/{id}", delete_conversation_handler),
        # Phase 3: Memory
        web.get("/api/memory/projects", list_memory_projects_handler),
        web.post("/api/memory/scan", scan_memory_handler),
        web.get("/api/memory/projects/{id}", get_memory_project_handler),
        web.post("/api/memory/projects/{id}/remember", remember_fact_handler),
        web.get("/api/memory/projects/{id}/recall", recall_facts_handler),
        # Phase 4: Planning
        web.get("/api/plans", list_plans_handler),
        web.post("/api/plans", create_plan_handler),
        web.get("/api/plans/{id}", get_plan_handler),
        web.post("/api/plans/{id}/execute", execute_plan_handler),
        # Phase 5: Code Intelligence
        web.post("/api/code-intel/parse", parse_file_handler),
        web.post("/api/code-intel/search", semantic_search_handler),
        web.post("/api/code-intel/dependencies", dependency_graph_handler),
        web.post("/api/code-intel/api-discovery", api_discovery_handler),
        # Phase 6: Agents
        web.get("/api/agents", list_agents_handler),
        web.post("/api/agents/spawn", spawn_agent_handler),
        web.get("/api/agents/{id}", get_agent_handler),
        web.post("/api/agents/{id}/stop", stop_agent_handler),
        # Phase 7: Vision + 3D
        web.post("/api/vision/analyze", vision_analyze_handler),
        web.post("/api/3d/generate", generate_3d_handler),
        # Phase 8: Self-Improve + Orchestration
        web.get("/api/performance", performance_handler),
        web.get("/api/errors/patterns", error_patterns_handler),
        web.get("/api/models/score", model_score_handler),
        # Phase 9: Smart Agent (tool routing, workflows, planning)
        web.post("/api/classify", classify_handler),
        web.get("/api/workflows", workflows_handler),
        web.post("/api/workflows/match", workflow_match_handler),
        web.post("/api/plan", plan_handler),
        web.post("/api/tools/filtered", tools_filtered_handler),
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
