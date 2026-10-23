"""Model router — select the best model for a given task based on scoring matrix."""
from __future__ import annotations

from hermes.core import CFG
from hermes.modules.self_improve.perf_profiler import perf_profiler
# --- константы вынесены FORGE refactor ---
CONST_6 = 6
CONST_7 = 7
CONST_8 = 8
CONST_9 = 9



TASK_MODEL_SCORES = {
    "coding": {
        "codellama:13b": CONST_9, "codellama:7b": CONST_7, "deepseek-coder:6.7b": CONST_8,
        "qwen2.5-coder:7b": CONST_8, "llama3.1:8b": CONST_6, "mistral:7b": 5,
    },
    "reasoning": {
        "llama3.1:8b": CONST_8, "mistral:7b": CONST_7, "qwen2.5:7b": CONST_8,
        "deepseek-r1:8b": CONST_9, "gemma2:9b": CONST_7, "phi3:14b": CONST_8,
    },
    "analysis": {
        "llama3.1:8b": CONST_8, "qwen2.5:7b": CONST_8, "mistral:7b": CONST_7,
        "deepseek-r1:8b": CONST_9, "phi3:14b": CONST_8,
    },
    "creative": {
        "llama3.1:8b": CONST_7, "mistral:7b": CONST_7, "qwen2.5:7b": CONST_7,
        "gemma2:9b": CONST_7, "phi3:14b": CONST_7,
    },
    "simple": {
        "qwen2.5:7b": CONST_8, "llama3.1:8b": CONST_7, "mistral:7b": CONST_7,
        "phi3:14b": CONST_6, "gemma2:9b": CONST_7,
    },
    "vision": {
        "llava:1.6-mistral": CONST_9, "bakllava:7b": CONST_7,
    },
    "fast": {
        "qwen2.5:7b": CONST_8, "mistral:7b": CONST_8, "phi3:14b": CONST_7,
        "llama3.1:8b": CONST_7, "gemma2:9b": CONST_7,
    },
}


class ModelRouter:
    def __init__(self):
        self._default_model = CFG.get("models", {}).get("coding", "llama3.1:8b")

    def select_model(self, task: str = "", context: str = "") -> str:
        task_lower = task.lower() if task else ""
        context_lower = context.lower() if context else ""
        combined = f"{task_lower} {context_lower}"

        task_type = self._classify_task(combined)

        historical = perf_profiler.get_recommendation(task_type)
        if historical:
            return historical

        scores = TASK_MODEL_SCORES.get(task_type, {})
        if scores:
            best = max(scores, key=lambda m: scores[m])
            return best

        return self._default_model

    def _classify_task(self, text: str) -> str:
        coding_keywords = ["code", "function", "class", "implement", "debug", "refactor", "write", "fix", "bug", "compile"]
        reasoning_keywords = ["explain", "why", "how", "analyze", "reason", "compare", "evaluate", "think"]
        vision_keywords = ["image", "screenshot", "visual", "see", "look", "picture", "ui", "layout"]
        creative_keywords = ["create", "write", "story", "generate", "design", "brainstorm"]
        simple_keywords = ["list", "show", "what", "where", "when", "is there"]

        if any(k in text for k in vision_keywords):
            return "vision"
        if any(k in text for k in coding_keywords):
            return "coding"
        if any(k in text for k in reasoning_keywords):
            return "reasoning"
        if any(k in text for k in creative_keywords):
            return "creative"
        if any(k in text for k in simple_keywords):
            return "simple"
        return "reasoning"

    def get_fallback_chain(self, task: str = "") -> list[str]:
        primary = self.select_model(task)
        all_models = set()
        for scores in TASK_MODEL_SCORES.values():
            all_models.update(scores.keys())
        others = [m for m in all_models if m != primary]
        others.sort(key=lambda m: self._model_rank(m), reverse=True)
        return [primary] + others[:3]

    def _model_rank(self, model: str) -> int:
        for task_scores in TASK_MODEL_SCORES.values():
            if model in task_scores:
                return task_scores[model]
        return 0

    def get_available_models(self) -> list[str]:
        models = set()
        for scores in TASK_MODEL_SCORES.values():
            models.update(scores.keys())
        return sorted(models)

    def get_model_info(self, model: str) -> dict:
        strengths = []
        for task_type, scores in TASK_MODEL_SCORES.items():
            if model in scores and scores[model] >= CONST_7:
                strengths.append(task_type)
        return {
            "model": model,
            "strengths": strengths,
            "max_score": max((scores.get(model, 0) for scores in TASK_MODEL_SCORES.values()), default=0),
        }


model_router = ModelRouter()
