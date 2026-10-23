"""Agent-to-Agent tools — spawn, message, status, list, stop agents."""
from __future__ import annotations


from hermes.modules.agents.base import BaseAgent, AgentStatus
from hermes.modules.agents.explorer import ExplorerAgent
from hermes.modules.agents.coder import CoderAgent
from hermes.modules.agents.tester import TesterAgent
from hermes.modules.agents.reviewer import ReviewerAgent
from hermes.modules.agents.coordinator import CoordinatorAgent
from hermes.modules.agents.message import MessageType

_agent_registry: dict[str, BaseAgent] = {}

_ROLE_MAP = {
    "explorer": ExplorerAgent,
    "coder": CoderAgent,
    "tester": TesterAgent,
    "reviewer": ReviewerAgent,
    "coordinator": CoordinatorAgent,
}


async def tool_spawn_agent(role: str, task: str = "", model: str = "") -> dict:
    cls = _ROLE_MAP.get(role)
    if not cls:
        return {"success": False, "error": f"Unknown role: {role}. Available: {list(_ROLE_MAP.keys())}"}
    agent = cls(task=task, model=model)
    _agent_registry[agent.id] = agent
    return {"success": True, "agent_id": agent.id, "role": role, "status": agent.status.value}


async def tool_send_agent_message(agent_id: str, content: str, msg_type: str = "task") -> dict:
    agent = _agent_registry.get(agent_id)
    if not agent:
        return {"success": False, "error": f"Agent not found: {agent_id}"}
    try:
        mt = MessageType(msg_type)
    except ValueError:
        mt = MessageType.TASK
    msg = agent.bus.send("tool", agent_id, content, mt)
    return {"success": True, "message_id": msg.id, "to": agent_id}


async def tool_get_agent_status(agent_id: str) -> dict:
    agent = _agent_registry.get(agent_id)
    if not agent:
        return {"success": False, "error": f"Agent not found: {agent_id}"}
    return {"success": True, **agent.to_dict()}


async def tool_list_agents() -> dict:
    agents = [a.to_dict() for a in _agent_registry.values()]
    return {"success": True, "agents": agents, "count": len(agents)}


async def tool_stop_agent(agent_id: str) -> dict:
    agent = _agent_registry.get(agent_id)
    if not agent:
        return {"success": False, "error": f"Agent not found: {agent_id}"}
    if agent.status == AgentStatus.WORKING:
        agent._set_status(AgentStatus.FAILED)
        agent.error = "Stopped by user"
    return {"success": True, "agent_id": agent_id, "status": agent.status.value}


AGENTS_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "spawn_agent",
            "description": "Create a new specialized agent. Roles: explorer, coder, tester, reviewer, coordinator.",
            "parameters": {
                "type": "object",
                "properties": {
                    "role": {"type": "string", "enum": ["explorer", "coder", "tester", "reviewer", "coordinator"], "description": "Agent role"},
                    "task": {"type": "string", "description": "Task description for the agent"},
                    "model": {"type": "string", "description": "Model to use (optional)"},
                },
                "required": ["role"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_agent_message",
            "description": "Send a message to an active agent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string", "description": "Target agent ID"},
                    "content": {"type": "string", "description": "Message content"},
                    "msg_type": {"type": "string", "enum": ["task", "result", "error", "status"], "default": "task"},
                },
                "required": ["agent_id", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_agent_status",
            "description": "Get the current status of an agent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string", "description": "Agent ID"},
                },
                "required": ["agent_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_agents",
            "description": "List all active agents with their status.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stop_agent",
            "description": "Stop a running agent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string", "description": "Agent ID to stop"},
                },
                "required": ["agent_id"],
            },
        },
    },
]

AGENTS_TOOL_MAP = {
    "spawn_agent": tool_spawn_agent,
    "send_agent_message": tool_send_agent_message,
    "get_agent_status": tool_get_agent_status,
    "list_agents": tool_list_agents,
    "stop_agent": tool_stop_agent,
}
