"""Plan executor — runs plan steps sequentially with dependency checks."""
import time
from typing import Any, Callable, Awaitable

from hermes.bus import bus
from hermes.modules.plan_schema import Plan, Phase, Step, PlanStatus, StepStatus


class PlanExecutor:
    def __init__(self):
        self._tool_handlers: dict[str, Callable[..., Awaitable[dict]]] = {}
        self._execution_log: list[dict] = []

    def register_tool(self, name: str, handler: Callable[..., Awaitable[dict]]):
        self._tool_handlers[name] = handler

    def get_log(self) -> list[dict]:
        return list(self._execution_log)

    async def execute_plan(self, plan: Plan, on_step_complete: Callable | None = None) -> dict[str, Any]:
        plan.status = PlanStatus.EXECUTING
        bus.emit("executor.plan.started", {"plan_id": plan.id})
        results = []

        for phase in plan.phases:
            phase_result = await self.execute_phase(plan, phase, on_step_complete)
            results.append(phase_result)

            if phase_result.get("failed_steps"):
                plan.status = PlanStatus.FAILED
                return {
                    "plan_id": plan.id,
                    "status": "failed",
                    "phase": phase.name,
                    "results": results,
                }

        plan.status = PlanStatus.COMPLETED
        plan.completed_at = time.time()
        bus.emit("executor.plan.completed", {"plan_id": plan.id})

        return {
            "plan_id": plan.id,
            "status": "completed",
            "results": results,
        }

    async def execute_phase(self, plan: Plan, phase: Phase, on_step_complete: Callable | None = None) -> dict[str, Any]:
        bus.emit("executor.phase.started", {"plan_id": plan.id, "phase_id": phase.id})
        completed = []
        failed = []

        for step in phase.steps:
            if step.status == StepStatus.DONE:
                completed.append(step.id)
                continue

            if step.status == StepStatus.SKIPPED:
                continue

            if not plan.all_dependencies_met(step):
                failed.append({"step_id": step.id, "error": "dependencies not met"})
                continue

            result = await self.execute_step(step, plan)
            if result.get("success"):
                step.status = StepStatus.DONE
                completed.append(step.id)
                if on_step_complete:
                    await on_step_complete(plan, step, result)
            else:
                step.status = StepStatus.FAILED
                failed.append({"step_id": step.id, "error": result.get("error", "unknown")})
                bus.emit("executor.step.failed", {"plan_id": plan.id, "step_id": step.id})

        return {
            "phase_id": phase.id,
            "phase_name": phase.name,
            "completed": completed,
            "failed": failed,
        }

    async def execute_step(self, step: Step, plan: Plan | None = None) -> dict[str, Any]:
        step.status = StepStatus.RUNNING
        start_time = time.time()
        bus.emit("executor.step.started", {"step_id": step.id, "tool": step.tool})

        handler = self._tool_handlers.get(step.tool)
        if not handler:
            error = f"No handler registered for tool: {step.tool}"
            step.status = StepStatus.FAILED
            step.result = {"error": error}
            self._log_execution(step.id, step.tool, False, error, time.time() - start_time)
            return {"success": False, "error": error}

        try:
            result = await handler(**step.args)
            elapsed = time.time() - start_time

            if result.get("success", False):
                step.status = StepStatus.DONE
                step.result = result
                self._log_execution(step.id, step.tool, True, None, elapsed)
                bus.emit("executor.step.completed", {"step_id": step.id, "elapsed": elapsed})
                return result
            else:
                step.status = StepStatus.FAILED
                step.result = result
                error = result.get("error", "Step returned failure")
                self._log_execution(step.id, step.tool, False, error, elapsed)
                return result
        except Exception as e:
            elapsed = time.time() - start_time
            step.status = StepStatus.FAILED
            error = str(e)
            step.result = {"error": error}
            self._log_execution(step.id, step.tool, False, error, elapsed)
            bus.emit("executor.step.error", {"step_id": step.id, "error": error})
            return {"success": False, "error": error}

    async def verify_step(self, step: Step) -> dict[str, Any]:
        if step.status != StepStatus.DONE:
            return {
                "step_id": step.id,
                "verified": False,
                "reason": f"Step status is '{step.status.value}'",
            }

        if not step.verify:
            return {"step_id": step.id, "verified": True, "message": "No verification needed"}

        handler = self._tool_handlers.get("run_python")
        if not handler:
            return {"step_id": step.id, "verified": True, "message": "Cannot verify — no Python handler"}

        try:
            result = await handler(code=step.verify)
            if result.get("success"):
                return {"step_id": step.id, "verified": True, "output": result.get("stdout", "")}
            return {"step_id": step.id, "verified": False, "error": result.get("error", "")}
        except Exception as e:
            return {"step_id": step.id, "verified": False, "error": str(e)}

    async def rollback_step(self, step: Step, plan: Plan | None = None) -> dict[str, Any]:
        if step.status == StepStatus.PENDING:
            return {"step_id": step.id, "rolled_back": True, "message": "Already pending"}

        step.status = StepStatus.PENDING
        step.result = {}

        if plan:
            dependent = []
            for _, s in plan.get_all_steps():
                if step.id in s.depends_on and s.status != StepStatus.PENDING:
                    s.status = StepStatus.SKIPPED
                    s.result = {}
                    dependent.append(s.id)
            return {"step_id": step.id, "rolled_back": True, "affected": dependent}

        return {"step_id": step.id, "rolled_back": True}

    def _log_execution(self, step_id: str, tool: str, success: bool, error: str | None, elapsed: float):
        self._execution_log.append({
            "step_id": step_id,
            "tool": tool,
            "success": success,
            "error": error,
            "elapsed": round(elapsed, 3),
            "timestamp": time.time(),
        })


plan_executor = PlanExecutor()
