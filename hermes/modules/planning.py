"""Planning engine for task decomposition and execution."""
import time
from typing import Any

from hermes.bus import bus
from hermes.modules.plan_schema import (
    Plan, Phase, Step, PlanStatus, StepStatus,
    create_plan_id, create_phase_id, create_step_id,
    validate_plan,
)


class PlanningEngine:
    def __init__(self):
        self._plans: dict[str, Plan] = {}

    def create_plan(self, task: str, context: str = "", phases: list[dict] | None = None) -> Plan:
        plan = Plan(
            id=create_plan_id(),
            task=task,
            status=PlanStatus.PLANNING,
            created_at=time.time(),
        )

        if phases:
            for phase_data in phases:
                phase = Phase(
                    id=phase_data.get("id", create_phase_id()),
                    name=phase_data.get("name", "Unnamed Phase"),
                )
                for step_data in phase_data.get("steps", []):
                    step = Step(
                        id=step_data.get("id", create_step_id()),
                        tool=step_data["tool"],
                        args=step_data.get("args", {}),
                        depends_on=step_data.get("depends_on", []),
                        verify=step_data.get("verify", ""),
                    )
                    phase.steps.append(step)
                plan.phases.append(phase)

        errors = validate_plan(plan)
        if errors:
            raise ValueError(f"Invalid plan: {'; '.join(errors)}")

        self._plans[plan.id] = plan
        bus.emit("plan.created", {"plan_id": plan.id, "task": task})
        return plan

    def get_plan(self, plan_id: str) -> Plan | None:
        return self._plans.get(plan_id)

    def get_plan_status(self, plan_id: str) -> dict[str, Any]:
        plan = self._plans.get(plan_id)
        if not plan:
            return {"error": f"Plan not found: {plan_id}"}

        total_steps = 0
        completed = 0
        failed = 0
        running = 0
        pending = 0

        for _, step in plan.get_all_steps():
            total_steps += 1
            if step.status == StepStatus.DONE:
                completed += 1
            elif step.status == StepStatus.FAILED:
                failed += 1
            elif step.status == StepStatus.RUNNING:
                running += 1
            elif step.status == StepStatus.PENDING:
                pending += 1

        return {
            "plan_id": plan.id,
            "task": plan.task,
            "status": plan.status.value,
            "total_steps": total_steps,
            "completed": completed,
            "failed": failed,
            "running": running,
            "pending": pending,
            "progress": round(completed / total_steps * 100, 1) if total_steps > 0 else 0,
            "created_at": plan.created_at,
            "completed_at": plan.completed_at,
        }

    def list_plans(self) -> list[dict]:
        return [
            {
                "plan_id": p.id,
                "task": p.task,
                "status": p.status.value,
                "created_at": p.created_at,
            }
            for p in self._plans.values()
        ]

    def execute_plan_step(self, plan_id: str, step_id: str) -> dict[str, Any]:
        plan = self._plans.get(plan_id)
        if not plan:
            return {"error": f"Plan not found: {plan_id}"}

        target_step = None
        target_phase = None
        for phase in plan.phases:
            for step in phase.steps:
                if step.id == step_id:
                    target_step = step
                    target_phase = phase
                    break
            if target_step:
                break

        if not target_step:
            return {"error": f"Step not found: {step_id}"}

        if target_step.status == StepStatus.DONE:
            return {"error": "Step already completed", "step_id": step_id}

        if not plan.all_dependencies_met(target_step):
            unmet = []
            all_steps = {s.id: s for _, s in plan.get_all_steps()}
            for dep_id in target_step.depends_on:
                dep = all_steps.get(dep_id)
                if not dep or dep.status != StepStatus.DONE:
                    unmet.append(dep_id)
            return {"error": f"Dependencies not met: {unmet}", "step_id": step_id}

        target_step.status = StepStatus.RUNNING
        plan.status = PlanStatus.EXECUTING
        bus.emit("plan.step.started", {"plan_id": plan_id, "step_id": step_id, "tool": target_step.tool})

        return {
            "plan_id": plan_id,
            "phase_id": target_phase.id,
            "step_id": step_id,
            "tool": target_step.tool,
            "args": target_step.args,
            "status": "ready",
            "message": "Step is ready for execution",
        }

    def complete_plan_step(self, plan_id: str, step_id: str, result: dict[str, Any] | None = None) -> dict[str, Any]:
        plan = self._plans.get(plan_id)
        if not plan:
            return {"error": f"Plan not found: {plan_id}"}

        target_step = None
        for phase in plan.phases:
            for step in phase.steps:
                if step.id == step_id:
                    target_step = step
                    break
            if target_step:
                break

        if not target_step:
            return {"error": f"Step not found: {step_id}"}

        target_step.status = StepStatus.DONE
        target_step.result = result or {}
        bus.emit("plan.step.completed", {"plan_id": plan_id, "step_id": step_id})

        all_done = all(
            s.status in (StepStatus.DONE, StepStatus.SKIPPED)
            for _, s in plan.get_all_steps()
        )
        any_failed = any(s.status == StepStatus.FAILED for _, s in plan.get_all_steps())

        if all_done:
            plan.status = PlanStatus.COMPLETED
            plan.completed_at = time.time()
            bus.emit("plan.completed", {"plan_id": plan_id})
        elif any_failed:
            plan.status = PlanStatus.FAILED
            bus.emit("plan.failed", {"plan_id": plan_id})

        return {"plan_id": plan_id, "step_id": step_id, "status": "completed"}

    def fail_plan_step(self, plan_id: str, step_id: str, error: str = "") -> dict[str, Any]:
        plan = self._plans.get(plan_id)
        if not plan:
            return {"error": f"Plan not found: {plan_id}"}

        target_step = None
        for phase in plan.phases:
            for step in phase.steps:
                if step.id == step_id:
                    target_step = step
                    break
            if target_step:
                break

        if not target_step:
            return {"error": f"Step not found: {step_id}"}

        target_step.status = StepStatus.FAILED
        target_step.result = {"error": error}
        plan.status = PlanStatus.FAILED
        bus.emit("plan.step.failed", {"plan_id": plan_id, "step_id": step_id, "error": error})

        return {"plan_id": plan_id, "step_id": step_id, "status": "failed", "error": error}

    def rollback_plan_step(self, plan_id: str, step_id: str) -> dict[str, Any]:
        plan = self._plans.get(plan_id)
        if not plan:
            return {"error": f"Plan not found: {plan_id}"}

        target_step = None
        for phase in plan.phases:
            for step in phase.steps:
                if step.id == step_id:
                    target_step = step
                    break
            if target_step:
                break

        if not target_step:
            return {"error": f"Step not found: {step_id}"}

        if target_step.status == StepStatus.PENDING:
            return {"error": "Step is already pending", "step_id": step_id}

        dependent_steps = []
        for _, s in plan.get_all_steps():
            if step_id in s.depends_on:
                dependent_steps.append(s.id)

        for _, s in plan.get_all_steps():
            if s.id in dependent_steps or s.id == step_id:
                if s.status in (StepStatus.DONE, StepStatus.RUNNING, StepStatus.FAILED):
                    s.status = StepStatus.SKIPPED if s.id != step_id else StepStatus.PENDING
                    s.result = {}

        target_step.status = StepStatus.PENDING
        target_step.result = {}
        plan.status = PlanStatus.EXECUTING
        bus.emit("plan.step.rollback", {"plan_id": plan_id, "step_id": step_id})

        return {
            "plan_id": plan_id,
            "step_id": step_id,
            "rolled_back": dependent_steps,
            "status": "rolled_back",
        }

    def verify_plan_step(self, plan_id: str, step_id: str) -> dict[str, Any]:
        plan = self._plans.get(plan_id)
        if not plan:
            return {"error": f"Plan not found: {plan_id}"}

        target_step = None
        for phase in plan.phases:
            for step in phase.steps:
                if step.id == step_id:
                    target_step = step
                    break
            if target_step:
                break

        if not target_step:
            return {"error": f"Step not found: {step_id}"}

        if target_step.status != StepStatus.DONE:
            return {
                "step_id": step_id,
                "verified": False,
                "reason": f"Step status is '{target_step.status.value}', expected 'done'",
            }

        if target_step.verify:
            return {
                "step_id": step_id,
                "verified": True,
                "verification_method": target_step.verify,
                "message": "Step completed and verification rule present",
            }

        return {
            "step_id": step_id,
            "verified": True,
            "message": "Step completed (no verification rule specified)",
        }

    def delete_plan(self, plan_id: str) -> bool:
        if plan_id in self._plans:
            del self._plans[plan_id]
            bus.emit("plan.deleted", {"plan_id": plan_id})
            return True
        return False


planning_engine = PlanningEngine()
