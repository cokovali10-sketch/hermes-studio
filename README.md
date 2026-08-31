<div align="center">

# ◆ Hermes Studio

### Fully Offline AI Desktop Assistant

**No cloud. No API keys. No subscription. Just your machine.**

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Ollama](https://img.shields.io/badge/Ollama-Local%20Models-000?style=flat-square&logo=ollama&logoColor=white)](https://ollama.com)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078D4?style=flat-square&logo=windows&logoColor=white)]()

<br/>

![Hermes Studio](screenshots/main.png)

</div>

---

## What is this?

Hermes Studio is a local AI assistant that runs **entirely on your machine**. Two lightweight models handle everything:

| Model | Purpose | Size |
|-------|---------|------|
| **deepseek-r1:1.5b** | Reasoning, analysis, conversation | ~1.1 GB |
| **qwen2.5-coder:1.5b** | Code generation, HTML/CSS/JS | ~986 MB |

A **Smart Router** automatically detects what you're asking and sends it to the right model. Ask a question → deepseek-r1 answers. Ask for code → qwen2.5-coder writes it.

**Total size: ~2 GB. Zero internet required after setup.**

---

## Features

- **Smart Router** — automatic prompt classification (reasoning vs coding)
- **Streaming responses** — text appears token by token
- **File upload** — attach images for vision analysis
- **Voice output** — text-to-speech in Russian
- **Agent Log** — real-time event stream (SSE)
- **100% offline** — works without internet, no data leaves your PC
- **D: drive storage** — models stored on D:, not filling C:
- **One-click launch** — double-click `Hermes.bat` and done
- **Auto-cleanup** — Ollama + server stop when you close the window

---

## Quick Start

### 1. Install

```bash
git clone https://github.com/cokovali10-sketch/hermes-studio.git
cd hermes-studio
pip install -r requirements.txt
```

### 2. Download models

Models auto-download on first run, or manually:

```bash
ollama pull deepseek-r1:1.5b
ollama pull qwen2.5-coder:1.5b
```

### 3. Launch

```bash
# Option A: double-click
Hermes.bat

# Option B: terminal
python launch.py
```

Browser opens automatically → **http://127.0.0.1:8765**

---

## Architecture

```
┌─────────────────────────────────────────────┐
│                   Browser                    │
│            (Edge / Chrome app)               │
└──────────────────┬──────────────────────────┘
                   │ HTTP
┌──────────────────▼──────────────────────────┐
│              server.py (:8765)               │
│  ┌─────────────┐  ┌──────────────────────┐  │
│  │ Smart Router │  │     Event Bus (SSE)  │  │
│  └──────┬──────┘  └──────────────────────┘  │
│         │                                    │
└─────────┼────────────────────────────────────┘
          │ HTTP
┌─────────▼────────────────────────────────────┐
│           Ollama (:11434)                    │
│  ┌──────────────┐  ┌─────────────────────┐  │
│  │ deepseek-r1  │  │   qwen2.5-coder     │  │
│  │  (reasoning) │  │     (coding)         │  │
│  └──────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────┘
```

**How routing works:**

```python
"Напиши HTML кнопку"  → qwen2.5-coder (code keywords detected)
"Объясни квантовые вычисления" → deepseek-r1 (general question)
"Напиши React компонент" → qwen2.5-coder (code keywords detected)
"Кто ты?" → deepseek-r1 (general question)
```

---

## Project Structure

```
hermes-studio/
├── launch.py          # Single-instance launcher
├── server.py          # Backend (aiohttp + smart router)
├── setup_models.py    # Model downloader
├── config.json        # Configuration
├── requirements.txt   # Python dependencies
├── Hermes.bat         # One-click launcher
├── frontend/
│   └── index.html     # UI (vanilla HTML/CSS/JS)
└── screenshots/
    └── main.png       # App screenshot
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | HTML5 + CSS3 + Vanilla JS |
| Backend | Python 3.10+ / aiohttp |
| AI Engine | Ollama (local inference) |
| Models | DeepSeek-R1 1.5B, Qwen2.5-Coder 1.5B |
| Streaming | Server-Sent Events (SSE) |
| Storage | D: drive (models + uploads) |

---

## System Requirements

- **OS:** Windows 10/11
- **RAM:** 8 GB minimum (16 GB recommended)
- **Disk:** 3 GB free (2 GB models + 1 GB app)
- **GPU:** Optional (CPU inference works fine for 1.5B models)

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Frontend UI |
| `GET` | `/api/health` | Health check |
| `GET` | `/api/models` | Installed models status |
| `POST` | `/api/chat` | Chat (`?stream=1` for SSE) |
| `POST` | `/api/upload` | File upload |
| `GET` | `/api/events` | SSE event stream |

---

## Configuration

Edit `config.json`:

```json
{
  "models": {
    "reasoning": "deepseek-r1:1.5b",
    "coding": "qwen2.5-coder:1.5b"
  },
  "server": {
    "port": 8765
  },
  "ollama": {
    "host": "http://127.0.0.1:11434",
    "auto_start": true
  }
}
```

---

## License

MIT — use it however you want.

---

<div align="center">

**Built with care. Runs on your machine. Your data stays yours.**

</div>
