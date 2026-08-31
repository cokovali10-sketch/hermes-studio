#!/usr/bin/env python3
"""
Hermes Studio v3 — Agentic Tool Suite Launcher.
  - Starts Ollama if not running
  - Starts backend server
  - Opens one Edge/Chrome window
  - Prevents duplicate instances (mutex + port check)
  - Kills processes on exit
"""
import sys
import os
import time
import subprocess
import pathlib
import socket
import urllib.request
import ctypes
import signal
import atexit

ROOT = pathlib.Path(__file__).parent
OLLAMA_DIR = ROOT / ".ollama"
OLLAMA_EXE = OLLAMA_DIR / "ollama.exe"
OLLAMA_HOST = "http://127.0.0.1:11434"
OLLAMA_MODELS = str(OLLAMA_DIR / "models")
URL = "http://127.0.0.1:8765"
PORT = 8765
MUTEX_NAME = "Global\\HermesStudioV3"

kernel32 = ctypes.windll.kernel32

_ollama_proc = None
_server_proc = None
_browser_proc = None


def _cleanup():
    global _ollama_proc, _server_proc
    if _server_proc and _server_proc.poll() is None:
        try:
            _server_proc.kill()
        except Exception:
            pass
    if _ollama_proc and _ollama_proc.poll() is None:
        try:
            _ollama_proc.kill()
        except Exception:
            pass

atexit.register(_cleanup)
signal.signal(signal.SIGTERM, lambda *_: (_cleanup(), sys.exit(0)))
signal.signal(signal.SIGINT, lambda *_: (_cleanup(), sys.exit(0)))


def _set_ollama_env():
    os.environ["OLLAMA_HOST"] = "127.0.0.1:11434"
    os.environ["OLLAMA_MODELS"] = OLLAMA_MODELS


def server_ready():
    try:
        with urllib.request.urlopen(f"{URL}/api/health", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def ollama_running():
    try:
        with urllib.request.urlopen(f"{OLLAMA_HOST}/api/tags", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def start_ollama():
    global _ollama_proc
    if ollama_running():
        return
    _set_ollama_env()
    print("[Hermes] Starting Ollama...")
    if not OLLAMA_EXE.exists():
        print(f"[Hermes] Ollama not found at {OLLAMA_EXE}")
        return
    try:
        _ollama_proc = subprocess.Popen(
            [str(OLLAMA_EXE), "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=0x08000000,
            close_fds=False,
        )
    except Exception as e:
        print(f"[Hermes] Could not start Ollama: {e}")
        return

    for _ in range(20):
        time.sleep(0.5)
        if ollama_running():
            print("[Hermes] Ollama started.")
            return
    print("[Hermes] Ollama did not respond.")


def start_server():
    global _server_proc
    exe = sys.executable
    pyw = pathlib.Path(exe).with_name("pythonw.exe")
    if pyw.exists():
        exe = str(pyw)
    _server_proc = subprocess.Popen(
        [exe, str(ROOT / "server.py")],
        cwd=str(ROOT),
        creationflags=0x08000000,
        close_fds=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def open_window():
    global _browser_proc
    for exe in [
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]:
        if pathlib.Path(exe).exists():
            try:
                _browser_proc = subprocess.Popen(
                    [exe, f"--app={URL}/", "--window-size=1400,900"],
                    creationflags=0x08000000,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return True
            except Exception:
                continue
    import webbrowser
    webbrowser.open(URL + "/")
    return False


def main():
    mutex = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    already_running = kernel32.GetLastError() == 183

    if already_running:
        if server_ready():
            open_window()
        sys.exit(0)

    if port_in_use(PORT) and server_ready():
        open_window()
        sys.exit(0)

    start_ollama()

    if not server_ready():
        if port_in_use(PORT):
            print(f"[Hermes] Port {PORT} occupied but server not responding. Waiting...")
            time.sleep(2)
        start_server()

    for _ in range(30):
        if server_ready():
            break
        time.sleep(1)
    else:
        print("[Hermes] Server did not start. Check server.py output.")
        sys.exit(1)

    open_window()

    try:
        while True:
            time.sleep(3)
            if _browser_proc and _browser_proc.poll() is not None:
                break
            if not server_ready():
                break
    except KeyboardInterrupt:
        pass
    finally:
        _cleanup()


if __name__ == "__main__":
    main()
