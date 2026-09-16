"""Direct AirLLM provider with lazy model loading.

AirLLM is optional: importing JARVIS never requires it. The provider loads the
model only on the first generation request and keeps the model instance cached.
"""
from __future__ import annotations

import os
from typing import Optional


class AirLLMProvider:
    name = "Джарвис AirLLM"

    def __init__(self, model: Optional[str] = None, max_length: int = 2048,
                 max_new_tokens: int = 256):
        self.model_name = (model or os.environ.get("JARVIS_AIRLLM_MODEL", "")).strip()
        self.max_length = max(256, int(max_length))
        self.max_new_tokens = max(1, int(max_new_tokens))
        self._model = None
        self._tokenizer = None
        self.system_prompt = (
            "Ты — Джарвис, персональный ИИ-ассистент пользователя. "
            "Отвечай на русском языке, если пользователь не попросил другой язык. "
            "Не выдумывай результаты действий."
        )
        self.history: list[dict] = []

    def _load(self) -> None:
        if self._model is not None:
            return
        if not self.model_name:
            raise RuntimeError(
                "Для AirLLM не задана модель. Укажите JARVIS_AIRLLM_MODEL, "
                "например Qwen/Qwen3-8B."
            )
        try:
            from airllm import AutoModel
        except ImportError as exc:
            raise RuntimeError(
                "AirLLM не установлен. Установите дополнительную зависимость: pip install airllm."
            ) from exc
        try:
            self._model = AutoModel.from_pretrained(self.model_name)
            self._tokenizer = self._model.tokenizer
        except Exception as exc:
            self._model = None
            self._tokenizer = None
            raise RuntimeError(f"Не удалось загрузить модель AirLLM «{self.model_name}»: {exc}") from exc

    def generate(self, prompt: str, tools=None, max_steps: int = 1) -> str:
        del tools, max_steps
        self._load()
        conversation = [
            {"role": "system", "content": self.system_prompt},
            *self.history[-8:],
            {"role": "user", "content": prompt},
        ]
        try:
            if hasattr(self._tokenizer, "apply_chat_template"):
                text = self._tokenizer.apply_chat_template(
                    conversation, tokenize=False, add_generation_prompt=True
                )
            else:
                text = "\n".join(f"{m['role']}: {m['content']}" for m in conversation) + "\nassistant:"
            inputs = self._tokenizer(
                [text], return_tensors="pt", return_attention_mask=False,
                truncation=True, max_length=self.max_length, padding=False,
            )
            input_ids = inputs["input_ids"]
            if hasattr(input_ids, "cuda"):
                input_ids = input_ids.cuda()
            output = self._model.generate(
                input_ids,
                max_new_tokens=self.max_new_tokens,
                use_cache=True,
                return_dict_in_generate=True,
            )
            generated = output.sequences[0][input_ids.shape[-1]:]
            reply = self._tokenizer.decode(generated, skip_special_tokens=True).strip()
        except Exception as exc:
            raise RuntimeError(f"Ошибка генерации AirLLM: {exc}") from exc
        self.history.extend([
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": reply},
        ])
        self.history = self.history[-16:]
        return reply or "Модель AirLLM не вернула текстовый ответ."
