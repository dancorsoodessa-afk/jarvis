"""Assemble a runnable agent from settings."""

import os
from pathlib import Path

from .config import Settings
from .core import JarvisAgent
from .logging_setup import get as get_log
from .memory import KnowledgeGraph, MemoryStore, SessionMemory, relevant_notes
from .providers.cloud import OpenAIChatProvider
from .providers.local_vulkan import LocalVulkanProvider
from .reminders import ReminderService
from .tools import apps, audio, clipboard, files, processes, screenshot, system, web
from .tools.registry import ToolRegistry
from . import stt, tts
from .skills import NoteStore, calculate, now


def build_agent(settings: Settings | None = None) -> JarvisAgent:
    settings = settings or Settings.from_env()
    log = get_log("runtime")
    log.info("Старт агента (local=%s)", settings.use_local)
    memory = MemoryStore(settings.memory_path)

    if settings.use_local:
        provider = LocalVulkanProvider(
            settings.llama_cli, settings.model,
            ctx=settings.ctx, threads=settings.threads,
        )
    else:
        # Restore dialogue history from memory so the model keeps context
        # across restarts.
        provider = OpenAIChatProvider(history=SessionMemory(memory).load_history())

    reminders = ReminderService(
        str(Path(settings.memory_path).with_name("jarvis_reminders.json")))

    tools = ToolRegistry()
    tools.register("status", system.status,
                   description="Показать статус системы (ОС, CPU, RAM, диски). Не принимает аргументов.")
    tools.register("search", files.search,
                   description="Найти файлы по маске в папке.",
                   parameters={"pattern": "маска, например *.txt",
                               "folder": "папка для поиска"})
    tools.register("delete", files.delete, confirm=True,
                   description="Удалить файл. ОПАСНО: требует подтверждения.",
                   parameters={"path": "путь к файлу"})
    tools.register("launch", apps.launch, confirm=True,
                   description="Запустить приложение. Требует подтверждения.",
                   parameters={"name": "имя приложения или путь"})
    tools.register("open_path", apps.open_path,
                   description="Открыть локальный файл или папку в Windows Explorer. Используй для команд вроде «открой диск C», «открой C:\\», «открой папку загрузки» при наличии точного пути.",
                   parameters={"path": "полный локальный путь, например C:\\ или C:\\Users\\User\\Downloads"})
    tools.register("open_url", apps.open_url,
                   description="Открыть веб-страницу в браузере. Используй для команд вроде «открой YouTube», «открой сайт Google» и других HTTP(S) адресов.",
                   parameters={"url": "полный адрес страницы, начиная с http:// или https://"})
    tools.register("volume", audio.get_volume,
                   description="Показать текущую громкость.")
    tools.register("set_volume", audio.set_volume,
                   description="Установить громкость (0-100).",
                   parameters={"level": "уровень громкости 0-100"})
    tools.register("screenshot", screenshot.capture,
                   description="Сделать скриншот и вернуть путь к файлу.")
    tools.register("ps", lambda *f: "\n".join(
        f"{p['pid']:>7}  {p['name']}" for p in processes.list_processes(*f)) or "Не найдено",
                   description="Список запущенных процессов, можно фильтровать по имени.",
                   parameters={"name": "фильтр по имени (необязательный)"})
    tools.register("kill", processes.kill_process, confirm=True,
                   description="Завершить процесс. ОПАСНО: требует подтверждения.",
                   parameters={"pid": "PID процесса"})
    tools.register("clip_get", lambda: clipboard.get(),
                   description="Прочитать буфер обмена.")
    tools.register("clip_set", clipboard.set,
                   description="Записать текст в буфер обмена.",
                   parameters={"text": "текст для буфера"})
    tools.register("remind", reminders.add,
                   description="Поставить напоминание.",
                   parameters={"when": "время, например 21:30",
                               "text": "текст напоминания"})
    tools.register("reminders", reminders.list_pending,
                   description="Показать активные напоминания.")
    tools.register("say", lambda text: tts.speak_and_play(text) and f"Озвучено: {text[:100]}",
                   description="Озвучить текст голосом (TTS).",
                   parameters={"text": "текст для озвучки"})
    tools.register("web_search", web.web_search,
                   description="Найти информацию в интернете (DuckDuckGo).",
                   parameters={"query": "поисковый запрос"})
    tools.register("weather", web.weather,
                   description="Текущая погода в городе.",
                   parameters={"city": "название города"})
    tools.register("transcribe", stt.transcribe,
                   description="Распознать речь из wav-файла и вернуть текст (STT).",
                   parameters={"audio_path": "путь к wav-файлу"})

    notes = NoteStore(str(Path(settings.memory_path).with_name("jarvis_notes.json")))
    tools.register("remember", notes.add,
                   description="Сохранить факт/заметку в долговременную память о пользователе.",
                   parameters={"text": "что запомнить",
                               "tags": "теги через пробел (необязательно)"})
    tools.register("recall", notes.recall,
                   description="Найти сохранённые заметки/факты по ключевым словам.",
                   parameters={"query": "ключевые слова (необязательно)"})
    tools.register("forget", notes.forget,
                   description="Удалить заметку по номеру.",
                   parameters={"note_id": "номер заметки"})

    kg_path = settings.kg_path or str(Path(settings.memory_path).with_name("jarvis_kg.json"))
    kg = KnowledgeGraph(kg_path)
    tools.register("kg_add", kg.add_fact,
                   description="Добавить факт/связь в граф знаний: субъект, отношение, объект (например: 'Алексей', 'разработчик', 'Jarvis').",
                   parameters={"source": "исходная сущность / субъект",
                               "relation": "тип связи / отношение",
                               "target": "целевая сущность / объект"})
    tools.register("kg_query", kg.query,
                   description="Найти информацию, сущности и связи в графе знаний по ключевому слову или имени.",
                   parameters={"query": "имя сущности или поисковый запрос (необязательно)"})
    tools.register("kg_relate", kg.find_path,
                   description="Найти цепочку связей между двумя сущностями в графе знаний.",
                   parameters={"source": "первая сущность",
                               "target": "вторая сущность"})
    tools.register("kg_forget", kg.delete,
                   description="Удалить факт или сущность из графа знаний.",
                   parameters={"target": "имя сущности или формат 'субъект; отношение; объект'"})
    tools.register("kg_show", lambda focus="": kg.visualize(focus),
                   description="Показать граф знаний в виде схемы (Mermaid) и сводки (можно указать конкретную сущность).",
                   parameters={"focus": "имя сущности для подграфа (необязательно)"})

    tools.register("calc", calculate,
                   description="Вычислить арифметическое выражение (+ - * / ** %).",
                   parameters={"expression": "выражение, например (2+3)*7"})
    tools.register("now", lambda: now(),
                   description="Текущая дата и время.")

    agent = JarvisAgent(provider, tools=tools,
                        memory=memory,
                        reminders=reminders)
    if not settings.use_local:
        session = SessionMemory(memory)

        def _sync_memory(user: str, assistant: str):
            session.append(user, assistant)
            data = memory.load()
            data["chat_history"] = provider.history
            memory.save(data)
        agent.on_exchange = _sync_memory
        agent.session = session  # exposed for IPC "clear_memory"

        # RAG: before each turn, inject notes relevant to the recent dialogue
        # into the model's system prompt so long-term facts are seen without
        # explicit /recall calls.
        base_prompt = provider.system_prompt

        def _rag_hook(text: str):
            block = relevant_notes(notes, session.last_user_text(2) + [text])
            provider.system_prompt = (
                base_prompt + "\n\n" + block) if block else base_prompt
        agent.context_hook = _rag_hook
    return agent
