"""Local image understanding service for JARVIS.

Uses Ollama's local multimodal HTTP API. The model name is configuration, not
hard-coded, so an installed vision model can be selected by the user.
"""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path


class VisionService:
    def __init__(self, endpoint: str | None = None, model: str | None = None, timeout: int = 90):
        self.endpoint = endpoint or os.environ.get("JARVIS_VISION_URL", "http://127.0.0.1:11434/api/chat")
        self.model = model or os.environ.get("JARVIS_VISION_MODEL", "")
        self.timeout = timeout

    def analyze(self, image_path: str, prompt: str = "Опиши изображение подробно и по-русски.") -> str:
        if not self.model:
            raise RuntimeError("Модель зрения не настроена: задайте JARVIS_VISION_MODEL")
        path = Path(image_path).expanduser()
        if not path.is_file():
            raise FileNotFoundError(path)
        image = base64.b64encode(path.read_bytes()).decode("ascii")
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt, "images": [image]}],
            "stream": False,
        }
        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:400]
            raise RuntimeError(f"Локальное зрение HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Локальное зрение недоступно: {exc.reason}") from exc
        try:
            return str(body["message"]["content"])
        except (KeyError, TypeError) as exc:
            raise RuntimeError(f"Неожиданный ответ локального зрения: {body!r}") from exc
