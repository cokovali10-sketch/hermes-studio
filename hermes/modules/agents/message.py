"""Inter-agent messaging and message bus."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum


class MessageType(str, Enum):
    TASK = "task"
    RESULT = "result"
    ERROR = "error"
    STATUS = "status"
    HEARTBEAT = "heartbeat"


@dataclass
class AgentMessage:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    from_agent: str = ""
    to_agent: str = ""
    content: str = ""
    type: MessageType = MessageType.TASK
    timestamp: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)


class MessageBus:
    def __init__(self):
        self._messages: dict[str, list[AgentMessage]] = {}
        self._subscribers: dict[str, list] = {}

    def send(self, from_agent: str, to_agent: str, content: str,
             msg_type: MessageType = MessageType.TASK, metadata: dict | None = None) -> AgentMessage:
        msg = AgentMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            content=content,
            type=msg_type,
            metadata=metadata or {},
        )
        self._messages.setdefault(to_agent, []).append(msg)
        self._messages.setdefault(f"_log", []).append(msg)
        for callback in self._subscribers.get(to_agent, []):
            try:
                callback(msg)
            except Exception:
                pass
        return msg

    def broadcast(self, from_agent: str, content: str,
                  msg_type: MessageType = MessageType.TASK, metadata: dict | None = None) -> list[AgentMessage]:
        sent = []
        for agent_id in list(self._messages.keys()):
            if agent_id.startswith("_"):
                continue
            if agent_id == from_agent:
                continue
            msg = self.send(from_agent, agent_id, content, msg_type, metadata)
            sent.append(msg)
        return sent

    def get_messages(self, agent_id: str, clear: bool = False) -> list[AgentMessage]:
        msgs = list(self._messages.get(agent_id, []))
        if clear:
            self._messages[agent_id] = []
        return msgs

    def get_log(self) -> list[AgentMessage]:
        return list(self._messages.get("_log", []))

    def subscribe(self, agent_id: str, callback):
        self._subscribers.setdefault(agent_id, []).append(callback)

    def clear(self):
        self._messages.clear()
        self._subscribers.clear()


agent_bus = MessageBus()
