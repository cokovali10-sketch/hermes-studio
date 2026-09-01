"""Core configuration and constants for Hermes."""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))

PORT = CFG["server"]["port"]
URL = f"http://127.0.0.1:{PORT}"
OLLAMA_HOST = CFG["ollama"]["host"]
OLLAMA_DIR = ROOT / ".ollama"
OLLAMA_EXE = OLLAMA_DIR / "ollama.exe"
OLLAMA_MODELS = str(OLLAMA_DIR / "models")

MODEL_REASONING = CFG["models"]["reasoning"]
MODEL_CODING = CFG["models"]["coding"]
MODEL_AGENT = CFG["models"].get("agent", MODEL_CODING)
MODEL_VISION = CFG["models"].get("vision", "llava:1.6-mistral")

UPLOAD_DIR = pathlib.Path(CFG["paths"]["uploads"])
WORKSPACE_DIR = pathlib.Path(CFG["paths"]["workspace"])
BACKUP_DIR = pathlib.Path(CFG["paths"]["backups"])
FRONTEND_DIR = ROOT / "frontend"
PLUGINS_DIR = ROOT / "plugins"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
PLUGINS_DIR.mkdir(parents=True, exist_ok=True)

MAX_TOOL_STEPS = CFG["limits"].get("max_tool_steps", 50)
SHELL_TIMEOUT = CFG["limits"].get("shell_timeout_sec", 120)
MAX_PROMPT_CHARS = CFG["limits"].get("max_prompt_chars", 32000)
AGENT_SYSTEM = CFG.get("agent", {}).get("system_prompt", "You are Hermes.")
MAX_ITERATIONS = CFG.get("agent", {}).get("max_iterations", 30)
