"""Agent loop — tool calling with smart routing, planning, and fallback for small models."""
import json
import re
import time
import uuid

from hermes.bus import bus
from hermes.ollama import ollama
from hermes.tools import TOOL_MAP, TOOLS_SCHEMA, call_tool
from hermes.core import MODEL_AGENT, MAX_ITERATIONS, WORKSPACE_DIR
from hermes.tool_router import classify_request, get_relevant_tools, get_tool_schemas, build_compact_system
from hermes.planner import create_plan, render_plan_for_model, get_next_step, mark_step_done, suggest_recovery
from hermes.workflows import match_workflow, render_workflow_for_model


def _parse_tool_from_text(text: str) -> list:
    """Parse tool calls from plain text when model doesn't use function calling."""
    calls = []

    patterns = [
        (r'```json\s*\{[^`]*?"tool"\s*:\s*"([^"]+)"[^`]*?\}\s*```', 'json_block'),
        (r'```tool_call\s*\n(.*?)\n```', 'tool_block'),
        (r'(?:CALL|call|Call)\s+(\w+)\(([^)]*)\)', 'func_call'),
        (r'\[(?:TOOL|tool)\]\s*(\w+):\s*(.+)', 'bracket'),
        (r'"name"\s*:\s*"([^"]+)".*?"arguments"\s*:\s*\{([^}]*)\}', 'json_inline'),
    ]

    for pattern, fmt in patterns:
        for m in re.finditer(pattern, text, re.DOTALL):
            try:
                if fmt == 'json_block':
                    data = json.loads(m.group(0).strip('`json\n'))
                    calls.append({"name": data.get("tool", ""), "arguments": data.get("args", data.get("arguments", {}))})
                elif fmt == 'tool_block':
                    lines = m.group(1).strip().splitlines()
                    name = lines[0].strip() if lines else ""
                    args = {}
                    for line in lines[1:]:
                        if ":" in line:
                            k, v = line.split(":", 1)
                            args[k.strip()] = v.strip().strip('"')
                    calls.append({"name": name, "arguments": args})
                elif fmt == 'func_call':
                    name = m.group(1)
                    args_str = m.group(2)
                    args = {}
                    for pair in args_str.split(","):
                        if "=" in pair:
                            k, v = pair.split("=", 1)
                            args[k.strip()] = v.strip().strip('"').strip("'")
                    calls.append({"name": name, "arguments": args})
                elif fmt == 'bracket':
                    name = m.group(1)
                    args_str = m.group(2).strip()
                    args = {}
                    if args_str:
                        for pair in args_str.split(";"):
                            if "=" in pair:
                                k, v = pair.split("=", 1)
                                args[k.strip()] = v.strip().strip('"')
                    calls.append({"name": name, "arguments": args})
                elif fmt == 'json_inline':
                    name = m.group(1)
                    args_raw = m.group(2)
                    args = {}
                    for pair in args_raw.split(","):
                        pair = pair.strip()
                        if ":" in pair:
                            k, v = pair.split(":", 1)
                            k = k.strip().strip('"')
                            v = v.strip().strip('"')
                            args[k] = v
                    calls.append({"name": name, "arguments": args})
            except Exception:
                continue

    valid_tools = set(TOOL_MAP.keys())
    return [c for c in calls if c["name"] in valid_tools]


def _auto_select_tool(text: str, relevant_tools: list) -> dict | None:
    """When model doesn't produce a tool call, try to auto-select based on context."""
    text_lower = text.lower()

    if any(kw in text_lower for kw in ["file", "файл", "write", "напиши", "создай", "read", "прочитай"]):
        for name in relevant_tools:
            if name == "workspace_file_ops":
                return {"name": "workspace_file_ops", "arguments": {"action": "list", "path": "."}}

    if any(kw in text_lower for kw in ["run", "запусти", "выполни", "install", "установи"]):
        for name in relevant_tools:
            if name == "execute_shell_command":
                return {"name": "execute_shell_command", "arguments": {"command": "ls"}}

    if any(kw in text_lower for kw in ["commit", "коммит", "сохрани"]):
        for name in relevant_tools:
            if name == "git_checkpoint":
                return {"name": "git_checkpoint", "arguments": {"message": "chore: save progress"}}

    if any(kw in text_lower for kw in ["search", "найди", "поиск", "grep"]):
        for name in relevant_tools:
            if name == "search_code":
                return {"name": "search_code", "arguments": {"pattern": "TODO"}}

    return None


class AgentLoop:
    def __init__(self, task: str, model: str = None):
        self.task = task
        self.model = model or MODEL_AGENT
        self.steps = []
        self.done = False
        self.result_summary = ""
        self.consecutive_no_tools = 0
        self.consecutive_errors = 0

        self.classification = classify_request(task)
        self.relevant_tools = get_relevant_tools(task, max_tools=15)
        self.filtered_schemas = get_tool_schemas(task, TOOLS_SCHEMA, max_tools=15)
        self.workflow = match_workflow(task)
        self.plan = create_plan(task) if not self.workflow else None
        self.workflow_step = 0

        system_prompt = build_compact_system(task, str(WORKSPACE_DIR))
        self.messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task},
        ]

        if self.workflow:
            wf_instructions = render_workflow_for_model(self.workflow)
            self.messages.append({"role": "user", "content": f"Follow this workflow:\n{wf_instructions}"})
        elif self.plan and self.plan["needs_user_input"]:
            plan_text = render_plan_for_model(self.plan, task)
            self.messages.append({"role": "user", "content": f"Here is the plan:\n{plan_text}\n\nExecute step by step. Call one tool at a time."})

    async def run(self, on_step=None):
        bus.emit("agent.start", {
            "task": self.task[:200],
            "model": self.model,
            "classification": self.classification,
            "tools_count": len(self.relevant_tools),
            "workflow": self.workflow["name"] if self.workflow else None,
        })

        for iteration in range(MAX_ITERATIONS):
            if self.done:
                break

            bus.emit("agent.iteration", {"step": iteration + 1, "max": MAX_ITERATIONS})

            response_text = ""
            tool_calls = []

            schemas_to_use = self.filtered_schemas if self.filtered_schemas else TOOLS_SCHEMA

            async for chunk in ollama.chat_stream(self.messages, self.model, tools=schemas_to_use):
                if "error" in chunk:
                    bus.emit("agent.error", {"error": chunk["error"]})
                    self.consecutive_errors += 1
                    break

                if "message" in chunk:
                    msg = chunk["message"]
                    if msg.get("content"):
                        response_text += msg["content"]
                    if msg.get("tool_calls"):
                        for tc in msg["tool_calls"]:
                            fn = tc.get("function", {})
                            tool_calls.append({
                                "id": tc.get("id", f"call_{uuid.uuid4().hex[:8]}"),
                                "name": fn.get("name", ""),
                                "arguments": fn.get("arguments", {}),
                            })

            if response_text:
                bus.emit("agent.text", {"text": response_text[:500]})
                self.messages.append({"role": "assistant", "content": response_text})

            if not tool_calls:
                parsed = _parse_tool_from_text(response_text)
                if parsed:
                    tool_calls = parsed

            if not tool_calls:
                auto = _auto_select_tool(response_text, self.relevant_tools)
                if auto:
                    tool_calls = [auto]
                    bus.emit("agent.auto_select", {"tool": auto["name"]})

            if not tool_calls:
                self.consecutive_no_tools += 1
                if self.done:
                    break
                if self.consecutive_no_tools >= 2:
                    hint = self._get_stuck_hint()
                    self.messages.append({"role": "user", "content": hint})
                    self.consecutive_no_tools = 0
                    continue
                if response_text.strip():
                    self.messages.append({
                        "role": "user",
                        "content": (
                            "You must call a tool. Available: " +
                            ", ".join(self.relevant_tools[:10]) +
                            "\nCall one tool now."
                        )
                    })
                    continue
                else:
                    break

            self.consecutive_no_tools = 0
            self.consecutive_errors = 0

            for tc in tool_calls:
                name = tc["name"]
                args = tc["arguments"]

                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}

                bus.emit("agent.tool_call", {"tool": name, "args": json.dumps(args, ensure_ascii=False)[:300]})

                result = await call_tool(name, args)

                step_record = {
                    "step": iteration + 1,
                    "tool": name,
                    "args": args,
                    "result": result,
                    "ts": time.time(),
                }
                self.steps.append(step_record)

                if on_step:
                    await on_step(step_record)

                if name == "done":
                    self.done = True
                    self.result_summary = args.get("summary", "")
                    break

                if not result.get("success", True):
                    self.consecutive_errors += 1
                    if self.consecutive_errors >= 3:
                        error_hint = self._get_error_recovery_hint(name, result)
                        self.messages.append({"role": "user", "content": error_hint})
                        self.consecutive_errors = 0
                        continue

                result_str = json.dumps(result, ensure_ascii=False)[:1500]
                self.messages.append({
                    "role": "tool",
                    "content": f"Tool '{name}' result:\n{result_str}"
                })

                if self.plan:
                    next_step = get_next_step(self.plan)
                    if next_step and next_step["tool"] == name:
                        mark_step_done(self.plan, next_step["index"], result.get("success", True))

        bus.emit("agent.finish", {
            "steps": len(self.steps),
            "done": self.done,
            "summary": self.result_summary,
            "classification": self.classification,
        })

        return {
            "done": self.done,
            "steps": len(self.steps),
            "summary": self.result_summary,
            "history": self.steps,
        }

    def _get_stuck_hint(self) -> str:
        """Generate a hint when the agent is stuck."""
        if self.workflow:
            remaining = self.workflow["steps"][self.workflow_step:]
            if remaining:
                next_step = remaining[0]
                args_str = json.dumps(next_step["args"], ensure_ascii=False)[:80]
                return (
                    f"Continue the workflow. Next step: Call {next_step['tool']}({args_str})\n"
                    f"Available tools: {', '.join(self.relevant_tools[:10])}"
                )

        if self.plan:
            next_step = get_next_step(self.plan)
            if next_step:
                args_str = json.dumps(next_step["args"], ensure_ascii=False)[:80]
                return (
                    f"Next step: Call {next_step['tool']}({args_str})\n"
                    f"Hint: {next_step['hint']}\n"
                    f"Available tools: {', '.join(self.relevant_tools[:10])}"
                )

        return (
            f"Continue the task. Use these tools: {', '.join(self.relevant_tools[:10])}\n"
            "Call one tool at a time. If done, call 'done' with a summary."
        )

    def _get_error_recovery_hint(self, tool_name: str, result: dict) -> str:
        """Generate a recovery hint after errors."""
        error = result.get("error", "unknown error")
        return (
            f"Tool '{tool_name}' failed: {error}\n"
            f"Try a different approach. Available tools: {', '.join(self.relevant_tools[:10])}\n"
            "If you can't proceed, call 'done' with what you've accomplished so far."
        )
