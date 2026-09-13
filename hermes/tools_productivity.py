"""Productivity tools for Hermes agent."""
import asyncio
import json
import pathlib
import time
from datetime import datetime

TOOLS = [
    {"name": "create_note", "description": "Create a markdown note file", "parameters": {"type": "object", "properties": {"title": {"type": "string", "description": "Note title (used as filename)"}, "content": {"type": "string", "description": "Markdown content"}, "folder": {"type": "string", "description": "Subfolder inside notes directory", "default": "notes"}}, "required": ["title", "content"]}},
    {"name": "search_notes", "description": "Search notes by keyword or regex", "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "Search keyword or regex"}, "folder": {"type": "string", "default": "notes"}}, "required": ["query"]}},
    {"name": "create_reminder", "description": "Create a timed reminder", "parameters": {"type": "object", "properties": {"message": {"type": "string", "description": "Reminder message"}, "time": {"type": "string", "description": "When to remind (ISO format or relative like '30m', '2h')"}, "channel": {"type": "string", "description": "Notification channel", "default": "console"}}, "required": ["message", "time"]}},
    {"name": "list_reminders", "description": "List all active reminders", "parameters": {"type": "object", "properties": {"include_past": {"type": "boolean", "default": False}}}},
    {"name": "create_todo", "description": "Create a todo item", "parameters": {"type": "object", "properties": {"title": {"type": "string", "description": "Todo title"}, "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"], "default": "medium"}, "due": {"type": "string", "description": "Due date (ISO format)"}, "tags": {"type": "array", "items": {"type": "string"}, "description": "Tags for categorization"}}, "required": ["title"]}},
    {"name": "list_todos", "description": "List todo items with optional filters", "parameters": {"type": "object", "properties": {"status": {"type": "string", "enum": ["pending", "done", "all"], "default": "all"}, "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"]}, "tag": {"type": "string", "description": "Filter by tag"}}}},
    {"name": "pomodoro_start", "description": "Start a Pomodoro timer (25 min work + 5 min break)", "parameters": {"type": "object", "properties": {"work_minutes": {"type": "integer", "default": 25}, "break_minutes": {"type": "integer", "default": 5}, "task": {"type": "string", "description": "Task name for this session"}}}},
    {"name": "timer_start", "description": "Start a countdown timer", "parameters": {"type": "object", "properties": {"duration": {"type": "string", "description": "Duration (e.g. '5m', '1h30m', '90s')"}, "label": {"type": "string", "description": "Timer label"}}, "required": ["duration"]}},
    {"name": "calendar_add", "description": "Add a calendar event to a local ICS file", "parameters": {"type": "object", "properties": {"title": {"type": "string", "description": "Event title"}, "start": {"type": "string", "description": "Start datetime (ISO format)"}, "end": {"type": "string", "description": "End datetime (ISO format)"}, "description": {"type": "string"}, "file": {"type": "string", "description": "ICS file path", "default": "calendar.ics"}}, "required": ["title", "start", "end"]}},
    {"name": "calendar_list", "description": "List upcoming events from ICS calendar file", "parameters": {"type": "object", "properties": {"file": {"type": "string", "default": "calendar.ics"}, "days": {"type": "integer", "description": "How many days ahead to look", "default": 30}}}},
]

functions = {}
DATA_DIR = pathlib.Path("hermes_data")

def _data_file(name):
    DATA_DIR.mkdir(exist_ok=True)
    return DATA_DIR / name

async def create_note(args):
    title = args["title"]
    content = args["content"]
    folder = args.get("folder", "notes")
    note_dir = _data_file(folder)
    note_dir.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in title).strip().replace(" ", "_")
    note_path = note_dir / f"{safe_name}.md"
    header = f"# {title}\n\n_Created: {datetime.now().isoformat()}_\n\n---\n\n"
    note_path.write_text(header + content, encoding="utf-8")
    return json.dumps({"success": True, "path": str(note_path), "title": title})

async def search_notes(args):
    query = args["query"]
    folder = args.get("folder", "notes")
    note_dir = _data_file(folder)
    if not note_dir.exists():
        return json.dumps({"success": True, "results": [], "count": 0})
    import re
    try:
        regex = re.compile(query, re.IGNORECASE)
    except re.error:
        regex = re.compile(re.escape(query), re.IGNORECASE)
    results = []
    for note_file in note_dir.rglob("*.md"):
        try:
            text = note_file.read_text(encoding="utf-8", errors="replace")
            lines = text.splitlines()
            for i, line in enumerate(lines):
                if regex.search(line):
                    results.append({"file": str(note_file.relative_to(DATA_DIR)), "line": i + 1, "text": line.strip()[:200], "title": title_from_file(note_file)})
                    break
        except Exception:
            continue
    return json.dumps({"success": True, "results": results[:50], "count": len(results)})

def title_from_file(path):
    return path.stem.replace("_", " ").title()

async def create_reminder(args):
    message = args["message"]
    time_str = args["time"]
    channel = args.get("channel", "console")
    now = datetime.now()
    if time_str.endswith("m"):
        mins = int(time_str[:-1])
        trigger = now.timestamp() + mins * 60
    elif time_str.endswith("h"):
        hours = int(time_str[:-1])
        trigger = now.timestamp() + hours * 3600
    elif time_str.endswith("s"):
        secs = int(time_str[:-1])
        trigger = now.timestamp() + secs
    else:
        trigger = datetime.fromisoformat(time_str).timestamp()
    reminders = _load_json("reminders.json", [])
    reminder = {
        "id": int(time.time() * 1000),
        "message": message,
        "trigger_at": trigger,
        "trigger_human": datetime.fromtimestamp(trigger).isoformat(),
        "channel": channel,
        "created": now.isoformat(),
        "fired": False,
    }
    reminders.append(reminder)
    _save_json("reminders.json", reminders)
    return json.dumps({"success": True, "reminder": reminder})

async def list_reminders(args):
    include_past = args.get("include_past", False)
    reminders = _load_json("reminders.json", [])
    now = time.time()
    if not include_past:
        reminders = [r for r in reminders if not r.get("fired", False) or r["trigger_at"] > now]
    return json.dumps({"success": True, "reminders": reminders, "count": len(reminders)})

async def create_todo(args):
    title = args["title"]
    todo = {
        "id": int(time.time() * 1000),
        "title": title,
        "priority": args.get("priority", "medium"),
        "due": args.get("due"),
        "tags": args.get("tags", []),
        "status": "pending",
        "created": datetime.now().isoformat(),
    }
    todos = _load_json("todos.json", [])
    todos.append(todo)
    _save_json("todos.json", todos)
    return json.dumps({"success": True, "todo": todo})

async def list_todos(args):
    status_filter = args.get("status", "all")
    priority_filter = args.get("priority")
    tag_filter = args.get("tag")
    todos = _load_json("todos.json", [])
    if status_filter != "all":
        todos = [t for t in todos if t["status"] == status_filter]
    if priority_filter:
        todos = [t for t in todos if t["priority"] == priority_filter]
    if tag_filter:
        todos = [t for t in todos if tag_filter in t.get("tags", [])]
    return json.dumps({"success": True, "todos": todos, "count": len(todos)})

async def pomodoro_start(args):
    work = args.get("work_minutes", 25)
    brk = args.get("break_minutes", 5)
    task = args.get("task", "Focus session")
    return json.dumps({
        "success": True,
        "message": f"Pomodoro started: {work}min work / {brk}min break for '{task}'",
        "work_minutes": work,
        "break_minutes": brk,
        "task": task,
        "started_at": datetime.now().isoformat(),
    })

async def timer_start(args):
    duration = args["duration"]
    label = args.get("label", "Timer")
    total_secs = 0
    if "h" in duration:
        parts = duration.split("h")
        total_secs += int(parts[0]) * 3600
        duration = parts[1]
    if "m" in duration:
        parts = duration.split("m")
        total_secs += int(parts[0]) * 60
        duration = parts[1]
    if "s" in duration:
        total_secs += int(duration.replace("s", ""))
    end_time = datetime.now().timestamp() + total_secs
    return json.dumps({
        "success": True,
        "label": label,
        "duration_seconds": total_secs,
        "ends_at": datetime.fromtimestamp(end_time).isoformat(),
    })

async def calendar_add(args):
    title = args["title"]
    start = args["start"]
    end = args["end"]
    desc = args.get("description", "")
    cal_file = _data_file(args.get("file", "calendar.ics"))
    uid = f"{int(time.time()*1000)}@hermes"
    event = f"""BEGIN:VEVENT
UID:{uid}
DTSTART:{_ical_dt(start)}
DTEND:{_ical_dt(end)}
SUMMARY:{title}
DESCRIPTION:{desc}
END:VEVENT"""
    if cal_file.exists():
        content = cal_file.read_text(encoding="utf-8")
        content = content.replace("END:VCALENDAR", event + "\nEND:VCALENDAR")
    else:
        content = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Hermes//EN
{event}
END:VCALENDAR"""
    cal_file.write_text(content, encoding="utf-8")
    return json.dumps({"success": True, "file": str(cal_file), "title": title, "start": start, "end": end})

async def calendar_list(args):
    cal_file = _data_file(args.get("file", "calendar.ics"))
    days = args.get("days", 30)
    if not cal_file.exists():
        return json.dumps({"success": True, "events": [], "count": 0})
    content = cal_file.read_text(encoding="utf-8")
    events = []
    now = datetime.now()
    cutoff = now.timestamp() + days * 86400
    for block in content.split("BEGIN:VEVENT"):
        if "END:VEVENT" not in block:
            continue
        block = block.split("END:VEVENT")[0]
        ev = {}
        for line in block.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                ev[k.strip()] = v.strip()
        summary = ev.get("SUMMARY", "Untitled")
        dtstart = ev.get("DTSTART", "")
        try:
            start_ts = _parse_ical_dt(dtstart)
            if start_ts > now.timestamp() and start_ts < cutoff:
                events.append({"title": summary, "start": dtstart, "description": ev.get("DESCRIPTION", "")})
        except Exception:
            pass
    events.sort(key=lambda e: e["start"])
    return json.dumps({"success": True, "events": events, "count": len(events)})

def _ical_dt(iso_str):
    dt = datetime.fromisoformat(iso_str)
    return dt.strftime("%Y%m%dT%H%M%S")

def _parse_ical_dt(s):
    s = s.strip()
    if "T" in s:
        dt = datetime.strptime(s, "%Y%m%dT%H%M%S")
    else:
        dt = datetime.strptime(s, "%Y%m%d")
    return dt.timestamp()

def _load_json(name, default):
    f = _data_file(name)
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    return default

def _save_json(name, data):
    f = _data_file(name)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

functions = {
    "create_note": create_note,
    "search_notes": search_notes,
    "create_reminder": create_reminder,
    "list_reminders": list_reminders,
    "create_todo": create_todo,
    "list_todos": list_todos,
    "pomodoro_start": pomodoro_start,
    "timer_start": timer_start,
    "calendar_add": calendar_add,
    "calendar_list": calendar_list,
}
