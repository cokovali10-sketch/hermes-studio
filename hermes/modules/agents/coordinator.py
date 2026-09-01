"""Coordinator agent — orchestrates other agents."""
from __future__ import annotations

import asyncio
import time

from hermes.bus import bus
from hermes.modules.agents.base import BaseAgent, AgentStatus
from hermes.modules.agents.explorer import ExplorerAgent
from hermes.modules.agents.coder import CoderAgent
from hermes.modules.agents.tester import TesterAgent
from hermes.modules.agents.reviewer import ReviewerAgent
from hermes.modules.agents.message import MessageType


class CoordinatorAgent(BaseAgent):
    def __init__(self, task: str = "", model: str = "", **kwargs):
        super().__init__(role="coordinator", task=task, model=model, **kwargs)
        self.agents: dict[str, BaseAgent] = {}
        self.plan_results: list[dict] = []
        self.max_retries = 2

    async def run(self) -> dict:
        plan = await self.create_plan()
        return await self.execute_plan(plan)

    async def create_plan(self) -> dict:
        return {
            "phases": [
                {"name": "explore", "agent_class": ExplorerAgent, "description": "Analyze project structure"},
                {"name": "code", "agent_class": CoderAgent, "description": "Write/modify code"},
                {"name": "test", "agent_class": TesterAgent, "description": "Run tests"},
                {"name": "review", "agent_class": ReviewerAgent, "description": "Review code quality"},
            ],
            "task": self.task,
        }

    async def execute_plan(self, plan: dict) -> dict:
        results = {}
        context = {}

        for phase in plan.get("phases", []):
            agent_class = phase["agent_class"]
            phase_name = phase["name"]
            retries = 0

            while retries <= self.max_retries:
                agent = agent_class(
                    task=self.task,
                    model=self.model,
                    msg_bus=self.bus,
                )
                self.agents[agent.id] = agent
                bus.emit("coordinator.phase.started", {"phase": phase_name, "agent_id": agent.id})

                agent_result = await agent.execute()
                results[phase_name] = agent_result

                if agent_result.get("success"):
                    context[phase_name] = agent_result.get("result", {})
                    bus.emit("coordinator.phase.completed", {"phase": phase_name})
                    break
                else:
                    retries += 1
                    if retries <= self.max_retries:
                        bus.emit("coordinator.phase.retry", {
                            "phase": phase_name, "attempt": retries,
                            "error": agent_result.get("error", ""),
                        })
                    else:
                        bus.emit("coordinator.phase.failed", {"phase": phase_name})
                        return {
                            "success": False,
                            "failed_phase": phase_name,
                            "error": agent_result.get("error", "Max retries exceeded"),
                            "results": results,
                        }

        self.plan_results.append(results)
        return {"success": True, "results": results, "context": context}

    def get_agent(self, agent_id: str) -> BaseAgent | None:
        return self.agents.get(agent_id)

    def get_all_agents(self) -> list[dict]:
        return [a.to_dict() for a in self.agents.values()]

    def get_status_summary(self) -> dict:
        statuses = {}
        for a in self.agents.values():
            s = a.status.value
            statuses[s] = statuses.get(s, 0) + 1
        return {
            "total_agents": len(self.agents),
            "statuses": statuses,
            "plans_completed": len(self.plan_results),
        }

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["agent_count"] = len(self.agents)
        d["plan_count"] = len(self.plan_results)
        return d
