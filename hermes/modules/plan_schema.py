"""Schema definitions for planning engine."""
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
import uuid


class PlanStatus(Enum):
    PLANNING = "planning"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


class StepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Step:
    id: str
    tool: str
    args: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    verify: str = ""
    status: StepStatus = StepStatus.PENDING
    result: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tool": self.tool,
            "args": self.args,
            "depends_on": self.depends_on,
            "verify": self.verify,
            "status": self.status.value,
            "result": self.result,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Step":
        return cls(
            id=data["id"],
            tool=data["tool"],
            args=data.get("args", {}),
            depends_on=data.get("depends_on", []),
            verify=data.get("verify", ""),
            status=StepStatus(data.get("status", "pending")),
            result=data.get("result", {}),
        )


@dataclass
class Phase:
    id: str
    name: str
    steps: list[Step] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "steps": [s.to_dict() for s in self.steps],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Phase":
        return cls(
            id=data["id"],
            name=data["name"],
            steps=[Step.from_dict(s) for s in data.get("steps", [])],
        )


@dataclass
class Plan:
    id: str
    task: str
    phases: list[Phase] = field(default_factory=list)
    status: PlanStatus = PlanStatus.PLANNING
    created_at: float = field(default_factory=time.time)
    completed_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "task": self.task,
            "phases": [p.to_dict() for p in self.phases],
            "status": self.status.value,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Plan":
        return cls(
            id=data["id"],
            task=data["task"],
            phases=[Phase.from_dict(p) for p in data.get("phases", [])],
            status=PlanStatus(data.get("status", "planning")),
            created_at=data.get("created_at", time.time()),
            completed_at=data.get("completed_at", 0.0),
        )

    def get_step(self, phase_id: str, step_id: str) -> Step | None:
        for phase in self.phases:
            if phase.id == phase_id:
                for step in phase.steps:
                    if step.id == step_id:
                        return step
        return None

    def get_all_steps(self) -> list[tuple[str, Step]]:
        result = []
        for phase in self.phases:
            for step in phase.steps:
                result.append((phase.id, step))
        return result

    def all_dependencies_met(self, step: Step) -> bool:
        all_steps = {s.id: s for _, s in self.get_all_steps()}
        for dep_id in step.depends_on:
            dep = all_steps.get(dep_id)
            if not dep or dep.status != StepStatus.DONE:
                return False
        return True


def create_plan_id() -> str:
    return f"plan_{uuid.uuid4().hex[:12]}"


def create_phase_id() -> str:
    return f"phase_{uuid.uuid4().hex[:8]}"


def create_step_id() -> str:
    return f"step_{uuid.uuid4().hex[:8]}"


def validate_plan(plan: Plan) -> list[str]:
    errors = []
    if not plan.task:
        errors.append("Plan must have a task description")
    if not plan.phases:
        errors.append("Plan must have at least one phase")
    step_ids = set()
    for phase in plan.phases:
        if not phase.steps:
            errors.append(f"Phase '{phase.name}' has no steps")
        for step in phase.steps:
            if step.id in step_ids:
                errors.append(f"Duplicate step ID: {step.id}")
            step_ids.add(step.id)
            for dep in step.depends_on:
                if dep not in step_ids:
                    errors.append(f"Step '{step.id}' depends on unknown step '{dep}'")
    return errors


def plan_from_dict(data: dict) -> Plan:
    return Plan.from_dict(data)
