"""Event bus for SSE streaming and inter-module communication."""
import asyncio
import json
import time


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
        for q in self.subscribers[:]:
            try:
                q.put_nowait(msg)
            except Exception:
                self.subscribers.remove(q)

    async def stream(self, q):
        try:
            while True:
                msg = await q.get()
                yield f"data: {msg}\n\n"
        except asyncio.CancelledError:
            pass


bus = EventBus()
