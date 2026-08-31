#!/usr/bin/env python3
"""
Hermes Studio — Local AI Backend (100% offline, no API keys).

Smart Router:
  - Reasoning (вопросы, анализ, текст) → deepseek-r1:1.5b
  - Coding (код, верстка, сайты)      → qwen2.5-coder:1.5b

Endpoints:
  GET  /api/health    — health check
  GET  /api/models    — installed models status
  POST /api/chat      — chat (?stream=1 for SSE)
  POST /api/upload    — file upload
  GET  /api/events    — SSE event stream
"""
import asyncio
import json
import os
import pathlib
import re
import subprocess
import sys
import time
import uuid

import aiohttp
import aiohttp_cors
from aiohttp import web

ROOT = pathlib.Path(__file__).parent
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
PORT = CFG["server"]["port"]
URL = f"http://127.0.0.1:{PORT}"
OLLAMA_HOST = CFG["ollama"]["host"]
OLLAMA_DIR = ROOT / ".ollama"
OLLAMA_EXE = OLLAMA_DIR / "ollama.exe"
OLLAMA_MODELS = str(OLLAMA_DIR / "models")
MODEL_REASONING = CFG["models"]["reasoning"]
MODEL_CODING = CFG["models"]["coding"]
UPLOAD_DIR = ROOT / CFG["paths"]["uploads"]
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
FRONTEND_DIR = ROOT / "frontend"


# ════════════════════════════════════════════════════
# 1. Ollama Client
# ════════════════════════════════════════════════════

class Ollama:
    def __init__(self, host=OLLAMA_HOST):
        self.host = host
        self._available = None

    async def _get(self, path, timeout_s=5):
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{self.host}{path}", timeout=aiohttp.ClientTimeout(total=timeout_s)) as r:
                return r.status, await r.json()

    async def _post(self, path, payload, timeout_s=120):
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{self.host}{path}", json=payload,
                timeout=aiohttp.ClientTimeout(total=timeout_s),
            ) as r:
                return r.status, await r.json()

    async def _post_stream(self, path, payload, timeout_s=120):
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{self.host}{path}", json=payload,
                timeout=aiohttp.ClientTimeout(total=timeout_s),
            ) as r:
                async for raw in r.content:
                    line = raw.decode().strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue

    async def is_available(self):
        if self._available is not None:
            return self._available
        try:
            status, _ = await self._get("/api/tags", timeout_s=3)
            self._available = status == 200
        except Exception:
            self._available = False
        return self._available

    async def list_models(self):
        try:
            _, data = await self._get("/api/tags", timeout_s=5)
            return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    def model_installed(self, model_name, installed_list):
        """Check if model is installed (handles tag variations like :latest)."""
        for m in installed_list:
            if m == model_name or m.startswith(model_name.split(":")[0]):
                return True
        return False

    async def generate(self, prompt, model, system="", images=None):
        payload = {"model": model, "prompt": prompt, "stream": False}
        if system:
            payload["system"] = system
        if images:
            payload["images"] = images
        try:
            _, data = await self._post("/api/generate", payload, timeout_s=120)
            return data.get("response", "")
        except Exception as e:
            print(f"[Ollama] generate({model}) error: {e}")
            return None

    async def stream(self, prompt, model, system="", images=None):
        payload = {"model": model, "prompt": prompt, "stream": True}
        if system:
            payload["system"] = system
        if images:
            payload["images"] = images
        try:
            async for chunk in self._post_stream("/api/generate", payload, timeout_s=120):
                text = chunk.get("response", "")
                if text:
                    yield text
                if chunk.get("done"):
                    return
        except Exception as e:
            yield f"\n\n[Ollama error: {e}]"


ollama = Ollama()


# ════════════════════════════════════════════════════
# 2. Smart Router — decides which model handles the request
# ════════════════════════════════════════════════════

# Keywords that indicate a coding request
CODE_KEYWORDS = re.compile(
    r"(?:"
    r"код|кодируй|напиши код|программ|скрипт|функци"
    r"|html|css|javascript|typescript|react|vue|angular|svelte"
    r"|python|java|c\+\+|rust|go|sql"
    r"|сайт|лендинг|интерфейс|страниц|верстк|фронтенд|бэкенд"
    r"|компонент|массив|объект|класс|метод|api|endpoint"
    r"|debug|ошибк|баг|fix|исправ"
    r"|deploy|билд|сборк|настроен"
    r"|бот|скрипт|автоматиз"
    r")",
    re.IGNORECASE,
)

SITE_KEYWORDS = re.compile(
    r"(?:сайт|лендинг|магазин|портфолио|страниц|интерфейс|web-?app|приложение)",
    re.IGNORECASE,
)


def route_request(prompt):
    """Returns model name to use for this prompt."""
    if CODE_KEYWORDS.search(prompt):
        return MODEL_CODING, "coding"
    return MODEL_REASONING, "reasoning"


# System prompts per model type
SYSTEM_REASONING = (
    "Ты — Hermes Studio, локальный ИИ-ассистент. "
    "Отвечай подробно, структурно, на русском языке. "
    "Будь полезным, умным и точным."
)

SYSTEM_CODING = (
    "Ты — Hermes Studio, локальный ИИ-ассистент для кода. "
    "Пиши чистый, рабочий, готовый к запуску код. "
    "Отвечай на русском. "
    "Код обёртывай в ```html, ```python, ```typescript и т.д. "
    "Всегда объясняй что делаешь."
)


# ════════════════════════════════════════════════════
# 3. Event Bus (SSE)
# ════════════════════════════════════════════════════

class EventBus:
    def __init__(self):
        self.subscribers = []

    def subscribe(self):
        q = asyncio.Queue()
        self.subscribers.append(q)
        return q

    def unsubscribe(self, q):
        if q in self.subscribers:
            self.subscribers.remove(q)

    def emit(self, event, payload=None):
        msg = json.dumps({"event": event, "payload": payload or {}, "ts": time.time()}, ensure_ascii=False)
        for q in self.subscribers:
            try:
                q.put_nowait(msg)
            except Exception:
                pass

    async def stream(self, q):
        try:
            while True:
                msg = await q.get()
                yield f"data: {msg}\n\n"
        except asyncio.CancelledError:
            pass


bus = EventBus()


# ════════════════════════════════════════════════════
# 4. Ollama Auto-Start
# ════════════════════════════════════════════════════

async def ensure_ollama():
    """Try to start Ollama if not running. Returns True if available."""
    if await ollama.is_available():
        return True

    if not CFG["ollama"].get("auto_start", True):
        return False

    print("[Hermes] Ollama not running, attempting to start...")
    if not OLLAMA_EXE.exists():
        print(f"[Hermes] Ollama not found at {OLLAMA_EXE}")
        return False

    try:
        os.environ["OLLAMA_HOST"] = "127.0.0.1:11434"
        os.environ["OLLAMA_MODELS"] = OLLAMA_MODELS
        subprocess.Popen(
            [str(OLLAMA_EXE), "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as e:
        print(f"[Hermes] Failed to start Ollama: {e}")
        return False

    # Wait up to 10 seconds
    for _ in range(20):
        await asyncio.sleep(0.5)
        if await ollama.is_available():
            print("[Hermes] Ollama started successfully.")
            return True

    print("[Hermes] Ollama did not start in time.")
    return False


# ════════════════════════════════════════════════════
# 5. Handlers
# ════════════════════════════════════════════════════

async def index_handler(request):
    html_path = FRONTEND_DIR / "index.html"
    if html_path.exists():
        return web.FileResponse(html_path)
    return web.Response(text="Frontend not found", status=404)

async def health_handler(request):
    ollama_ok = await ollama.is_available()
    return web.json_response({
        "status": "ok",
        "port": PORT,
        "ollama": {"available": ollama_ok},
    })


async def models_handler(request):
    ollama_ok = await ollama.is_available()
    models = await ollama.list_models() if ollama_ok else []
    return web.json_response({
        "ollama": {
            "available": ollama_ok,
            "models": models,
        },
        "reasoning": {
            "model": MODEL_REASONING,
            "installed": ollama.model_installed(MODEL_REASONING, models),
        },
        "coding": {
            "model": MODEL_CODING,
            "installed": ollama.model_installed(MODEL_CODING, models),
        },
    })


async def chat_handler(request):
    body = await request.json()
    prompt = (body.get("prompt") or "").strip()
    history = body.get("history", [])
    images = body.get("images")
    use_stream = request.query.get("stream") == "1"

    if not prompt and not images:
        return web.json_response({"error": "empty prompt"}, status=400)

    # Route to the right model
    model, route_type = route_request(prompt)
    system = SYSTEM_CODING if route_type == "coding" else SYSTEM_REASONING

    # Add recent history context
    if history:
        recent = history[-6:]
        lines = []
        for m in recent:
            role = "User" if m.get("role") == "user" else "Assistant"
            lines.append(f"{role}: {m.get('content', '')}")
        system += "\n\nRecent context:\n" + "\n".join(lines)

    bus.emit("chat.request", {"prompt": prompt[:200], "model": model, "route": route_type})

    # Check Ollama
    if not await ensure_ollama():
        msg = (
            "Ollama не запущена.\n\n"
            "1. Установи: https://ollama.com\n"
            "2. Запусти:  ollama serve\n"
            "3. Скачай модели:  python setup_models.py\n\n"
            "Или запусти Hermes — он попробует стартовать автоматически."
        )
        if use_stream:
            return await _stream_text(request, msg)
        return web.json_response({"text": msg, "model": "unavailable"})

    # Check model installed
    installed = await ollama.list_models()
    if not ollama.model_installed(model, installed):
        missing = MODEL_REASONING if route_type == "coding" else MODEL_CODING
        msg = (
            f"Модель {model} не скачана.\n\n"
            f"Запусти:  python setup_models.py\n"
            f"Или вручную:  ollama pull {model}"
        )
        if use_stream:
            return await _stream_text(request, msg)
        return web.json_response({"text": msg, "model": "missing"})

    # ── Streaming ──
    if use_stream:
        bus.emit("chat.stream_start", {"model": model, "route": route_type})
        resp = web.StreamResponse(
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
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

    # ── Non-streaming ──
    bus.emit("chat.generate", {"model": model, "route": route_type})
    text = await ollama.generate(prompt, model=model, system=system, images=images)
    if text:
        bus.emit("chat.done", {"model": model, "route": route_type})
        return web.json_response({"text": text, "model": model, "route": route_type})

    return web.json_response({"text": "Не удалось получить ответ. Попробуй ещё раз.", "model": "error"})


async def _stream_text(request, text):
    """Helper: return a short text as SSE stream."""
    resp = web.StreamResponse(
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
    await resp.prepare(request)
    chunk = json.dumps({"text": text, "done": False}, ensure_ascii=False)
    await resp.write(f"data: {chunk}\n\n".encode())
    done = json.dumps({"text": "", "done": True}, ensure_ascii=False)
    await resp.write(f"data: {done}\n\n".encode())
    return resp


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
                return web.json_response(
                    {"error": f"File too large (max {CFG['limits']['max_upload_mb']}MB)"},
                    status=413,
                )
            f.write(chunk)

    bus.emit("upload.done", {"filename": filename, "size": size})
    return web.json_response({"path": str(dest).replace("\\", "/"), "size": size, "filename": filename})


async def events_handler(request):
    q = bus.subscribe()
    resp = web.StreamResponse(
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
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


# ════════════════════════════════════════════════════
# 6. App Setup
# ════════════════════════════════════════════════════

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

routes = [
    web.get("/", index_handler),
    web.get("/api/health", health_handler),
    web.get("/api/models", models_handler),
    web.post("/api/chat", chat_handler),
    web.post("/api/upload", upload_handler),
    web.get("/api/events", events_handler),
]
for route in routes:
    cors.add(app.router.add_route(route.method, route.path, route.handler))

if UPLOAD_DIR.exists():
    app.router.add_static("/uploads", str(UPLOAD_DIR), show_index=False)


async def on_startup(app):
    bus.emit("system.started", {"time": time.time()})

    ollama_ok = await ensure_ollama()
    models = await ollama.list_models() if ollama_ok else []
    reasoning_ok = ollama.model_installed(MODEL_REASONING, models)
    coding_ok = ollama.model_installed(MODEL_CODING, models)

    bus.emit("models.status", {
        "ollama": ollama_ok,
        "reasoning": reasoning_ok,
        "coding": coding_ok,
    })

    print()
    print(f"  Hermes Studio — http://127.0.0.1:{PORT}")
    print(f"  Ollama:      {'ON' if ollama_ok else 'OFF'}")
    print(f"  Reasoning:   {MODEL_REASONING} {'ready' if reasoning_ok else 'NOT INSTALLED'}")
    print(f"  Coding:      {MODEL_CODING} {'ready' if coding_ok else 'NOT INSTALLED'}")

    if not reasoning_ok or not coding_ok:
        print()
        print("  Run:  python setup_models.py")
    print()


app.on_startup.append(on_startup)


# ════════════════════════════════════════════════════
# 7. Main
# ════════════════════════════════════════════════════

if __name__ == "__main__":
    web.run_app(app, host="127.0.0.1", port=PORT)
