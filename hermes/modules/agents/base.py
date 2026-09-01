"""Base agent class for all specialized agents."""
from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from enum import Enum

from hermes.bus import bus
from hermes.modules.agents.message import AgentMessage, MessageBus, MessageType, agent_bus


class AgentStatus(str, Enum):
    IDLE = "idle"
    WORKING = "working"
    DONE = "done"
    FAILED = "failed"


class BaseAgent(ABC):
    def __init__(self, agent_id: str = "", role: str = "base",
                 task: str = "", model: str = "", msg_bus: MessageBus | None = None):
        self.id = agent_id or f"{role}_{uuid.uuid4().hex[:8]}"
        self.role = role
        self.task = task
        self.model = model
        self.status = AgentStatus.IDLE
        self.result: dict | None = None
        self.error: str | None = None
        self.created_at = time.time()
        self.completed_at: float | None = None
        self.bus = msg_bus or agent_bus
        self._inbox: list[AgentMessage] = []

    @abstractmethod
    async def run(self) -> dict:
        ...

    def send_message(self, to_agent: str, content: str,
                     msg_type: MessageType = MessageType.TASK, metadata: dict | None = None) -> AgentMessage:
        return self.bus.send(self.id, to_agent, content, msg_type, metadata)

    def receive_message(self, message: AgentMessage):
        self._inbox.append(message)

    def get_inbox(self, clear: bool = False) -> list[AgentMessage]:
        msgs = list(self._inbox)
        if clear:
            self._inbox.clear()
        return msgs

    def _set_status(self, status: AgentStatus):
        self.status = status
        bus.emit("agent.status", {"agent_id": self.id, "role": self.role, "status": status.value})

    async def execute(self) -> dict:
        self._set_status(AgentStatus.WORKING)
        bus.emit("agent.started", {"agent_id": self.id, "role": self.role, "task": self.task[:200]})
        try:
            result = await self.run()
            self.result = result
            self.completed_at = time.time()
            self._set_status(AgentStatus.DONE)
            bus.emit("agent.completed", {"agent_id": self.id, "role": self.role, "elapsed": self.elapsed()})
            return {"success": True, "agent_id": self.id, "role": self.role, "result": result}
        except Exception as e:
            self.error = str(e)
            self.completed_at = time.time()
            self._set_status(AgentStatus.FAILED)
            bus.emit("agent.failed", {"agent_id": self.id, "role": self.role, "error": str(e)})
            return {"success": False, "agent_id": self.id, "role": self.role, "error": str(e)}

    def elapsed(self) -> float:
        if self.completed_at:
            return round(self.completed_at - self.created_at, 3)
        return round(time.time() - self.created_at, 3)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "role": self.role,
            "task": self.task,
            "model": self.model,
            "status": self.status.value,
            "elapsed": self.elapsed(),
            "has_result": self.result is not None,
            "error": self.error,
        }
