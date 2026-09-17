"""Tool assembly kept outside the runtime orchestrator."""
from pathlib import Path
import os, smtplib
from email.message import EmailMessage
from .memory import KnowledgeGraph
from .reminders import ReminderService
from .skills import NoteStore, calculate, now
from .tools import apps, audio, clipboard, files, processes, screenshot, system, web, osint
from .tools.registry import ToolRegistry
from . import stt, tts

def _send_email(to: str, subject: str, body: str) -> str:
    host=os.environ.get("JARVIS_SMTP_HOST","").strip(); user=os.environ.get("JARVIS_SMTP_USER","").strip(); password=os.environ.get("JARVIS_SMTP_PASSWORD","")
    if not host or not user or not password: raise RuntimeError("SMTP не настроен: JARVIS_SMTP_HOST, JARVIS_SMTP_USER, JARVIS_SMTP_PASSWORD")
    msg=EmailMessage(); msg["From"]=os.environ.get("JARVIS_SMTP_FROM",user).strip(); msg["To"]=to; msg["Subject"]=subject; msg.set_content(body)
    with smtplib.SMTP(host,int(os.environ.get("JARVIS_SMTP_PORT","587")),timeout=30) as smtp:
        smtp.starttls(); smtp.login(user,password); smtp.send_message(msg)
    return f"Письмо отправлено: {to}"

def build_tools(settings):
    reminders=ReminderService(str(Path(settings.memory_path).with_name("jarvis_reminders.json")))
    tools=ToolRegistry()
    add=tools.register
    add("status",system.status,description="Показать статус системы (ОС, CPU, RAM, диски). Не принимает аргументов.")
    add("search",files.search,description="Найти файлы по маске в папке.",parameters={"pattern":"маска, например *.txt","folder":"папка для поиска"})
    add("delete",files.delete,confirm=True,description="Удалить файл. ОПАСНО: требует подтверждения.",parameters={"path":"путь к файлу"})
    add("launch",apps.launch,confirm=True,description="Запустить приложение. Требует подтверждения.",parameters={"name":"имя приложения или путь"})
    add("open_path",apps.open_path,description="Открыть локальный файл или папку в Windows Explorer.",parameters={"path":"полный локальный путь"})
    add("open_url",apps.open_url,description="Открыть веб-страницу в браузере.",parameters={"url":"полный HTTP(S) адрес"})
    add("volume",audio.get_volume,description="Показать текущую громкость.")
    add("set_volume",audio.set_volume,description="Установить громкость (0-100).",parameters={"level":"уровень 0-100"})
    add("screenshot",screenshot.capture,description="Сделать скриншот и вернуть путь к файлу.")
    add("ps",lambda *f:"\n".join(f"{p['pid']:>7}  {p['name']}" for p in processes.list_processes(*f)) or "Не найдено",description="Список запущенных процессов.",parameters={"name":"фильтр по имени (необязательный)"})
    add("kill",processes.kill_process,confirm=True,description="Завершить процесс. ОПАСНО: требует подтверждения.",parameters={"pid":"PID процесса"})
    add("clip_get",clipboard.get,description="Прочитать буфер обмена.")
    add("clip_set",clipboard.set,description="Записать текст в буфер обмена.",parameters={"text":"текст"})
    add("remind",reminders.add,description="Поставить напоминание.",parameters={"when":"время","text":"текст напоминания"})
    add("reminders",reminders.list_pending,description="Показать активные напоминания.")
    add("say",lambda text:tts.speak_and_play(text) and f"Озвучено: {text[:100]}",description="Озвучить текст голосом (TTS).",parameters={"text":"текст для озвучки"})
    add("web_search",web.web_search,description="Найти информацию в интернете (Google).",parameters={"query":"поисковый запрос"})
    add("weather",web.weather,description="Текущая погода в городе.",parameters={"city":"название города"})
    add("transcribe",stt.transcribe,description="Распознать речь из wav-файла.",parameters={"audio_path":"путь к wav-файлу"})
    add("osint",osint.investigate,description="OSINT: исследовать домен, URL, IP, email или username.",parameters={"target":"домен, URL, IP, email или username"})
    add("osint_domain",osint.domain_intel,description="OSINT домена: DNS/IP, RDAP, NS и TLS.",parameters={"value":"домен"})
    add("osint_ip",osint.ip_intel,description="OSINT IP: география, ASN, организация и провайдер.",parameters={"value":"IPv4 или IPv6"})
    add("osint_url",osint.url_intel,description="OSINT URL: HTTP, заголовки, title, ссылки и SHA-256.",parameters={"value":"HTTP(S) URL"})
    add("osint_email",osint.email_intel,description="Email OSINT и анализ домена.",parameters={"value":"email"})
    add("osint_username",osint.username_search,description="Проверить публичные профили по username.",parameters={"username":"username"})
    add("image_metadata",osint.image_metadata,description="Извлечь EXIF/метаданные изображения и SHA-256.",parameters={"path":"путь к изображению"})
    add("email_send",_send_email,confirm=True,description="Отправить email через настроенный SMTP. Требует подтверждения.",parameters={"to":"получатель","subject":"тема","body":"текст"})
    notes=NoteStore(str(Path(settings.memory_path).with_name("jarvis_notes.json")))
    add("remember",notes.add,description="Сохранить факт/заметку.",parameters={"text":"что запомнить","tags":"теги через пробел"})
    add("recall",notes.recall,description="Найти сохранённые заметки.",parameters={"query":"ключевые слова"})
    add("forget",notes.forget,confirm=True,description="Удалить заметку по номеру. ОПАСНО: требует подтверждения.",parameters={"note_id":"номер заметки"})
    kg=KnowledgeGraph(settings.kg_path or str(Path(settings.memory_path).with_name("jarvis_kg.json")))
    add("kg_add",kg.add_fact,description="Добавить факт/связь в граф знаний.",parameters={"source":"субъект","relation":"отношение","target":"объект"})
    add("kg_query",kg.query,description="Найти информацию в графе знаний.",parameters={"query":"поисковый запрос"})
    add("kg_relate",kg.find_path,description="Найти цепочку связей.",parameters={"source":"первая сущность","target":"вторая сущность"})
    add("kg_forget",kg.delete,confirm=True,description="Удалить факт или сущность. ОПАСНО: требует подтверждения.",parameters={"target":"сущность или связь"})
    add("kg_show",lambda focus="":kg.visualize(focus),description="Показать граф знаний.",parameters={"focus":"сущность (необязательно)"})
    add("calc",calculate,description="Вычислить арифметическое выражение.",parameters={"expression":"выражение"})
    add("now",lambda:now(),description="Текущая дата и время.")
    return tools, reminders, notes
