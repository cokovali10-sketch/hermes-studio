"""Ollama client for local LLM inference."""
import json

import aiohttp

from hermes.core import OLLAMA_HOST, MODEL_VISION, MODEL_CODING, MODEL_REASONING
# --- константы вынесены FORGE refactor ---
CONST_5 = 5
CONST_120 = 120
CONST_300 = 300



class Ollama:
    def __init__(self, host=OLLAMA_HOST):
        self.host = host
        self._available = None

    async def _get(self, path, timeout_s=CONST_5):
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{self.host}{path}", timeout=aiohttp.ClientTimeout(total=timeout_s)) as r:
                return r.status, await r.json()

    async def _post(self, path, payload, timeout_s=CONST_120):
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{self.host}{path}", json=payload,
                timeout=aiohttp.ClientTimeout(total=timeout_s),
            ) as r:
                return r.status, await r.json()

    async def _post_stream(self, path, payload, timeout_s=CONST_120):
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
            _, data = await self._get("/api/tags", timeout_s=CONST_5)
            return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    def model_installed(self, model_name, installed_list):
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
            _, data = await self._post("/api/generate", payload, timeout_s=CONST_300)
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
            async for chunk in self._post_stream("/api/generate", payload, timeout_s=CONST_300):
                text = chunk.get("response", "")
                if text:
                    yield text
                if chunk.get("done"):
                    return
        except Exception as e:
            yield f"\n\n[Ollama error: {e}]"

    async def chat_stream(self, messages, model, tools=None):
        payload = {"model": model, "messages": messages, "stream": True}
        if tools:
            payload["tools"] = tools
        try:
            async for chunk in self._post_stream("/api/chat", payload, timeout_s=CONST_300):
                yield chunk
        except Exception as e:
            yield {"error": str(e)}

    async def vision_analyze(self, prompt: str, image_b64: str, model: str = None) -> str:
        use_model = model or MODEL_VISION
        installed = await self.list_models()
        if not self.model_installed(use_model, installed):
            use_model = MODEL_CODING if self.model_installed(MODEL_CODING, installed) else MODEL_REASONING
        return await self.generate(prompt, model=use_model, images=[image_b64])


ollama = Ollama()
