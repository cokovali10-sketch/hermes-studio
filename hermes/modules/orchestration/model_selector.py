"""Model selector — query available models and select best for task."""
from __future__ import annotations

from hermes.core import CFG, OLLAMA_DIR
from hermes.modules.orchestration.model_router import model_router


class ModelSelector:
    def __init__(self):
        self._ollama_models: list[str] | None = None

    def get_available_models(self) -> list[str]:
        if self._ollama_models is not None:
            return list(self._ollama_models)

        try:
            import subprocess
            ollama_exe = OLLAMA_DIR / "ollama.exe"
            if not ollama_exe.exists():
                return model_router.get_available_models()

            result = subprocess.run(
                [str(ollama_exe), "list"],
                capture_output=True, text=True, timeout=10,
            )
            models = []
            for line in result.stdout.strip().splitlines()[1:]:
                parts = line.split()
                if parts:
                    models.append(parts[0])
            self._ollama_models = models
            return models
        except Exception:
            return model_router.get_available_models()

    def get_model_info(self, model: str) -> dict:
        return model_router.get_model_info(model)

    def select_best_for_task(self, task_type: str) -> str:
        available = self.get_available_models()
        recommended = model_router.select_model(task=task_type)
        if recommended in available:
            return recommended
        fallback = model_router.get_fallback_chain(task_type)
        for m in fallback:
            if m in available:
                return m
        return available[0] if available else CFG.get("models", {}).get("coding", "llama3.1:8b")


model_selector = ModelSelector()
