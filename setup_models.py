#!/usr/bin/env python3
"""
Hermes Studio — Auto-install local AI models into Ollama.
Run once. Downloads ~2GB total. Never needed again.
"""
import subprocess
import sys
import json
import pathlib
import urllib.request
import time
# --- константы вынесены FORGE refactor ---
CONST_3 = 3


ROOT = pathlib.Path(__file__).parent
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
OLLAMA_DIR = ROOT / ".ollama"
OLLAMA_EXE = OLLAMA_DIR / "ollama.exe"
OLLAMA_HOST = "http://127.0.0.1:11434"
OLLAMA_MODELS = str(OLLAMA_DIR / "models")

MODELS = [
    CFG["models"]["reasoning"],  # deepseek-r1:1.5b
    CFG["models"]["coding"],     # qwen2.5-coder:1.5b
]


def ollama_running():
    try:
        req = urllib.request.Request(f"{OLLAMA_HOST}/api/tags")
        with urllib.request.urlopen(req, timeout=CONST_3) as r:
            return r.status == 200
    except Exception:
        return False


def get_installed_models():
    try:
        req = urllib.request.Request(f"{OLLAMA_HOST}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
            return {m["name"] for m in data.get("models", [])}
    except Exception:
        return set()


def pull_model(name):
    print(f"\n  Downloading {name} ...")
    proc = subprocess.Popen(
        [str(OLLAMA_EXE), "pull", name],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    for line in proc.stdout:
        line = line.strip()
        if line:
            print(f"    {line}")
    proc.wait()
    return proc.returncode == 0


def main():
    print()
    print("  ====================================")
    print("   Hermes Studio — Model Setup")
    print("  ====================================")
    print()

    # Set env vars
    os.environ["OLLAMA_HOST"] = "127.0.0.1:11434"
    os.environ["OLLAMA_MODELS"] = OLLAMA_MODELS

    # Check Ollama binary
    if not OLLAMA_EXE.exists():
        print(f"  Ollama not found at: {OLLAMA_EXE}")
        print("  Download from https://ollama.com")
        print("  Extract ollama.exe to .ollama/ folder")
        sys.exit(1)

    # Check Ollama running
    if not ollama_running():
        print("  Ollama is not running.")
        print("  Starting it for you...")
        subprocess.Popen(
            [str(OLLAMA_EXE), "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        import time
        time.sleep(CONST_3)
        if not ollama_running():
            print("  Could not start Ollama. Start manually: ollama serve")
            sys.exit(1)
            print("  Ollama is running!")

    print("  Ollama is running.")

    installed = get_installed_models()
    print(f"  Installed models: {len(installed)}")
    for m in installed:
        print(f"    - {m}")

    # Check what we need
    needed = []
    for model in MODELS:
        if model in installed:
            print(f"  [OK] {model}")
        else:
            print(f"  [MISSING] {model}")
            needed.append(model)

    if not needed:
        print()
        print("  All models installed. Ready to go!")
        return

    print()
    print(f"  Installing {len(needed)} model(s)...")
    print()

    for model in needed:
        ok = pull_model(model)
        if ok:
            print(f"  [OK] {model} installed")
        else:
            print(f"  [FAIL] {model} — check Ollama output above")

    print()
    print("  ====================================")
    print("   Setup complete!")
    print("   Launch Hermes:  python launch.py")
    print("  ====================================")
    print()


if __name__ == "__main__":
    main()
