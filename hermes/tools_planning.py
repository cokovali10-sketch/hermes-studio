"""Planning tools for the Hermes agent."""
import json

from hermes.modules.planning import planning_engine
from hermes.modules.plan_schema import PlanStatus


async def tool_create_plan(task: str, phases: list[dict] | None = None, context: str = "") -> dict:
    try:
        plan = planning_engine.create_plan(task, context, phases)
        return {
            "success": True,
            "plan_id": plan.id,
            "task": plan.task,
            "phases": len(plan.phases),
            "total_steps": sum(len(p.steps) for p in plan.phases),
            "status": plan.status.value,
        }
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def tool_execute_plan_step(plan_id: str, step_id: str) -> dict:
    result = planning_engine.execute_plan_step(plan_id, step_id)
    if "error" in result:
        result["success"] = False
    else:
        result["success"] = True
    return result


async def tool_verify_plan_step(plan_id: str, step_id: str) -> dict:
    result = planning_engine.verify_plan_step(plan_id, step_id)
    result["success"] = "error" not in result
    return result


async def tool_get_plan_status(plan_id: str) -> dict:
    return planning_engine.get_plan_status(plan_id)


async def tool_rollback_plan_step(plan_id: str, step_id: str) -> dict:
    result = planning_engine.rollback_plan_step(plan_id, step_id)
    if "error" in result:
        result["success"] = False
    else:
        result["success"] = True
    return result


async def tool_list_plans() -> dict:
    plans = planning_engine.list_plans()
    return {"plans": plans, "count": len(plans), "success": True}


async def tool_complete_plan_step(plan_id: str, step_id: str, result_json: str = "{}") -> dict:
    try:
        result = json.loads(result_json) if result_json else {}
    except json.JSONDecodeError:
        result = {}
    out = planning_engine.complete_plan_step(plan_id, step_id, result)
    if "error" in out:
        out["success"] = False
    else:
        out["success"] = True
    return out


PLANNING_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "create_plan",
            "description": "Create a structured plan with phases and steps for a task. Each step specifies a tool and arguments.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "Task description"},
                    "context": {"type": "string", "description": "Additional context for planning"},
                    "phases": {
                        "type": "array",
                        "description": "List of phases, each with name and steps",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "steps": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "id": {"type": "string"},
                                            "tool": {"type": "string"},
                                            "args": {"type": "object"},
                                            "depends_on": {"type": "array", "items": {"type": "string"}},
                                            "verify": {"type": "string"},
                                        },
                                        "required": ["tool"],
                                    },
                                },
                            },
                            "required": ["name"],
                        },
                    },
                },
                "required": ["task"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_plan_step",
            "description": "Execute a specific step in a plan. Checks dependencies before execution.",
            "parameters": {
                "type": "object",
                "properties": {
                    "plan_id": {"type": "string", "description": "Plan ID"},
                    "step_id": {"type": "string", "description": "Step ID to execute"},
                },
                "required": ["plan_id", "step_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "verify_plan_step",
            "description": "Verify that a plan step was completed successfully.",
            "parameters": {
                "type": "object",
                "properties": {
                    "plan_id": {"type": "string", "description": "Plan ID"},
                    "step_id": {"type": "string", "description": "Step ID to verify"},
                },
                "required": ["plan_id", "step_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_plan_status",
            "description": "Get the current status and progress of a plan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "plan_id": {"type": "string", "description": "Plan ID"},
                },
                "required": ["plan_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rollback_plan_step",
            "description": "Roll back a plan step and its dependents to pending status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "plan_id": {"type": "string", "description": "Plan ID"},
                    "step_id": {"type": "string", "description": "Step ID to rollback"},
                },
                "required": ["plan_id", "step_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_plans",
            "description": "List all active plans with their status.",
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
            "name": "complete_plan_step",
            "description": "Mark a plan step as completed with a result.",
            "parameters": {
                "type": "object",
                "properties": {
                    "plan_id": {"type": "string", "description": "Plan ID"},
                    "step_id": {"type": "string", "description": "Step ID"},
                    "result_json": {"type": "string", "description": "JSON result of step execution"},
                },
                "required": ["plan_id", "step_id"],
            },
        },
    },
]

PLANNING_TOOL_MAP = {
    "create_plan": tool_create_plan,
    "execute_plan_step": tool_execute_plan_step,
    "verify_plan_step": tool_verify_plan_step,
    "get_plan_status": tool_get_plan_status,
    "rollback_plan_step": tool_rollback_plan_step,
    "list_plans": tool_list_plans,
    "complete_plan_step": tool_complete_plan_step,
}
