"""Assemble a runnable agent from settings."""
from pathlib import Path
from .config import Settings
from .core import JarvisAgent
from .logging_setup import get as get_log
from .memory import KnowledgeGraph, MemoryStore, SessionMemory, relevant_notes
from .providers.openai_chat import OpenAIChatProvider
from .model_router import RoleRouterProvider
from .reminders import ReminderService
from .tools import apps, audio, clipboard, files, processes, screenshot, system, web, osint, universal, self_modify
from .tools.registry import ToolRegistry
from . import stt, tts
from .skills import NoteStore, calculate, now, wikipedia_search, dictionary_lookup, news_search, youtube_search, youtube_download, google_maps_search, open_website, play_music, location_lookup, todo_add, todo_list, todo_done


def _send_email(to: str, subject: str, body: str) -> str:
    import os, smtplib
    from email.message import EmailMessage
    host=os.environ.get("JARVIS_SMTP_HOST","").strip(); user=os.environ.get("JARVIS_SMTP_USER","").strip(); password=os.environ.get("JARVIS_SMTP_PASSWORD","")
    if not host or not user or not password:
        raise RuntimeError("SMTP не настроен: JARVIS_SMTP_HOST, JARVIS_SMTP_USER, JARVIS_SMTP_PASSWORD")
    port=int(os.environ.get("JARVIS_SMTP_PORT","587")); sender=os.environ.get("JARVIS_SMTP_FROM","").strip() or user
    msg=EmailMessage(); msg["From"]=sender; msg["To"]=to; msg["Subject"]=subject; msg.set_content(body)
    with smtplib.SMTP(host,port,timeout=30) as smtp:
        smtp.starttls(); smtp.login(user,password); smtp.send_message(msg)
    return f"Письмо отправлено: {to}"


def build_agent(settings: Settings | None = None) -> JarvisAgent:
    settings=settings or Settings.from_env(); log=get_log("runtime"); log.info("Старт агента (provider=%s)",settings.provider); memory=MemoryStore(settings.memory_path)
    if settings.provider == "gemini":
        session = SessionMemory(memory)
        history = session.load_history()
        shared_url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        # Settings.from_env() already resolves environment keys. An empty value here
        # must stay empty so a deliberately cleared key cannot be resurrected.
        shared_key = settings.chat_key
        default_model = settings.chat_model or "gemini-3.8-flash"
        timeout = max(5, min(180, int(settings.gemini_timeout)))
        # The role profiles may point to the same configured model. Add known
        # Gemini alternatives so a capacity outage can fail over to a different model.
        fallback_candidates = [
            settings.fast_model, settings.reasoning_model, settings.coding_model, settings.additional_model,
            "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.6-flash",
        ]
        fast = OpenAIChatProvider(url=shared_url, api_key=shared_key, model=settings.fast_model or default_model,
                                  timeout=timeout, history=history, fallback_models=fallback_candidates)
        reasoning = OpenAIChatProvider(url=shared_url, api_key=shared_key, model=settings.reasoning_model or default_model,
                                       timeout=timeout, history=history, fallback_models=fallback_candidates)
        coding = OpenAIChatProvider(url=shared_url, api_key=shared_key, model=settings.coding_model or default_model,
                                    timeout=timeout, history=history, fallback_models=fallback_candidates)
        additional = OpenAIChatProvider(url=shared_url, api_key=shared_key, model=settings.additional_model or default_model,
                                        timeout=timeout, history=history, fallback_models=fallback_candidates)
        providers = {"fast": fast, "reasoning": reasoning, "coding": coding, "additional": additional}
        # Gemini is the only supported cloud provider. Role fallback stays within Gemini.
        provider = RoleRouterProvider(providers, fallback_order=("fast", "reasoning", "coding", "additional"))
    else:
        raise RuntimeError("JARVIS поддерживает только Gemini API Google.")
    reminders=ReminderService(str(Path(settings.memory_path).with_name("jarvis_reminders.json")))
    tools=ToolRegistry()
    tools.register("read_source", self_modify.read_source, description="Прочитать исходный код или конфигурацию внутри проекта JARVIS.", parameters={"path":"относительный путь внутри репозитория"})
    tools.register("write_source", self_modify.write_source, confirm=True, description="Изменить исходный файл проекта с созданием резервной копии. Требует подтверждения.", parameters={"path":"относительный путь внутри репозитория","content":"полное новое содержимое файла"})
    tools.register("run_self_tests", self_modify.run_tests, description="Запустить набор pytest-тестов проекта JARVIS и вернуть результаты.")
    tools.register("git_status", self_modify.git_status, description="Показать состояние Git-репозитория JARVIS.")
    tools.register("rollback_self_change", self_modify.rollback_last_backup, confirm=True, description="Восстановить последний резервный файл самоизменения. Требует подтверждения.")
    tools.register("inspect_file",universal.inspect_file,description="Прочитать и проанализировать локальный файл: TXT, MD, CSV, JSON, XML, Python, PDF, DOCX, XLSX и другие поддерживаемые форматы.",parameters={"path":"путь к файлу или папке"})
    tools.register("inspect_archive",universal.inspect_archive,description="Прочитать содержимое ZIP, TAR, GZ, 7Z или RAR архива.",parameters={"path":"путь к архиву"})
    tools.register("extract_archive",universal.extract_archive,confirm=True,description="Распаковать архив. Требует подтверждения.",parameters={"path":"путь к архиву","destination":"папка назначения (необязательно)"})
    tools.register("find_errors",universal.find_errors,description="Просканировать проект/папку и найти строки ошибок, traceback и типичные ошибки сборки.",parameters={"path":"путь к проекту или файлу"})
    tools.register("project_check",universal.project_check,description="Запустить безопасную диагностику проекта: синтаксис Python, pip check, npm и Flutter analyze/build.",parameters={"path":"путь к проекту"})
    tools.register("app_test_environment",universal.app_test_environment,description="Проверить наличие JMeter, ADB, Flutter, Gradle и Xcode для тестирования приложений.")
    tools.register("android_app_diagnostics",universal.android_app_diagnostics,description="Проверить Android-устройство через ADB: модель, Android, память, батарею и критические ошибки logcat.",parameters={"serial":"серийный номер устройства, необязательно","package":"пакет приложения для фильтра logcat, необязательно"})
    tools.register("jmeter_load_test",universal.jmeter_load_test,confirm=True,description="Запустить JMeter-нагрузочный тест из JMX. Требует подтверждения.",parameters={"jmx_path":"путь к JMX","result_file":"путь к JTL, необязательно"})
    tools.register("loaderio_status",universal.loaderio_status,confirm=True,description="Проверить или запустить тесты Loader.io через API. Для run требуется подтверждение.",parameters={"action":"apps, tests, results или run","test_id":"ID теста для results/run"})
    tools.register("cloudflare_analytics",universal.cloudflare_analytics,description="Получить данные Cloudflare Analytics GraphQL по запросу пользователя.",parameters={"query":"GraphQL query, необязательно"})
    tools.register("manageengine_monitor",universal.manageengine_monitor,description="Получить данные из ManageEngine Applications Manager REST API.",parameters={"path":"путь API без базового URL"})
    tools.register("edit_file",universal.edit_file,confirm=True,description="Изменить UTF-8 текстовый файл точной заменой. Создаёт резервную копию и требует подтверждения.",parameters={"path":"путь к файлу","old":"точный старый текст","new":"новый текст","count":"сколько замен, по умолчанию 1"})
    tools.register("run_command",universal.run_command,confirm=True,description="Выполнить команду Windows для диагностики, сборки или исправления проекта. Требует подтверждения.",parameters={"command":"команда Windows"})
    tools.register("shutdown",universal.shutdown,confirm=True,description="Выключить, перезагрузить или перевести Windows в сон. Требует подтверждения.",parameters={"action":"shutdown, restart или sleep"})
    tools.register("open_folder",apps.open_path,description="Открыть папку или файл в Проводнике Windows.",parameters={"path":"путь к папке или файлу"})
    tools.register("status",system.status,description="Показать статус системы (ОС, CPU, RAM, диски). Не принимает аргументов.")
    tools.register("search",files.search,description="Найти файлы по маске в папке.",parameters={"pattern":"маска, например *.txt","folder":"папка для поиска"})
    tools.register("delete",files.delete,confirm=True,description="Удалить файл. ОПАСНО: требует подтверждения.",parameters={"path":"путь к файлу"})
    tools.register("launch",apps.launch,confirm=True,description="Запустить приложение или программу с подтверждением.",parameters={"name":"имя приложения или путь"})
    tools.register("open_path",apps.open_path,description="Открыть локальный файл или папку в Windows Explorer.",parameters={"path":"полный локальный путь"})
    tools.register("open_url",apps.open_url,description="Открыть веб-страницу в браузере.",parameters={"url":"полный HTTP(S) адрес"})
    tools.register("volume",audio.get_volume,description="Показать текущую громкость.")
    tools.register("set_volume",audio.set_volume,description="Установить громкость (0-100).",parameters={"level":"уровень 0-100"})
    tools.register("change_volume",audio.change_volume,description="Увеличить или уменьшить громкость относительно текущей. Для «сделай громче» используй +10, для «тише» используй -10.",parameters={"delta":"изменение в процентах, например +10 или -10"})
    tools.register("screenshot",screenshot.capture,description="Сделать скриншот и вернуть путь к файлу.")
    tools.register("ps",lambda *f:"\n".join(f"{p['pid']:>7}  {p['name']}" for p in processes.list_processes(*f)) or "Не найдено",description="Список запущенных процессов.",parameters={"name":"фильтр по имени (необязательный)"})
    tools.register("kill",processes.kill_process,confirm=True,description="Завершить процесс. ОПАСНО: требует подтверждения.",parameters={"pid":"PID процесса"})
    tools.register("clip_get",lambda:clipboard.get(),description="Прочитать буфер обмена.")
    tools.register("clip_set",clipboard.set,description="Записать текст в буфер обмена.",parameters={"text":"текст"})
    tools.register("remind",reminders.add,description="Поставить напоминание.",parameters={"when":"время","text":"текст напоминания"})
    tools.register("reminders",reminders.list_pending,description="Показать активные напоминания.")
    tools.register("say",lambda text:tts.speak_and_play(text) and f"Озвучено: {text[:100]}",description="Озвучить текст голосом (TTS).",parameters={"text":"текст для озвучки"})
    tools.register("web_search",web.web_search,description="Найти информацию в интернете (Google).",parameters={"query":"поисковый запрос"})
    tools.register("weather",web.weather,description="Текущая погода в городе.",parameters={"city":"название города"})
    tools.register("wikipedia",wikipedia_search,description="Поиск по Wikipedia.",parameters={"query":"поисковый запрос"})
    tools.register("dictionary",dictionary_lookup,description="Словарь с автоматическим поиском определения.",parameters={"word":"слово"})
    tools.register("news",news_search,description="Открыть поиск актуальных новостей.",parameters={"query":"тема новостей"})
    tools.register("youtube_search",youtube_search,description="Поиск видео на YouTube.",parameters={"query":"что искать"})
    tools.register("youtube_download",youtube_download,confirm=True,description="Скачать видео по URL через yt-dlp. Требует подтверждения.",parameters={"url":"URL видео","output_dir":"папка назначения, необязательно"})
    tools.register("google_maps",google_maps_search,description="Поиск места в Google Maps.",parameters={"location":"место"})
    tools.register("open_website",open_website,description="Открыть сайт в браузере.",parameters={"url":"адрес сайта"})
    tools.register("play_music",play_music,description="Открыть локальный музыкальный файл.",parameters={"path":"путь к аудиофайлу"})
    tools.register("location",location_lookup,description="Определить примерное местоположение по публичному IP; GPS устройства не используется.")
    tools.register("todo_add",todo_add,description="Добавить задачу в список дел.",parameters={"text":"текст задачи","path":"файл todo.json, необязательно"})
    tools.register("todo_list",todo_list,description="Показать активные задачи.",parameters={"path":"файл todo.json, необязательно"})
    tools.register("todo_done",todo_done,description="Отметить задачу выполненной.",parameters={"task_id":"номер задачи","path":"файл todo.json, необязательно"})
    tools.register("transcribe",stt.transcribe,description="Распознать речь из wav-файла.",parameters={"audio_path":"путь к wav-файлу"})
    tools.register("osint",osint.investigate,description="OSINT: исследовать домен, URL, IP, email или username.",parameters={"target":"домен, URL, IP, email или username"})
    tools.register("osint_domain",osint.domain_intel,description="OSINT домена: DNS/IP, RDAP, NS и TLS.",parameters={"value":"домен"})
    tools.register("osint_ip",osint.ip_intel,description="OSINT IP: география, ASN, организация и провайдер.",parameters={"value":"IPv4 или IPv6"})
    tools.register("osint_url",osint.url_intel,description="OSINT URL: HTTP, заголовки, title, ссылки и SHA-256.",parameters={"value":"HTTP(S) URL"})
    tools.register("osint_email",osint.email_intel,description="Email OSINT и анализ домена.",parameters={"value":"email"})
    tools.register("osint_username",osint.username_search,description="Проверить публичные профили по username.",parameters={"username":"username"})
    tools.register("image_metadata",osint.image_metadata,description="Извлечь EXIF/метаданные изображения и SHA-256.",parameters={"path":"путь к изображению"})
    tools.register("email_send",_send_email,confirm=True,description="Отправить email через настроенный SMTP. Требует подтверждения.",parameters={"to":"получатель","subject":"тема","body":"текст"})
    notes=NoteStore(str(Path(settings.memory_path).with_name("jarvis_notes.json")))
    tools.register("remember",notes.add,description="Сохранить факт/заметку.",parameters={"text":"что запомнить","tags":"теги через пробел"})
    tools.register("recall",notes.recall,description="Найти сохранённые заметки.",parameters={"query":"ключевые слова"})
    tools.register("forget",notes.forget,confirm=True,description="Удалить заметку по номеру. ОПАСНО: требует подтверждения.",parameters={"note_id":"номер заметки"})
    kg_path=settings.kg_path or str(Path(settings.memory_path).with_name("jarvis_kg.json")); kg=KnowledgeGraph(kg_path)
    tools.register("kg_add",kg.add_fact,description="Добавить факт/связь в граф знаний.",parameters={"source":"субъект","relation":"отношение","target":"объект"})
    tools.register("kg_query",kg.query,description="Найти информацию в графе знаний.",parameters={"query":"поисковый запрос"})
    tools.register("kg_relate",kg.find_path,description="Найти цепочку связей.",parameters={"source":"первая сущность","target":"вторая сущность"})
    tools.register("kg_forget",kg.delete,confirm=True,description="Удалить факт или сущность. ОПАСНО: требует подтверждения.",parameters={"target":"сущность или связь"})
    tools.register("kg_show",lambda focus="":kg.visualize(focus),description="Показать граф знаний.",parameters={"focus":"сущность (необязательно)"})
    tools.register("calc",calculate,description="Вычислить арифметическое выражение.",parameters={"expression":"выражение"}); tools.register("now",lambda:now(),description="Текущая дата и время.")
    agent=JarvisAgent(provider,tools=tools,memory=memory,reminders=reminders)
    if session is not None:
        def _sync_memory(user:str,assistant:str):
            session.append(user,assistant); data=memory.load(); data["chat_history"]=provider.history; memory.save(data)
        agent.on_exchange=_sync_memory; agent.session=session; base_prompt=provider.system_prompt
        def _rag_hook(text:str):
            block=relevant_notes(notes,session.last_user_text(2)+[text]); provider.system_prompt=(base_prompt+"\n\n"+block) if block else base_prompt
        agent.context_hook=_rag_hook
    return agent
