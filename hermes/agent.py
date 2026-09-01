"""Agent loop — tool calling with output parsing for Hermes."""
import json
import re
import time
import uuid

from hermes.bus import bus
from hermes.ollama import ollama
from hermes.tools import TOOL_MAP, TOOLS_SCHEMA, call_tool
from hermes.core import MODEL_AGENT, MAX_ITERATIONS
from hermes.router import SYSTEM_AGENT


def _parse_tool_from_text(text: str) -> list:
    """Parse tool calls from plain text when model doesn't use function calling."""
    calls = []

    patterns = [
        (r'```json\s*\{[^`]*?"tool"\s*:\s*"([^"]+)"[^`]*?\}\s*```', 'json_block'),
        (r'```tool_call\s*\n(.*?)\n```', 'tool_block'),
        (r'(?:CALL|call|Call)\s+(\w+)\(([^)]*)\)', 'func_call'),
        (r'\[(?:TOOL|tool)\]\s*(\w+):\s*(.+)', 'bracket'),
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
            except Exception:
                continue

    valid_tools = set(TOOL_MAP.keys())
    return [c for c in calls if c["name"] in valid_tools]


class AgentLoop:
    def __init__(self, task: str, model: str = None):
        self.task = task
        self.model = model or MODEL_AGENT
        self.messages = [
            {"role": "system", "content": SYSTEM_AGENT},
            {"role": "user", "content": task},
        ]
        self.steps = []
        self.done = False
        self.result_summary = ""
        self.consecutive_no_tools = 0

    async def run(self, on_step=None):
        bus.emit("agent.start", {"task": self.task[:200], "model": self.model})

        for iteration in range(MAX_ITERATIONS):
            if self.done:
                break

            bus.emit("agent.iteration", {"step": iteration + 1, "max": MAX_ITERATIONS})

            response_text = ""
            tool_calls = []

            async for chunk in ollama.chat_stream(self.messages, self.model, tools=TOOLS_SCHEMA):
                if "error" in chunk:
                    bus.emit("agent.error", {"error": chunk["error"]})
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
                self.consecutive_no_tools += 1
                if self.done:
                    break
                if self.consecutive_no_tools >= 3:
                    self.messages.append({
                        "role": "user",
                        "content": (
                            "You MUST use tools. Available tools: " +
                            ", ".join(TOOL_MAP.keys()) +
                            "\nExample: Use workspace_file_ops to create files, execute_shell_command to run commands, done when finished."
                        )
                    })
                    self.consecutive_no_tools = 0
                    continue
                if response_text.strip():
                    self.messages.append({
                        "role": "user",
                        "content": "Continue using tools. If done, call the done tool."
                    })
                    continue
                else:
                    break

            self.consecutive_no_tools = 0

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

                result_str = json.dumps(result, ensure_ascii=False)[:2000]
                self.messages.append({
                    "role": "tool",
                    "content": f"Tool '{name}' result:\n{result_str}"
                })

        bus.emit("agent.finish", {
            "steps": len(self.steps),
            "done": self.done,
            "summary": self.result_summary,
        })

        return {
            "done": self.done,
            "steps": len(self.steps),
            "summary": self.result_summary,
            "history": self.steps,
        }
