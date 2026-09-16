"""Preflight checks that never start an AI model or execute user commands."""
from __future__ import annotations

import importlib.util
import os
import platform
import sys
from pathlib import Path


def run(provider: str = "") -> tuple[bool, list[str]]:
    provider = (provider or os.environ.get("JARVIS_PROVIDER", "openai-compatible")).strip().lower()
    lines: list[str] = []
    ok = True

    lines.append(f"Python: {platform.python_version()} [{platform.system()} {platform.machine()}]")
    if sys.version_info < (3, 10) or sys.version_info >= (3, 15):
        ok = False
        lines.append("ОШИБКА: требуется Python >=3.10 и <3.15")

    memory = Path(os.environ.get("JARVIS_MEMORY", "jarvis_memory.json")).expanduser()
    try:
        memory.parent.mkdir(parents=True, exist_ok=True)
        lines.append(f"Память: OK ({memory})")
    except OSError as exc:
        ok = False
        lines.append(f"ОШИБКА памяти: {exc}")

    if provider == "airllm":
        if importlib.util.find_spec("airllm") is None:
            ok = False
            lines.append("ОШИБКА: AirLLM не установлен; выполните poetry install --extras airllm")
        else:
            lines.append("AirLLM: пакет найден")
        model = os.environ.get("JARVIS_AIRLLM_MODEL", "").strip()
        if not model:
            ok = False
            lines.append("ОШИБКА: JARVIS_AIRLLM_MODEL не задан")
        else:
            lines.append(f"AirLLM model: {model}")
    elif provider == "local-vulkan":
        model = Path(os.environ.get("JARVIS_MODEL", "model.gguf")).expanduser()
        if not model.is_file():
            ok = False
            lines.append(f"ОШИБКА: GGUF модель не найдена: {model}")
        else:
            lines.append(f"GGUF: OK ({model})")
    elif provider == "openai-compatible":
        lines.append("OpenAI-compatible: endpoint проверяется при первом AI-запросе")
    else:
        ok = False
        lines.append(f"ОШИБКА: неизвестный провайдер: {provider}")

    try:
        import pytest  # noqa: F401
        lines.append("Pytest: установлен")
    except ImportError:
        lines.append("Предупреждение: pytest не установлен; тесты локально не запустить")

    lines.append("Итог: ГОТОВ" if ok else "Итог: ЕСТЬ ОШИБКИ")
    return ok, lines
