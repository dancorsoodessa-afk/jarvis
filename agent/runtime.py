"""Assemble a runnable agent from settings."""

import json
import os
import urllib.request
from pathlib import Path

from .config import Settings
from .core import JarvisAgent
from .memory.store import MemoryStore
from .providers.cloud import CloudProvider
from .providers.local_vulkan import LocalVulkanProvider
from .reminders import ReminderService
from .tools import apps, audio, clipboard, files, processes, screenshot, system
from .tools.registry import ToolRegistry


def _cloud_generate(prompt: str) -> str:
    url = os.environ.get("JARVIS_CLOUD_URL")
    if not url:
        raise RuntimeError(
            "Cloud provider not configured: set JARVIS_CLOUD_URL "
            "(or run with JARVIS_LOCAL=1 for local inference)"
        )
    req = urllib.request.Request(
        url,
        data=json.dumps({"prompt": prompt}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))["text"]


def build_agent(settings: Settings | None = None) -> JarvisAgent:
    settings = settings or Settings.from_env()
    if settings.use_local:
        provider = LocalVulkanProvider(
            settings.llama_cli, settings.model,
            ctx=settings.ctx, threads=settings.threads,
        )
    else:
        provider = CloudProvider(_cloud_generate)

    reminders = ReminderService(
        str(Path(settings.memory_path).with_name("jarvis_reminders.json")))

    tools = ToolRegistry()
    tools.register("status", system.status)
    tools.register("search", files.search)
    tools.register("delete", files.delete, confirm=True)
    tools.register("launch", apps.launch, confirm=True)
    tools.register("volume", audio.get_volume)
    tools.register("set_volume", audio.set_volume)
    tools.register("screenshot", screenshot.capture)
    tools.register("ps", lambda *f: "\n".join(
        f"{p['pid']:>7}  {p['name']}" for p in processes.list_processes(*f)) or "Не найдено")
    tools.register("kill", processes.kill_process, confirm=True)
    tools.register("clip_get", lambda: clipboard.get())
    tools.register("clip_set", clipboard.set)
    tools.register("remind", reminders.add)
    tools.register("reminders", reminders.list_pending)

    return JarvisAgent(provider, tools=tools,
                       memory=MemoryStore(settings.memory_path),
                       reminders=reminders)
