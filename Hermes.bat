@echo off
REM Hermes Studio - One click = one window
set OLLAMA_HOST=127.0.0.1:11434
set OLLAMA_MODELS=D:\PortfolioProjects\Hermes\.ollama\models
start "" /min pythonw.exe "D:\PortfolioProjects\Hermes\launch.py"
