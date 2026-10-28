"""Native Windows desktop UI for JARVIS with live module controls."""

import json
import base64
import math
import os
import queue
import threading
import time
import webbrowser
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import mimetypes

from agent.runtime import build_agent
from agent import tts, voice, stt
from agent.visual_server import start_visual_server
from agent.secrets import protect_secret, unprotect_secret
from agent.tools_catalog import TOOLS

BG = "#081522"
PANEL = "#0d2638"
PANEL2 = "#123e55"
LINE = "#2f7d9e"
CYAN = "#6ff3ff"
TEXT = "#f0fbff"
MUTED = "#91adbd"
GREEN = "#55e39b"
RED = "#ff647c"
YELLOW = "#ffcf6b"
APP_DIR = Path(os.environ.get("APPDATA", Path.home())) / "JARVIS"
SETTINGS_FILE = APP_DIR / "settings.json"
DEFAULT_PROVIDER = "gemini"
DEFAULT_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"


_CPU_TIMES_PREVIOUS = None


def _cpu_activity_level() -> float:
    """Return normalized Windows CPU activity for the live 3D scene (0.0–1.0)."""
    global _CPU_TIMES_PREVIOUS
    try:
        import ctypes
        from ctypes import wintypes

        if os.name != "nt":
            return 0.0

        idle = wintypes.FILETIME()
        kernel = wintypes.FILETIME()
        user = wintypes.FILETIME()
        ok = ctypes.windll.kernel32.GetSystemTimes(
            ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
        )
        if not ok:
            return 0.0

        def ticks(value):
            return (value.dwHighDateTime << 32) | value.dwLowDateTime

        current = (ticks(idle), ticks(kernel), ticks(user))
        previous = _CPU_TIMES_PREVIOUS
        _CPU_TIMES_PREVIOUS = current
        if previous is None:
            return 0.0
        idle_delta = current[0] - previous[0]
        total_delta = (current[1] - previous[1]) + (current[2] - previous[2])
        if total_delta <= 0:
            return 0.0
        return max(0.0, min(1.0, (total_delta - idle_delta) / total_delta))
    except Exception:
        return 0.0


def _safe_endpoint(value: str | None) -> str:
    """Preserve explicitly configured OpenAI-compatible endpoints, including localhost."""
    url = (value or "").strip()
    return url or DEFAULT_URL


def _safe_model_id(value: str | None, fallback: str) -> str:
    """Prevent an API URL accidentally saved in the model-ID field from breaking every request."""
    model = (value or "").strip()
    if not model or model.lower().startswith(("http://", "https://")) or "/chat/completions" in model.lower():
        return fallback
    return model


_SECRET_SETTING_KEYS = {
    "api_key",
    "gemini_api_key",
    "groq_api_key",
    "smtp_password",
    "cloudflare_token",
    "manageengine_key",
    "loaderio_key",
    "hf_token",
}

def _transform_settings_secrets(value, transform):
    if isinstance(value, dict):
        return {
            key: transform(item) if key in _SECRET_SETTING_KEYS and isinstance(item, str)
            else _transform_settings_secrets(item, transform)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_transform_settings_secrets(item, transform) for item in value]
    return value


def _load_saved_settings() -> dict:
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        return _transform_settings_secrets(data, unprotect_secret)
    except (OSError, ValueError):
        return {}




class JarvisDesktop(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("JARVIS — AI COMMAND CENTER")
        self.geometry("1420x900")
        self.minsize(1180, 740)
        self.configure(bg=BG)
        self.agent = None
        self._agent_generation = 0
        self._agent_start_pending = False
        self.busy = False
        self.events = queue.Queue()
        self.tool_names = []
        self.attachments = []
        self._voice_loop_running = False
        self._voice_armed_until = 0.0
        self._visual_state = "IDLE"
        self._visual_level = 0.0
        self.settings = _load_saved_settings()
        self._apply_saved_settings()
        if getattr(self, "_legacy_tts_settings_removed", False):
            self._save_settings()
        self._build_style()
        self._build_ui()
        # The Three.js scene is served locally; no camera access is requested.
        self._visual_server, self._visual_url = start_visual_server(
            lambda: {
                "state": self._visual_state,
                "level": self._visual_level,
                "cpu": _cpu_activity_level(),
            }
        )
        self.after(900, self._open_3d_scene)
        self._start_agent()
        self.after(80, self._drain_events)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _apply_saved_settings(self):
        profiles = self.settings.get("agents", {})
        if not isinstance(profiles, dict):
            profiles = {}
        active = int(self.settings.get("active_agent", 0) or 0)
        active = max(0, min(2, active))
        legacy = {
            "name": "JARVIS",
            "provider": "gemini",
            "url": _safe_endpoint(self.settings.get("url") or os.environ.get("JARVIS_CHAT_URL") or DEFAULT_URL),
            "model": self.settings.get("model") or os.environ.get("JARVIS_CHAT_MODEL") or "gemini-3.8-flash",
            "api_key": (str(self.settings.get("gemini_api_key") or "") if "gemini_api_key" in self.settings else os.environ.get("GEMINI_API_KEY", "")),
        }
        defaults = {
            "0": legacy,
            "1": {"name": "Gemini Reasoning", "provider": "gemini", "url": DEFAULT_URL, "model": "gemini-3.8-flash", "api_key": legacy["api_key"]},
            "2": {"name": "Gemini Coding", "provider": "gemini", "url": DEFAULT_URL, "model": "gemini-3.8-flash", "api_key": legacy["api_key"]},
        }
        merged = {}
        for key, default in defaults.items():
            value = profiles.get(key, {})
            merged[key] = {**default, **(value if isinstance(value, dict) else {})}
            merged[key]["provider"] = "gemini"
            merged[key]["url"] = DEFAULT_URL
            merged[key]["api_key"] = legacy["api_key"]
            # Migrate stale OpenRouter/Hugging Face model IDs to the configured Gemini model.
            # Old saved profiles must never override the selected provider with incompatible model IDs.
            saved_model = str(merged[key].get("model") or "").strip()
            # Migrate stale non-Gemini model IDs, but preserve valid custom Gemini
            # model names selected by the user in the control center.
            if not saved_model.lower().startswith("gemini-"):
                merged[key]["model"] = default["model"]
            else:
                merged[key]["model"] = _safe_model_id(saved_model, default["model"])
        profile = merged[str(active)]
        self.settings["active_agent"] = active
        self.settings["agents"] = merged
        self.settings["provider"] = profile["provider"]
        self.settings["url"] = _safe_endpoint(profile["url"])
        profile["url"] = self.settings["url"]
        self.settings["model"] = profile["model"]
        self.settings["api_key"] = profile["api_key"]
        os.environ["JARVIS_PROVIDER"] = "gemini"
        os.environ["JARVIS_CHAT_URL"] = self.settings["url"]
        os.environ["JARVIS_CHAT_KEY"] = profile["api_key"]
        os.environ["GEMINI_API_KEY"] = profile["api_key"]
        # An explicitly empty saved key means disconnected; do not resurrect a stale environment key.
        os.environ["GROQ_API_KEY"] = str(self.settings.get("groq_api_key") or (os.environ.get("GROQ_API_KEY") if "groq_api_key" not in self.settings else "") or "")
        os.environ["JARVIS_GROQ_MODEL"] = str(self.settings.get("groq_model") or "openai/gpt-oss-120b")
        os.environ["JARVIS_GROQ_TIMEOUT"] = str(self.settings.get("groq_timeout") or "30")
        os.environ["JARVIS_GEMINI_TIMEOUT"] = str(self.settings.get("gemini_timeout") or "30")
        # Optional integrations are configured from the control center. Explicitly
        # cleared settings override stale process environment values.
        integration_env = {
            "JARVIS_SMTP_HOST": ("smtp_host", ""),
            "JARVIS_SMTP_PORT": ("smtp_port", "587"),
            "JARVIS_SMTP_USER": ("smtp_user", ""),
            "JARVIS_SMTP_PASSWORD": ("smtp_password", ""),
            "JARVIS_SMTP_FROM": ("smtp_from", ""),
            "JARVIS_CLOUDFLARE_TOKEN": ("cloudflare_token", ""),
            "JARVIS_MANAGEENGINE_URL": ("manageengine_url", ""),
            "JARVIS_MANAGEENGINE_KEY": ("manageengine_key", ""),
            "JARVIS_LOADERIO_KEY": ("loaderio_key", ""),
        }
        for env_name, (setting_name, default) in integration_env.items():
            if setting_name in self.settings:
                value = self.settings.get(setting_name)
            else:
                value = os.environ.get(env_name, default)
            os.environ[env_name] = str(value or default).strip()
        os.environ.pop("HF_TOKEN", None)
        os.environ["JARVIS_CHAT_MODEL"] = profile["model"]
        os.environ["JARVIS_FAST_MODEL"] = merged["0"]["model"]
        os.environ["JARVIS_REASONING_MODEL"] = merged["1"]["model"]
        os.environ["JARVIS_CODING_MODEL"] = merged["2"]["model"]
        self.settings["additional_model"] = _safe_model_id(
            self.settings.get("additional_model") or os.environ.get("JARVIS_ADDITIONAL_MODEL"),
            merged["0"]["model"],
        )
        os.environ["JARVIS_ADDITIONAL_MODEL"] = self.settings["additional_model"]
        # Independent consultant providers. Keep secrets out of the repository;
        # they live only in the user's settings/environment.
        disabled = self.settings.get("disabled_tools", [])
        if not isinstance(disabled, list):
            disabled = []
        self.settings["disabled_tools"] = disabled
        os.environ["JARVIS_DISABLED_TOOLS"] = json.dumps(disabled, ensure_ascii=False)
        self.settings.setdefault("voice_enabled", True)
        self.settings.setdefault("tts_enabled", True)
        self.settings.setdefault("tts_gender", "male")
        # Remove obsolete third-party TTS settings and persist the migration once.
        obsolete_keys = ("elevenlabs_api_key", "elevenlabs_voice_id", "elevenlabs_model")
        self._legacy_tts_settings_removed = any(key in self.settings for key in obsolete_keys)
        for obsolete in obsolete_keys:
            self.settings.pop(obsolete, None)
        for obsolete_env in ("JARVIS_ELEVENLABS_API_KEY", "JARVIS_ELEVENLABS_VOICE_ID", "JARVIS_ELEVENLABS_MODEL"):
            os.environ.pop(obsolete_env, None)
        self.settings.setdefault("tts_engine", "gemini")
        self.settings.setdefault("tts_voice", "Charon")
        if self.settings.get("tts_voice") in {"Windows system voice", "Dmitri", "Microsoft David", "Microsoft Zira", ""}:
            self.settings["tts_voice"] = "Charon"
        self.settings.setdefault("tts_model", "gemini-3.8-flash-tts")
        self.settings.setdefault("tts_timeout", "45")
        self.settings.setdefault("stt_timeout", "45")
        self.settings.setdefault("stt_model", "gemini-3.8-flash")
        os.environ["JARVIS_STT_TIMEOUT"] = str(self.settings.get("stt_timeout") or "45")
        os.environ["JARVIS_STT_MODEL"] = str(self.settings.get("stt_model") or "gemini-3.8-flash")
        tts_engine = str(self.settings.get("tts_engine", "gemini")).strip().lower() or "gemini"
        if tts_engine not in {"gemini", "off"}:
            tts_engine = "gemini"
        self.settings["tts_engine"] = tts_engine
        os.environ["JARVIS_TTS"] = tts_engine
        os.environ["JARVIS_TTS_VOICE"] = str(self.settings.get("tts_voice") or "Charon")
        os.environ["JARVIS_TTS_MODEL"] = str(self.settings.get("tts_model") or "gemini-3.8-flash-tts")
        os.environ["JARVIS_TTS_TIMEOUT"] = str(self.settings.get("tts_timeout") or "45")

    def _save_settings(self):
        APP_DIR.mkdir(parents=True, exist_ok=True)
        safe = _transform_settings_secrets(self.settings, protect_secret)
        SETTINGS_FILE.write_text(
            json.dumps(safe, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _build_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TButton", background=PANEL2, foreground=TEXT, bordercolor=LINE,
                        padding=(12, 9), font=("Segoe UI", 10, "bold"), relief="flat")
        style.map("TButton", background=[("active", "#1b526c")], foreground=[("active", "white")])
        style.configure("Accent.TButton", background="#0e667a", foreground="#f4ffff",
                        bordercolor=CYAN, padding=(14, 9), font=("Segoe UI", 10, "bold"))
        style.map("Accent.TButton", background=[("active", "#148aa1")])
        style.configure("TCheckbutton", background=PANEL2, foreground=TEXT, font=("Segoe UI", 9))
        style.map("TCheckbutton", background=[("active", PANEL2)], foreground=[("active", TEXT)])


    def _build_ui(self):
        self.grid_columnconfigure(0, weight=0, minsize=230)
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=0, minsize=270)
        self.grid_rowconfigure(1, weight=1)
        self.configure(bg="#050912")

        top = tk.Frame(self, bg="#070d17", highlightbackground="#183044", highlightthickness=1, height=72)
        top.grid(row=0, column=0, columnspan=3, sticky="ew", padx=10, pady=(10, 8))
        top.grid_propagate(False)
        top.grid_columnconfigure(1, weight=1)
        brand = tk.Frame(top, bg="#070d17")
        brand.grid(row=0, column=0, sticky="w", padx=16)
        tk.Label(brand, text="J·A·R·V·I·S", bg="#070d17", fg=CYAN,
                 font=("Segoe UI", 18, "bold")).pack(anchor="w")
        tk.Label(brand, text="ПЕРСОНАЛЬНАЯ AI-ОПЕРАЦИОННАЯ СИСТЕМА", bg="#070d17", fg=MUTED,
                 font=("Consolas", 7, "bold")).pack(anchor="w")
        core = tk.Frame(top, bg="#070d17")
        core.grid(row=0, column=1, sticky="w", padx=22)
        tk.Label(core, text="A.R.C. CORE  //  ЖИВОЕ ЯДРО", bg="#070d17", fg=TEXT,
                 font=("Segoe UI", 12, "bold")).pack(anchor="w")
        tk.Label(core, text="ЛОКАЛЬНОЕ УПРАВЛЕНИЕ • AI • ПАМЯТЬ • ГОЛОС • ИНСТРУМЕНТЫ",
                 bg="#070d17", fg=MUTED, font=("Consolas", 7)).pack(anchor="w")
        statusbox = tk.Frame(top, bg="#0b1621", highlightbackground="#214357", highlightthickness=1)
        statusbox.grid(row=0, column=2, sticky="e", padx=14)
        self.status = tk.Label(statusbox, text="● ЗАПУСК", bg="#0b1621", fg=YELLOW,
                               font=("Consolas", 9, "bold"), padx=14, pady=8)
        self.status.pack()

        self._build_sidebar()
        self._build_center()
        self._build_right()

    def _build_sidebar(self):
        side = tk.Frame(self, bg="#070d16", highlightbackground="#183044", highlightthickness=1)
        side.grid(row=1, column=0, sticky="nsew", padx=(10, 7), pady=(0, 10))
        tk.Label(side, text="СИСТЕМА УПРАВЛЕНИЯ", bg="#070d16", fg=MUTED,
                 font=("Consolas", 8, "bold")).pack(anchor="w", padx=14, pady=(14, 3))
        self.side_core = tk.Label(side, text="● CORE — BOOT", bg="#070d16", fg=YELLOW,
                                  font=("Consolas", 9, "bold"))
        self.side_core.pack(anchor="w", padx=14, pady=(0, 10))
        self.side_voice = tk.Label(side, text="◉ ГОЛОС — ЗАГРУЗКА STT", bg="#070d16", fg=MUTED,
                                   font=("Consolas", 8, "bold"))
        self.side_voice.pack(anchor="w", padx=14, pady=(0, 4))
        self.side_memory = tk.Label(side, text="◆ ПАМЯТЬ — ACTIVE", bg="#070d16", fg=GREEN,
                                    font=("Consolas", 8, "bold"))
        self.side_memory.pack(anchor="w", padx=14, pady=(0, 12))

        tk.Frame(side, bg="#183044", height=1).pack(fill="x", padx=14, pady=(0, 12))
        tk.Label(side, text="БЫСТРЫЕ МОДУЛИ", bg="#070d16", fg=TEXT,
                 font=("Consolas", 8, "bold")).pack(anchor="w", padx=14, pady=(0, 7))

        def nav(text, command, accent=False):
            b=tk.Button(side,text=text,command=command,bg="#0a131f" if not accent else "#0b2630",
                        fg=CYAN if accent else "#c4d1da",activebackground="#103645",
                        activeforeground=CYAN,relief="flat",anchor="w",padx=11,pady=9,
                        font=("Segoe UI",9,"bold"),highlightbackground="#184e61" if accent else "#142231",
                        highlightthickness=1)
            b.pack(fill="x", padx=10, pady=3)
            return b

        self.tools_button = nav("⌁  МОДУЛИ И ИНСТРУМЕНТЫ", self.show_tools, True)
        nav("⚙  НАСТРОЙКИ И AI-ПРОВАЙДЕРЫ", self.show_settings)
        nav("◉  ЗАПУСК ПРИЛОЖЕНИЙ", lambda: self._open_module_details("launch","Все установленные приложения","Полный список приложений Windows",True))
        nav("▣  ПРОЦЕССЫ ПК", lambda: self._open_module_details("ps","Все процессы Windows","Список активных процессов",True))
        nav("◎  OSINT / НАБЛЮДЕНИЕ", lambda: self._open_module_details("osint","OSINT-инструменты","Инструменты разведки и поиска",True))
        nav("🧹  ОЧИСТКА ВРЕМЕННЫХ ФАЙЛОВ", lambda: self._open_module_details("cleaner","Очистка ПК","Безопасная очистка временных файлов",True))
        nav("▣  ВИДЕОКОДЕКИ", lambda: self._open_module_details("codecs","Кодеки Windows","Управление доступными видеокодеками",True))
        nav("📎  ФАЙЛЫ И ВЛОЖЕНИЯ", self.pick_attachments)
        nav("🎙  ГОЛОСОВОЙ РЕЖИМ", self.start_voice)

        tk.Frame(side, bg="#183044", height=1).pack(fill="x", padx=14, pady=14)
        tk.Label(side, text="СОСТОЯНИЕ МОДУЛЕЙ", bg="#070d16", fg=MUTED,
                 font=("Consolas", 8, "bold")).pack(anchor="w", padx=14)
        self.enabled_label = tk.Label(side, text="Активно модулей: —\nОтключено: —", bg="#070d16",
                                      fg="#9eb0bc", justify="left", font=("Consolas", 8))
        self.enabled_label.pack(anchor="w", padx=14, pady=6)
        self.tool_status_label = tk.Label(side, text="ИНСТРУМЕНТЫ: ПОДГОТОВКА", bg="#070d16",
                                          fg=MUTED, font=("Consolas", 8, "bold"))
        self.tool_status_label.pack(anchor="w", padx=14, pady=4)
        tk.Label(side, text="Кнопки открывают реальные модули. Выключенные инструменты не передаются агенту.",
                 bg="#070d16", fg="#617786", wraplength=205, justify="left",
                 font=("Segoe UI", 8)).pack(side="bottom", anchor="w", padx=14, pady=14)
    def _command_from_hud(self, command):
        self.input.delete(0, "end")
        self.input.insert(0, command)
        self.send()


    def _build_center(self):
        center = tk.Frame(self, bg="#050912")
        center.grid(row=1, column=1, sticky="nsew", padx=0, pady=(0, 10))
        center.grid_rowconfigure(1, weight=1)
        center.grid_columnconfigure(0, weight=1)

        hero = tk.Frame(center, bg="#07101a", highlightbackground="#163246", highlightthickness=1)
        hero.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        hero.grid_columnconfigure(1, weight=1)
        self.scene_label = tk.Label(hero, text="REAL 3D REACTOR\nОТКРЫВАЕТСЯ В БРАУЗЕРЕ",
                                    bg="#030811", fg=CYAN, width=34, height=11,
                                    font=("Consolas", 11, "bold"), justify="center")
        self.scene_label.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(4, 8), pady=4)
        self.hud_text = tk.Label(hero, text="Инициализация ядра…", bg="#07101a", fg=CYAN,
                                 font=("Segoe UI", 14, "bold"), justify="left")
        self.hud_text.grid(row=0, column=1, sticky="sw", padx=8, pady=(42, 4))
        tk.Label(hero, text="ЖИВОЙ ВИЗУАЛЬНЫЙ КОНТУР  •  VOICE / AI / TOOLS / MEMORY",
                 bg="#07101a", fg=MUTED, font=("Consolas", 7, "bold")).grid(row=1,column=1,sticky="nw",padx=8,pady=(0,16))

        chat_frame = tk.Frame(center, bg="#08111c", highlightbackground="#183044", highlightthickness=1)
        chat_frame.grid(row=1, column=0, sticky="nsew")
        chat_frame.grid_rowconfigure(0, weight=1)
        chat_frame.grid_columnconfigure(0, weight=1)
        self.chat = tk.Text(chat_frame, bg="#08111c", fg=TEXT, insertbackground=CYAN, relief="flat",
                            wrap="word", padx=18, pady=16, font=("Segoe UI", 10), state="disabled")
        self.chat.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(chat_frame, command=self.chat.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.chat.configure(yscrollcommand=scroll.set)

        compose = tk.Frame(center, bg="#050912")
        compose.grid(row=2, column=0, sticky="ew", pady=(8,0))
        compose.grid_columnconfigure(0, weight=1)
        self.input = tk.Entry(compose, bg="#0a1420", fg=TEXT, insertbackground=CYAN,
                              relief="flat", font=("Segoe UI", 10))
        self.input.grid(row=0, column=0, sticky="ew", ipady=12, padx=(0,6))
        self.input.bind("<Return>", lambda _e: self.send())
        self.voice_button = ttk.Button(compose, text="🎙 ГОЛОС", command=self._on_voice_button_click)
        self.voice_button.grid(row=0,column=1,padx=3,ipadx=7,ipady=3)
        # Several voice status handlers update this control; keep a valid reference.
        self.voice_control = self.voice_button
        self.attach_button = ttk.Button(compose, text="📎 ФАЙЛ", command=self.pick_attachments)
        self.attach_button.grid(row=0,column=2,padx=3,ipadx=7,ipady=3)
        self.send_button = ttk.Button(compose, text="▶  ВЫПОЛНИТЬ", style="Accent.TButton", command=self.send)
        self.send_button.grid(row=0,column=3,padx=(3,0),ipadx=8,ipady=3)

        self.attachment_label = tk.Label(center, text="Вложений нет", bg="#050912", fg=MUTED,
                                         anchor="w", font=("Consolas",8))
        self.attachment_label.grid(row=3,column=0,sticky="ew",pady=(5,0))

    def _build_right(self):
        right = tk.Frame(self, bg="#070d16", highlightbackground="#183044", highlightthickness=1)
        right.grid(row=1, column=2, sticky="nsew", padx=(7,10), pady=(0,10))
        tk.Label(right, text="ЖИВАЯ ТЕЛЕМЕТРИЯ", bg="#070d16", fg=TEXT,
                 font=("Consolas", 9, "bold")).pack(anchor="w", padx=14, pady=(14,3))
        tk.Label(right, text="REAL-TIME SYSTEM STATUS", bg="#070d16", fg=MUTED,
                 font=("Consolas", 7)).pack(anchor="w", padx=14, pady=(0,12))
        self.metrics = {}
        for name in ("Core","AI Provider","Gemini API","Groq API","Memory","Tools","Voice","TTS"):
            row=tk.Frame(right,bg="#0a131f",highlightbackground="#13283a",highlightthickness=1)
            row.pack(fill="x",padx=10,pady=4)
            tk.Label(row,text=name,bg="#0a131f",fg=MUTED,font=("Consolas",8)).pack(side="left",padx=9,pady=9)
            value=tk.Label(row,text="—",bg="#0a131f",fg=CYAN,font=("Consolas",8,"bold"))
            value.pack(side="right",padx=9)
            self.metrics[name]=value

        tk.Frame(right,bg="#183044",height=1).pack(fill="x",padx=12,pady=14)
        tk.Label(right,text="БЫСТРЫЕ ДЕЙСТВИЯ",bg="#070d16",fg=TEXT,
                 font=("Consolas",8,"bold")).pack(anchor="w",padx=14,pady=(0,7))
        actions=[
            ("◉  Статус системы","Покажи полный статус системы"),
            ("◷  Текущее время","Который сейчас час?"),
            ("◆  Возможности","Что ты умеешь?"),
            ("▣  Проверка ПК","Проверь состояние компьютера"),
        ]
        for label,cmd in actions:
            tk.Button(right,text=label,command=lambda c=cmd:self._command_from_hud(c),
                      bg="#0a131f",fg="#c4d1da",activebackground="#103645",
                      activeforeground=CYAN,relief="flat",anchor="w",padx=10,pady=9,
                      font=("Segoe UI",8,"bold"),highlightbackground="#142231",
                      highlightthickness=1).pack(fill="x",padx=10,pady=3)
        tk.Label(right,text="AI-МАРШРУТИЗАЦИЯ",bg="#070d16",fg=MUTED,
                 font=("Consolas",8,"bold")).pack(anchor="w",padx=14,pady=(15,5))
        tk.Label(right,text="Gemini — основной ИИ\nGroq — отдельный резерв\nОблачный STT и TTS",
                 bg="#070d16",fg="#8297a5",justify="left",font=("Segoe UI",8),wraplength=235).pack(anchor="w",padx=14)
    def _set_visual_state(self, state, level=None):
        self._visual_state = state
        if level is not None:
            self._visual_level = max(0.0, min(1.0, float(level)))
        labels = {
            "IDLE": "СИСТЕМА ГОТОВА",
            "LISTENING": "СЛУШАЮ ВАС",
            "THINKING": "ОБРАБОТКА",
            "SPEAKING": "ОТВЕЧАЮ",
            "ERROR": "ОШИБКА",
        }
        self.hud_text.config(text=labels.get(state, state) + "\nJARVIS CORE")
        if hasattr(self, "scene_label"):
            self.scene_label.config(text=labels.get(state, state) + "\nTHREE.JS WEBGL")

    def _open_3d_scene(self):
        try:
            webbrowser.open(self._visual_url, new=1)
            self.scene_label.config(text="THREE.JS WEBGL\n3D REACTOR ОТКРЫТ\n\nГолос и состояние ИИ\nпередаются в сцену")
        except Exception as exc:
            self.scene_label.config(text="НЕ УДАЛОСЬ ОТКРЫТЬ 3D\n" + str(exc)[:100])

    def _start_agent(self):
        # Ignore stale results when settings are saved/reloaded more than once.
        self._stt_online = False
        if hasattr(self, "metrics") and "Voice" in self.metrics:
            self.metrics["Voice"].config(text="CHECKING", fg=YELLOW)
        self._agent_generation += 1
        generation = self._agent_generation
        self._agent_start_pending = True
        self.after(30000, lambda token=generation: self._agent_start_timeout(token))

        def work():
            try:
                agent = build_agent()
                self.events.put(("ready", agent, generation))
                if generation == self._agent_generation:
                    threading.Thread(target=self._warmup_stt, daemon=True).start()
                    threading.Thread(target=self._check_provider_health, args=(agent, generation), daemon=True).start()
            except Exception as exc:
                self.events.put(("agent_error", str(exc), generation))
        threading.Thread(target=work, daemon=True).start()

    def _agent_start_timeout(self, generation):
        if generation != self._agent_generation or not self._agent_start_pending:
            return
        self._agent_start_pending = False
        self.status.config(text="● ЗАПУСК ЗАВИС", fg=RED)
        self._append("SYSTEM", "Ядро не запустилось за 30 секунд. Повторите запуск; подробности могут быть в журнале JARVIS.")

    def _check_provider_health(self, agent, generation):
        try:
            provider = getattr(agent, "provider", None)
            checks = provider.health_checks() if provider and hasattr(provider, "health_checks") else {}
            if not self.settings.get("tts_enabled", True):
                checks["TTS"] = "OFF"
            else:
                try:
                    checks["TTS"] = tts.health_check()
                except Exception as exc:
                    checks["TTS"] = "ERROR: " + str(exc)[:160]
            self.events.put(("provider_health", checks, generation))
        except Exception as exc:
            self.events.put(("provider_health", {"Gemini API": "ERROR: " + str(exc)[:160]}, generation))

    def _warmup_stt(self):
        try:
            stt.warmup()
            self.events.put(("stt_ready", None))
        except Exception as exc:
            self.events.put(("stt_error", str(exc)))

    def _start_voice_loop(self):
        if not self.settings.get("voice_enabled", True) or self._voice_loop_running:
            return
        if not getattr(self, "_stt_online", False):
            self._append("VOICE", "Проверяю доступность облачного распознавания речи. Подождите несколько секунд.")
            return
        if not voice.available():
            self._append("VOICE", "Голосовой ввод недоступен: проверьте ключ Gemini и входной микрофон.")
            return
        self._voice_loop_running = True
        self.voice_button.config(text="🎙 СЛУШАЮ")
        self.voice_control.config(text="🔊  Голос: ВКЛ")
        last_level_event = [0.0]
        def on_audio_level(level):
            now = time.monotonic()
            if now - last_level_event[0] >= 0.08:
                last_level_event[0] = now
                self.events.put(("audio_level", max(0.0, min(1.0, float(level)))))
        def work():
            wake_words = ("jarvis", "джарвис")
            while self._voice_loop_running and self.settings.get("voice_enabled", True):
                try:
                    if tts.is_playing():
                        time.sleep(0.12)
                        continue
                    heard = voice.listen_for_phrase(
                        silence_seconds=0.55,
                        max_seconds=10.0,
                        start_timeout=2.0,
                        on_audio_level=on_audio_level,
                        should_stop=tts.is_playing,
                    )
                    self.events.put(("voice_capture_done",))
                    if not heard or not self._voice_loop_running:
                        continue
                    normalized = " ".join(heard.lower().split())
                    command = None
                    activated = False
                    for word in wake_words:
                        if normalized.startswith(word):
                            activated = True
                            command = normalized[len(word):].strip(" ,.!")
                            self._voice_armed_until = float("inf")
                            break
                    if activated and not command:
                        self.events.put(("voice_status", "Jarvis активирован. Слушаю вас."))
                        command = voice.listen_for_phrase(
                            silence_seconds=0.55,
                            max_seconds=10.0,
                            start_timeout=4.0,
                            on_audio_level=on_audio_level,
                            should_stop=tts.is_playing,
                        )
                        self.events.put(("voice_capture_done",))
                    elif not activated and time.monotonic() < self._voice_armed_until:
                        command = normalized
                    else:
                        continue
                    if command in {"стоп", "режим ожидания", "перейди в режим ожидания", "спасибо джарвис", "спасибо джарвис"}:
                        self._voice_armed_until = 0.0
                        self.events.put(("voice_status", "Голосовой режим: ожидание. Скажите «Джарвис», чтобы продолжить."))
                        continue
                    if command and self._voice_loop_running:
                        self._voice_armed_until = float("inf")
                        self.events.put(("voice_text", command))
                except Exception as exc:
                    self.events.put(("voice_error", str(exc)))
                    break
            self._voice_loop_running = False
        threading.Thread(target=work, daemon=True).start()

    def _stop_voice(self):
        self._voice_loop_running = False
        self.voice_button.config(text="🎙 ГОЛОС")
        self._append("VOICE", "Голосовой цикл остановлен. Его можно включить снова кнопкой «Голос». ")

    def toggle_voice(self):
        self.settings["voice_enabled"] = not self.settings.get("voice_enabled", True)
        self._save_settings()
        if self.settings["voice_enabled"]:
            self._start_voice_loop()
            self.voice_control.config(text="🔊  Голос: ВКЛ")
        else:
            self._stop_voice()
            self.voice_control.config(text="🔇  Голос: ВЫКЛ")
        self._update_voice_status()

    def toggle_tts(self):
        self.settings["tts_enabled"] = not self.settings.get("tts_enabled", True)
        self._save_settings()
        if not self.settings["tts_enabled"]:
            tts.stop()
        self.tts_control.config(text=("🗣  TTS: ВКЛ" if self.settings["tts_enabled"] else "🗣  TTS: ВЫКЛ"))
        self._update_voice_status()

    def _update_voice_status(self):
        stt_ok = voice.available() and self.settings.get("voice_enabled", True)
        tts_engine = tts.current_engine()
        tts_ok = self.settings.get("tts_enabled", True) and tts_engine != "off"
        self.metrics["Voice"].config(text="ON" if stt_ok else "OFF", fg=GREEN if stt_ok else RED)
        tts_label = "KEY SET" if tts_ok else "NO KEY"
        self.metrics["TTS"].config(text=tts_label, fg=YELLOW if tts_ok else RED)

    def _drain_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                try:
                    if kind == "ready":
                        if len(event) > 2 and event[2] != self._agent_generation:
                            continue
                        self._agent_start_pending = False
                        self.agent = event[1]
                        self.tool_names = list(self.agent.tools.names())
                        configured_providers = getattr(self.agent.provider, "providers", {})
                        provider = "GEMINI PRIMARY" + (" / GROQ BACKUP" if "groq" in configured_providers else "")
                        # Building the local agent does not prove that the remote API is reachable.
                        self.status.config(text="● ГОТОВ", fg=YELLOW)
                        self.hud_text.config(text="Ядро готово\nAI: " + provider + "\nAPI: проверка при запросе")
                        self.metrics["Core"].config(text="READY", fg=YELLOW)
                        self.metrics["AI Provider"].config(text=provider)
                        self.metrics["Memory"].config(text="ACTIVE", fg=GREEN)
                        self.metrics["Tools"].config(text=str(len(self.tool_names)), fg=GREEN)
                        self.tools_button.config(text=f"⌁  Модули ({len(self.tool_names)}/{len(TOOLS)})")
                        self.enabled_label.config(text=f"Активно модулей: {len(self.tool_names)} из {len(TOOLS)}\nОтключено: {len(TOOLS)-len(self.tool_names)}")
                        self._update_voice_status()
                        self.side_core.config(text="● CORE  —  ACTIVE", fg=GREEN)
                        self._append("JARVIS", f"Система готова. Активных модулей: {len(self.tool_names)} из {len(TOOLS)}.")
                    elif kind == "provider_health":
                        if len(event) > 2 and event[2] != self._agent_generation:
                            continue
                        for label, result in event[1].items():
                            if label not in self.metrics:
                                continue
                            status_text = str(result).split(":", 1)[0].upper()
                            color = GREEN if status_text == "ONLINE" else MUTED if status_text == "OFF" else YELLOW if status_text in {"CONFIGURED", "KEY SET"} else RED
                            self.metrics[label].config(text=status_text[:18], fg=color)
                        gemini_status = event[1].get("Gemini API", "UNKNOWN")
                        groq_status = event[1].get("Groq API", "NOT CONFIGURED")
                        self._append("SYSTEM", f"Проверка провайдеров — Gemini: {gemini_status}; Groq: {groq_status}")
                    elif kind == "stt_ready":
                        self._stt_online = True
                        self.metrics["Voice"].config(text="ONLINE", fg=GREEN)
                        self.side_voice.config(text="◉ ГОЛОС — ОБЛАКО ДОСТУПНО", fg=GREEN)
                        # Do not open the microphone automatically on application startup.
                        # Voice capture begins only after the user presses the microphone button.
                    elif kind == "stt_error":
                        self._stt_online = False
                        self.metrics["Voice"].config(text="ERROR", fg=RED)
                        self.side_voice.config(text="◉ ГОЛОС — ОШИБКА", fg=RED)
                        self._append("VOICE", "STT: " + event[1])
                    elif kind == "reply_delta":
                        self._streaming_reply = getattr(self, "_streaming_reply", "") + str(event[1])
                        self._set_visual_state("THINKING", 0.7)
                        self._replace_streaming_reply(self._streaming_reply)
                    elif kind == "reply":
                        reply = event[1]
                        if getattr(self, "_streaming_reply", ""):
                            self._replace_streaming_reply(reply, final=True)
                        else:
                            self._append("JARVIS", reply)
                        self._streaming_reply = ""
                        self.busy = False
                        self.send_button.config(state="normal")
                        self.attach_button.config(state="normal")
                        self.status.config(text="● ONLINE", fg=GREEN)
                        if self.settings.get("tts_enabled", True):
                            self._set_visual_state("THINKING", 0.35)
                            threading.Thread(target=self._speak_reply, args=(reply,), daemon=True).start()
                        else:
                            self._set_visual_state("IDLE", 0.0)
                    elif kind == "audio_level":
                        if not self.busy and self._visual_state not in {"THINKING", "SPEAKING", "ERROR"}:
                            self._set_visual_state("LISTENING", event[1])
                        else:
                            self._visual_level = max(0.0, min(1.0, float(event[1])))
                    elif kind == "voice_capture_done":
                        if not self.busy and self._visual_state == "LISTENING":
                            self._set_visual_state("IDLE", 0.0)
                    elif kind == "tts_started":
                        self._set_visual_state("SPEAKING", 0.7)
                    elif kind == "tts_done":
                        self.metrics["TTS"].config(text="ONLINE", fg=GREEN)
                        if not self.busy:
                            self._set_visual_state("IDLE", 0.0)
                    elif kind == "voice_text":
                        self._set_visual_state("LISTENING", 0.75)
                        if self.busy:
                            continue
                        self.input.delete(0, "end")
                        self.input.insert(0, event[1])
                        self.send(event[1])
                    elif kind == "voice_status":
                        self._append("VOICE", event[1])
                    elif kind == "voice_error":
                        self._set_visual_state("ERROR")
                        self.voice_button.config(text="🎙 ГОЛОС")
                        self.metrics["Voice"].config(text="ERROR", fg=RED)
                        self.side_voice.config(text="◉ ГОЛОС — ОШИБКА", fg=RED)
                        self._append("VOICE", "Прослушивание остановлено: " + event[1] + " Нажмите «Голос», чтобы повторить запуск.")
                    elif kind == "tts_error":
                        self._set_visual_state("ERROR")
                        self.metrics["TTS"].config(text="ERROR", fg=RED)
                        self._append("VOICE", "Не удалось озвучить ответ: " + event[1])
                    elif kind == "request_error":
                        self._set_visual_state("ERROR")
                        self.status.config(text="● API ERROR", fg=RED)
                        self._append("AI", "Запрос не выполнен: " + event[1])
                        self.busy = False
                        self.send_button.config(state="normal")
                        self.attach_button.config(state="normal")
                        self._streaming_reply = ""
                    elif kind == "agent_error":
                        if len(event) > 2 and event[2] != self._agent_generation:
                            continue
                        self._agent_start_pending = False
                        self._set_visual_state("ERROR")
                        self.status.config(text="● ERROR", fg=RED)
                        self._append("SYSTEM", "Не удалось запустить ядро: " + event[1])
                        self.busy = False
                        self.send_button.config(state="normal")
                        self.attach_button.config(state="normal")

                except Exception as exc:
                    # A malformed UI event must not stop all future replies/events.
                    try:
                        self.status.config(text="● UI ERROR", fg=RED)
                        self._append("SYSTEM", "Ошибка обработки события: " + str(exc))
                    except Exception:
                        pass
        except queue.Empty:
            pass
        finally:
            try:
                self.after(80, self._drain_events)
            except tk.TclError:
                pass

    def _speak_reply(self, text):
        # This function runs on a worker thread. Never call Tk widgets here:
        # Tkinter is not thread-safe and a UI exception used to prevent TTS itself.
        try:
            tts.speak_and_play(text, on_playback_start=lambda: self.events.put(("tts_started",)))
            self.events.put(("tts_done",))
        except Exception as exc:
            self.events.put(("tts_error", str(exc)))

    def _replace_streaming_reply(self, text, final=False):
        self.chat.configure(state="normal")
        if not getattr(self, "_streaming_reply_started", False):
            self.chat.insert("end", "JARVIS\n", "who")
            self._streaming_reply_started = True
        self.chat.delete("end-1c linestart", "end")
        self.chat.insert("end", text, "stream_body")
        if final:
            self.chat.insert("end", "\n\n")
            self._streaming_reply_started = False
        self.chat.tag_configure("stream_body", foreground=TEXT)
        self.chat.see("end")
        self.chat.configure(state="disabled")

    def _append(self, who, text):
        self.chat.configure(state="normal")
        self.chat.insert("end", f"{who}\n", "who")
        self.chat.insert("end", text + "\n\n", "body")
        self.chat.tag_configure("who", foreground=CYAN, font=("Segoe UI", 9, "bold"))
        self.chat.tag_configure("body", foreground=TEXT)
        self.chat.see("end")
        self.chat.configure(state="disabled")

    def _handle_voice_setting_command(self, text):
        """Handle voice-gender commands locally, without sending them to the AI backend."""
        normalized = " ".join(text.lower().replace("ё", "е").split())
        male_phrases = ("голос на мужской", "мужской голос", "сделай голос мужским", "поставь мужской голос", "включи мужской голос")
        female_phrases = ("голос на женский", "женский голос", "сделай голос женским", "поставь женский голос", "включи женский голос")
        if any(phrase in normalized for phrase in male_phrases):
            gender = "male"
            voice_name = "Charon"
            message = "Выбран облачный голос Gemini Charon."
        elif any(phrase in normalized for phrase in female_phrases):
            gender = "female"
            voice_name = "Aoede"
            message = "Выбран облачный голос Gemini Aoede."
        else:
            return False
        self.settings["tts_gender"] = gender
        self.settings["tts_voice"] = voice_name
        os.environ["JARVIS_TTS_GENDER"] = gender
        os.environ["JARVIS_TTS_VOICE"] = voice_name
        tts.set_gender(gender)
        self._save_settings()
        self.events.put(("reply", message))
        return True

    def pick_attachments(self):
        paths=filedialog.askopenfilenames(parent=self,title="Прикрепить файлы, фото, видео или аудио",
            filetypes=[("Все файлы","*.*")])
        if not paths: return
        self.attachments=[]
        for raw in paths:
            p=Path(raw)
            try: size=p.stat().st_size
            except OSError: continue
            if size<=50*1024*1024:
                self.attachments.append({"path":str(p),"name":p.name,"mime":mimetypes.guess_type(p.name)[0] or "application/octet-stream","size":size})
        self._refresh_attachment_label()

    def _refresh_attachment_label(self):
        if not self.attachments:
            self.attachment_label.config(text="Вложений нет",fg=MUTED); return
        names=", ".join(x["name"] for x in self.attachments)
        self.attachment_label.config(text=f"📎 {len(self.attachments)} файл(ов): {names[:140]}",fg=CYAN)

    def _build_attachment_context(self):
        if not self.attachments: return ""
        parts=["ВЛОЖЕНИЯ ПОЛЬЗОВАТЕЛЯ:"]
        for x in self.attachments:
            p=Path(x["path"])
            line=f"- {x['name']} | {x['mime']} | {x['size']} байт | путь: {p}"
            if x["size"] <= 15*1024*1024:
                try:
                    suffix=p.suffix.lower()
                    if suffix in {".txt",".md",".csv",".json",".xml",".log",".yaml",".yml",".toml",".ini",".py",".ps1",".js",".ts",".html",".css"}:
                        line+="\n  Содержимое:\n"+p.read_text(encoding="utf-8",errors="replace")[:120000]
                    elif suffix in {".pdf",".docx",".xlsx",".xlsm",".zip",".tar",".gz",".7z",".rar"}:
                        from agent.tools.universal import inspect_file
                        line+="\n  Анализ файла:\n"+inspect_file(str(p))[:120000]
                except Exception as exc:
                    line+=f"\n  Не удалось прочитать содержимое автоматически: {exc}"
            parts.append(line)
        return "\n".join(parts)

    def _build_attachment_payload(self):
        for x in self.attachments:
            mime=x.get("mime","").lower()
            if not (mime.startswith("image/") or mime.startswith("audio/")):
                continue
            p=Path(x["path"])
            try:
                if p.stat().st_size > 15*1024*1024:
                    continue
                return {"name":p.name,"mime":mime,"data":base64.b64encode(p.read_bytes()).decode("ascii")}
            except OSError:
                continue
        return None

    def _clear_attachments(self):
        self.attachments=[]; self._refresh_attachment_label()

    def send(self, text=None):
        if text is None: text=self.input.get()
        text=text.strip()
        if not text:
            self._append("SYSTEM", "Введите команду или используйте кнопку «Голос».")
            return
        if self.busy:
            self._append("SYSTEM", "Предыдущая команда ещё выполняется. Дождитесь ответа.")
            return
        if self.agent is None:
            self._append("SYSTEM", "Ядро ещё не готово или не запустилось. Проверьте статус и API-ключ в настройках.")
            return
        context=self._build_attachment_context()
        shown = text + (
            "\n📎 " + ", ".join(x["name"] for x in self.attachments)
            if self.attachments else ""
        )
        self.input.delete(0, "end")
        self._append("ВЫ", shown)
        if self._handle_voice_setting_command(text):
            self._clear_attachments(); return
        prompt=text+("\n\n"+context if context else "")
        attachment_payload=self._build_attachment_payload()
        self.busy=True; self.send_button.config(state="disabled"); self.attach_button.config(state="disabled")
        self.status.config(text="● PROCESSING",fg=CYAN)
        self._set_visual_state("THINKING", 0.55)
        def work():
            provider = getattr(self.agent, "provider", None)
            try:
                if provider is not None and hasattr(provider, "on_delta"):
                    provider.on_delta = lambda delta: self.events.put(("reply_delta", delta))
                result=self.agent.handle(prompt, attachment=attachment_payload)
                if provider is not None and hasattr(provider, "on_delta"):
                    provider.on_delta = None
                # JarvisAgent converts provider exceptions into an AgentResult string.
                # Detect that error explicitly instead of showing it as a successful reply.
                if str(result.text).startswith("Ошибка провайдера:"):
                    self.events.put(("request_error", str(result.text).partition(":")[2].strip()))
                else:
                    self.events.put(("reply",result.text))
            except Exception as exc:
                if provider is not None and hasattr(provider, "on_delta"):
                    provider.on_delta = None
                self.events.put(("request_error", str(exc)))
        self._clear_attachments()
        threading.Thread(target=work,daemon=True).start()

    def _on_voice_button_click(self):
        """Start voice capture without allowing a voice callback to hide the main window."""
        try:
            was_visible = self.state() != "iconic"
        except Exception:
            was_visible = True
        try:
            self.start_voice()
        except Exception as exc:
            try:
                self._append("VOICE", f"Не удалось запустить голосовой ввод: {exc}")
            except Exception:
                pass
        if was_visible:
            def keep_main_window_visible():
                try:
                    if self.winfo_exists() and self.state() == "iconic":
                        self.deiconify()
                        self.lift()
                except Exception:
                    pass
            self.after(150, keep_main_window_visible)

    def start_voice(self):
        if not self.settings.get("voice_enabled", True):
            self._append("VOICE", "Голос выключен. Включите его в настройках.")
            return
        if not getattr(self, "_stt_online", False):
            self._append("VOICE", "Облачное распознавание ещё проверяется или недоступно. Повторите после статуса ONLINE.")
            return
        # A manual click explicitly arms command capture: the user should not
        # have to say the wake word after pressing the microphone button.
        self._voice_armed_until = float("inf")
        if self._voice_loop_running:
            self.voice_button.config(text="🎙 СЛУШАЮ КОМАНДУ")
            self._append("VOICE", "Микрофон активен. Говорите команду сейчас — слово «Джарвис» не обязательно.")
            return
        self._start_voice_loop()
        if self._voice_loop_running:
            self._append("VOICE", "Микрофон включён. Говорите команду сейчас — слово «Джарвис» не обязательно.")
        else:
            devices = voice.audio_devices()
            detail = " Доступные микрофоны: " + ", ".join(devices) if devices else " Windows не обнаружил входной микрофон."
            self._append("VOICE", "Голосовой ввод не запущен. Проверьте разрешение микрофона в Windows и API-ключ Gemini." + detail)

    def _draw_tool_avatar(self, canvas, kind, seed):
        palette = {
            "core": (CYAN, "#0b5d73"), "folder": ("#6bdcff", "#155a76"), "danger": (RED, "#7a2334"),
            "app": ("#b68cff", "#4b2c7a"), "web": (GREEN, "#1c6c4a"), "audio": (YELLOW, "#805d1b"),
            "screen": ("#73a7ff", "#294d87"), "process": ("#f39cff", "#703d78"), "clipboard": ("#9ee6d1", "#326e60"),
            "time": ("#8ed0ff", "#315e83"), "voice": ("#ff9dce", "#74345b"), "weather": ("#80c9ff", "#24577d"),
            "intel": ("#d4a7ff", "#633a83"), "image": ("#91e7ff", "#286b80"), "mail": ("#ffad8a", "#7d3f2d"),
            "memory": ("#72f0ad", "#26754b"), "graph": ("#9fa9ff", "#394580"), "calc": ("#f5df72", "#75661c"),
        }
        c1, c2 = palette.get(kind, (CYAN, "#155a76"))
        canvas.delete("all")
        cx, cy = 32, 32
        canvas.create_oval(6, 9, 58, 58, fill="#02050a", outline="")
        angle = (seed % 11) * 0.42
        for r, flat, off in ((22, 8, 0), (17, 6, 1.2), (12, 4, 2.2)):
            a = angle + off
            x = cx + math.cos(a) * 12
            y = cy + math.sin(a) * flat
            canvas.create_oval(x-r, y-flat, x+r, y+flat, outline=c2, width=1)
        points = []
        for i in range(6):
            a = angle + i * math.pi / 3
            points.append((cx + math.cos(a) * 20, cy + math.sin(a) * 20))
        for x, y in points:
            canvas.create_oval(x-2, y-2, x+2, y+2, fill=c1, outline="")
        canvas.create_oval(cx-9, cy-9, cx+9, cy+9, fill=c1, outline="")
        canvas.create_oval(cx-5, cy-6, cx+1, cy, fill="#eaffff", outline="")

    def _run_ui_prompt(self, prompt: str):
        """Send a prepared, human-readable task from a button to the assistant."""
        self._command_from_hud(prompt)
        self.send()

    def _open_module_details(self, name, title, desc, enabled):
        """Open practical, button-driven controls; never expose shell commands to the user."""
        win = tk.Toplevel(self)
        win.title("JARVIS — " + title)
        win.configure(bg=BG)
        win.geometry("900x680")
        win.minsize(700, 500)
        win.transient(self)

        header = tk.Frame(win, bg=BG)
        header.pack(fill="x", padx=20, pady=(18, 8))
        tk.Label(header, text=title, bg=BG, fg=CYAN,
                 font=("Segoe UI", 18, "bold")).pack(anchor="w")
        tk.Label(header, text=desc, bg=BG, fg=MUTED,
                 font=("Segoe UI", 10), wraplength=840, justify="left").pack(anchor="w", pady=(4, 0))

        body = tk.Frame(win, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        body.pack(fill="both", expand=True, padx=20, pady=10)

        def action_button(parent, label, command, danger=False):
            return tk.Button(
                parent, text=label, command=command,
                bg="#572637" if danger else "#123e55",
                fg=TEXT, activebackground="#1d6178", activeforeground=TEXT,
                relief="flat", padx=12, pady=8, cursor="hand2",
                font=("Segoe UI", 9, "bold")
            )

        def status_line(text):
            tk.Label(body, text=text, bg=PANEL, fg=MUTED,
                     font=("Segoe UI", 9), justify="left", wraplength=800).pack(
                         anchor="w", padx=16, pady=(12, 4))

        if name == "launch":
            status_line("Выберите приложение и нажмите «Запустить». Поиск работает по названию.")
            search_var = tk.StringVar()
            search_row = tk.Frame(body, bg=PANEL)
            search_row.pack(fill="x", padx=16, pady=8)
            tk.Label(search_row, text="Поиск приложения", bg=PANEL, fg=TEXT).pack(side="left")
            search_entry = tk.Entry(search_row, textvariable=search_var, bg="#07131f", fg=TEXT,
                                    insertbackground=TEXT, relief="flat", font=("Segoe UI", 10))
            search_entry.pack(side="left", fill="x", expand=True, padx=10, ipady=7)
            list_frame = tk.Frame(body, bg=PANEL)
            list_frame.pack(fill="both", expand=True, padx=16, pady=(0, 12))
            canvas = tk.Canvas(list_frame, bg=PANEL, highlightthickness=0)
            scroll = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
            inner = tk.Frame(canvas, bg=PANEL)
            inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
            wid = canvas.create_window((0, 0), window=inner, anchor="nw")
            canvas.configure(yscrollcommand=scroll.set)
            canvas.pack(side="left", fill="both", expand=True)
            scroll.pack(side="right", fill="y")
            canvas.bind("<Configure>", lambda e: canvas.itemconfigure(wid, width=e.width))
            try:
                import subprocess
                result = subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     "Get-StartApps | Sort-Object Name | ForEach-Object { \"$($_.Name)|$($_.AppID)\" }"],
                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=12
                )
                apps = []
                for line in result.stdout.splitlines():
                    if "|" in line:
                        app_name, app_id = line.split("|", 1)
                        if app_name.strip() and app_id.strip():
                            apps.append((app_name.strip(), app_id.strip()))
            except Exception:
                apps = []

            def launch_app(app_id, app_name):
                try:
                    import subprocess
                    subprocess.Popen(
                        ["explorer.exe", "shell:AppsFolder\\" + app_id],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                    self._append("JARVIS", "Запуск приложения: " + app_name)
                except Exception as exc:
                    messagebox.showerror("Не удалось запустить", str(exc), parent=win)

            app_rows = []
            for app_name, app_id in apps:
                row = tk.Frame(inner, bg=PANEL2)
                row.pack(fill="x", pady=3)
                tk.Label(row, text=app_name, bg=PANEL2, fg=TEXT,
                         font=("Segoe UI", 9), anchor="w").pack(side="left", fill="x", expand=True, padx=10, pady=8)
                action_button(row, "ЗАПУСТИТЬ", lambda i=app_id, n=app_name: launch_app(i, n)).pack(side="right", padx=8, pady=4)
                app_rows.append((row, app_name))
            def filter_apps(*_):
                query = search_var.get().casefold().strip()
                for row, app_name in app_rows:
                    row.pack_forget()
                    if not query or query in app_name.casefold():
                        row.pack(fill="x", pady=3)
            search_var.trace_add("write", filter_apps)
            if not apps:
                status_line("Список приложений Windows не удалось получить. Проверьте, что JARVIS запущен в Windows.")
        elif name == "ps":
            status_line("Процессы показаны по названию. Завершение процесса всегда требует подтверждения.")
            top = tk.Frame(body, bg=PANEL)
            top.pack(fill="x", padx=16, pady=8)
            search_var = tk.StringVar()
            tk.Label(top, text="Поиск процесса", bg=PANEL, fg=TEXT).pack(side="left")
            entry = tk.Entry(top, textvariable=search_var, bg="#07131f", fg=TEXT,
                             insertbackground=TEXT, relief="flat", font=("Segoe UI", 10))
            entry.pack(side="left", fill="x", expand=True, padx=10, ipady=7)
            list_frame = tk.Frame(body, bg=PANEL)
            list_frame.pack(fill="both", expand=True, padx=16, pady=(0, 12))
            canvas = tk.Canvas(list_frame, bg=PANEL, highlightthickness=0)
            scroll = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
            inner = tk.Frame(canvas, bg=PANEL)
            inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
            wid = canvas.create_window((0, 0), window=inner, anchor="nw")
            canvas.configure(yscrollcommand=scroll.set)
            canvas.pack(side="left", fill="both", expand=True)
            scroll.pack(side="right", fill="y")
            canvas.bind("<Configure>", lambda e: canvas.itemconfigure(wid, width=e.width))
            try:
                import subprocess, json
                result = subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     "Get-Process | Sort-Object ProcessName | Select-Object ProcessName,Id | ConvertTo-Json -Compress"],
                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=12
                )
                raw = json.loads(result.stdout or "[]")
                processes = raw if isinstance(raw, list) else ([raw] if raw else [])
            except Exception:
                processes = []
            process_rows = []
            protected = {"system", "registry", "smss", "csrss", "wininit", "services", "lsass", "winlogon", "svchost", "explorer"}
            def end_process(pid, process_name):
                if process_name.casefold() in protected:
                    messagebox.showwarning("Защищённый процесс", "Этот системный процесс нельзя завершить из JARVIS.", parent=win)
                    return
                if not messagebox.askyesno("Подтверждение", f"Завершить процесс «{process_name}» (PID {pid})?", parent=win):
                    return
                try:
                    import subprocess
                    result = subprocess.run(["taskkill.exe", "/PID", str(int(pid)), "/T"],
                                            capture_output=True, text=True, timeout=10)
                    if result.returncode:
                        messagebox.showerror("Не удалось завершить процесс",
                                             (result.stderr or result.stdout or "Нет подробностей").strip(), parent=win)
                    else:
                        messagebox.showinfo("Готово", f"Процесс «{process_name}» завершён.", parent=win)
                        win.destroy()
                        self._open_module_details("ps", title, desc, enabled)
                except Exception as exc:
                    messagebox.showerror("Ошибка", str(exc), parent=win)
            for proc in processes:
                pname = str(proc.get("ProcessName", ""))
                pid = proc.get("Id")
                if not pname or pid is None:
                    continue
                row = tk.Frame(inner, bg=PANEL2)
                row.pack(fill="x", pady=3)
                tk.Label(row, text=f"{pname}   •   PID {pid}", bg=PANEL2, fg=TEXT,
                         font=("Segoe UI", 9), anchor="w").pack(side="left", fill="x", expand=True, padx=10, pady=8)
                action_button(row, "ЗАВЕРШИТЬ", lambda p=pid, n=pname: end_process(p, n), danger=True).pack(side="right", padx=8, pady=4)
                process_rows.append((row, pname))
            def filter_processes(*_):
                query = search_var.get().casefold().strip()
                for row, pname in process_rows:
                    row.pack_forget()
                    if not query or query in pname.casefold():
                        row.pack(fill="x", pady=3)
            search_var.trace_add("write", filter_processes)
            if not processes:
                status_line("Не удалось получить список процессов.")
        elif name == "osint":
            status_line("Выберите тип проверки, введите значение и нажмите кнопку. Используются только публичные сведения.")
            query = tk.StringVar()
            row = tk.Frame(body, bg=PANEL)
            row.pack(fill="x", padx=16, pady=12)
            tk.Label(row, text="Домен, IP, URL, email или username", bg=PANEL, fg=TEXT).pack(anchor="w")
            entry = tk.Entry(row, textvariable=query, bg="#07131f", fg=TEXT, insertbackground=TEXT,
                             relief="flat", font=("Segoe UI", 11))
            entry.pack(fill="x", pady=(6, 0), ipady=8)
            buttons = tk.Frame(body, bg=PANEL)
            buttons.pack(fill="x", padx=16, pady=8)
            for label, kind in (("ПРОВЕРИТЬ ДОМЕН", "домен"), ("ПРОВЕРИТЬ IP", "IP-адрес"),
                                ("ПРОВЕРИТЬ URL", "URL"), ("ПРОВЕРИТЬ EMAIL", "email"),
                                ("ПРОВЕРИТЬ USERNAME", "username")):
                action_button(buttons, label, lambda k=kind: self._run_ui_prompt(
                    f"Выполни OSINT-проверку типа {k} для значения: {query.get().strip()}"
                    if query.get().strip() else "Открой OSINT-проверку и попроси меня ввести значение."
                )).pack(side="left", padx=(0, 6), pady=4)
            action_button(body, "ОТКРЫТЬ OSINT В ЧАТЕ", lambda: self._run_ui_prompt(
                "Помоги выбрать и выполнить безопасную OSINT-проверку публичного домена, IP, URL, email или username."
            )).pack(anchor="w", padx=16, pady=8)
        elif name == "cleaner":
            status_line("Очистка удаляет только содержимое временных папок пользователя и Windows Temp. Файлы, занятые программами, пропускаются.")
            tk.Label(body, text="Перед удалением JARVIS покажет подтверждение. Личные документы и загрузки не затрагиваются.",
                     bg=PANEL, fg=TEXT, wraplength=800, justify="left").pack(anchor="w", padx=16, pady=8)
            def clean_temp():
                if not messagebox.askyesno("Подтвердить очистку",
                    "Удалить доступные временные файлы? Личные документы не затрагиваются.", parent=win):
                    return
                import tempfile, shutil
                roots = {Path(tempfile.gettempdir()), Path(os.environ.get("WINDIR", r"C:\Windows")) / "Temp"}
                deleted = 0
                skipped = 0
                errors = 0
                for root in roots:
                    try:
                        if not root.exists():
                            continue
                        for item in root.iterdir():
                            try:
                                if item.is_dir() and not item.is_symlink():
                                    shutil.rmtree(item)
                                else:
                                    item.unlink()
                                deleted += 1
                            except PermissionError:
                                skipped += 1
                            except OSError:
                                errors += 1
                    except OSError:
                        errors += 1
                messagebox.showinfo("Очистка завершена",
                    f"Удалено объектов: {deleted}\nПропущено занятых/недоступных: {skipped}\nДругих ошибок: {errors}", parent=win)
            action_button(body, "ОЧИСТИТЬ ВРЕМЕННЫЕ ФАЙЛЫ", clean_temp, danger=True).pack(anchor="w", padx=16, pady=14)
        elif name == "codecs":
            status_line("Установка кодеков зависит от формата и версии Windows. JARVIS не запускает неизвестные установщики.")
            action_button(body, "ОТКРЫТЬ УСТАНОВЛЕННЫЕ ПРИЛОЖЕНИЯ",
                          lambda: os.startfile("ms-settings:appsfeatures")).pack(anchor="w", padx=16, pady=8)
            action_button(body, "ОТКРЫТЬ MICROSOFT STORE — HEVC",
                          lambda: webbrowser.open("https://apps.microsoft.com/search?query=HEVC%20Video%20Extensions")).pack(anchor="w", padx=16, pady=8)
            action_button(body, "ОТКРЫТЬ MICROSOFT STORE — AV1",
                          lambda: webbrowser.open("https://apps.microsoft.com/search?query=AV1%20Video%20Extension")).pack(anchor="w", padx=16, pady=8)
        else:
            status_line("Для этой функции доступны понятные действия через кнопки. Команды оболочки вводить не требуется.")
            action_button(body, "ПОПРОСИТЬ JARVIS ВЫПОЛНИТЬ ЗАДАЧУ",
                          lambda: self._run_ui_prompt(f"Помоги выполнить задачу: {title}. Сначала объясни действие простыми словами и запроси подтверждение перед изменениями в системе.")).pack(anchor="w", padx=16, pady=12)
            if name == "run_command":
                tk.Label(body, text="Ручной ввод shell-команд не используется в этом окне. Опишите цель обычными словами в чате JARVIS.",
                         bg=PANEL, fg=YELLOW, wraplength=800, justify="left").pack(anchor="w", padx=16, pady=8)

        ttk.Button(win, text="ЗАКРЫТЬ", command=win.destroy).pack(anchor="e", padx=20, pady=(0, 14))

    def show_tools(self):
        win = tk.Toplevel(self)
        win.title("JARVIS — Управление модулями")
        win.configure(bg=BG)
        win.geometry("1120x760")
        win.minsize(920, 600)
        win.transient(self)
        header = tk.Frame(win, bg=BG)
        header.pack(fill="x", padx=20, pady=(18, 8))
        tk.Label(header, text="АКТИВНЫЕ МОДУЛИ", bg=BG, fg=CYAN,
                 font=("Segoe UI", 18, "bold")).pack(side="left")
        self.tool_status_label = tk.Label(header, text="", bg=BG, fg=GREEN,
                                          font=("Segoe UI", 10, "bold"))
        self.tool_status_label.pack(side="right")
        tk.Label(win, text="Нажми на модуль, чтобы открыть его. Переключатель «АКТИВЕН» включает или отключает функцию. JARVIS сам выбирает нужный инструмент по вашей задаче — команды вводить не нужно.",
                 bg=BG, fg=MUTED, font=("Segoe UI", 9), wraplength=1040, justify="left").pack(anchor="w", padx=22, pady=(0, 10))

        outer = tk.Frame(win, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        outer.pack(fill="both", expand=True, padx=20, pady=(0, 12))
        canvas = tk.Canvas(outer, bg=PANEL, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=scrollbar.set)
        inner = tk.Frame(canvas, bg=PANEL)
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def resize_inner(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfigure(window_id, width=canvas.winfo_width())
        inner.bind("<Configure>", resize_inner)
        canvas.bind("<Configure>", resize_inner)

        disabled = set(self.settings.get("disabled_tools", []))
        switches = {}
        catalog = {name: (title, desc, kind) for name, title, desc, kind in TOOLS}
        for index, (name, title, desc, kind) in enumerate(TOOLS, start=1):
            enabled_var = tk.BooleanVar(value=name not in disabled)
            switches[name] = enabled_var
            row = (index - 1) // 2
            col = (index - 1) % 2
            inner.grid_columnconfigure(col, weight=1)
            card = tk.Frame(inner, bg=PANEL2, highlightbackground=LINE, highlightthickness=1, cursor="hand2")
            card.grid(row=row, column=col, sticky="ew", padx=8, pady=7)
            icon = tk.Canvas(card, width=70, height=70, bg=PANEL2, highlightthickness=0, cursor="hand2")
            icon.pack(side="left", padx=10, pady=10)
            self._draw_tool_avatar(icon, kind, index)
            body = tk.Frame(card, bg=PANEL2)
            body.pack(side="left", fill="both", expand=True, padx=(0, 10), pady=10)
            tk.Label(body, text=title, bg=PANEL2, fg=TEXT, font=("Segoe UI", 10, "bold"),
                     anchor="w").pack(fill="x")
            tk.Label(body, text=desc, bg=PANEL2, fg=MUTED, font=("Segoe UI", 8),
                     wraplength=310, justify="left", anchor="w").pack(fill="x")
            state_label = tk.Label(body, text=("● АКТИВЕН" if enabled_var.get() else "● ВЫКЛЮЧЕН"), bg=PANEL2, fg=GREEN if enabled_var.get() else RED, font=("Segoe UI", 8, "bold"), cursor="hand2")
            state_label.pack(anchor="w", pady=(5, 0))
            state_label.bind("<Button-1>", lambda e, v=enabled_var, l=state_label: (v.set(not v.get()), l.config(text=("● АКТИВЕН" if v.get() else "● ВЫКЛЮЧЕН"), fg=GREEN if v.get() else RED)))
            action_row = tk.Frame(body, bg=PANEL2)
            action_row.pack(fill="x", pady=(8, 0))
            ttk.Button(action_row, text="ОТКРЫТЬ ИНСТРУМЕНТ",
                       command=lambda n=name, t=title, d=desc, v=enabled_var: self._open_module_details(n, t, d, v.get())).pack(side="left")
            state_label.bind("<Button-1>", lambda e, v=enabled_var, l=state_label: (v.set(not v.get()), l.config(text=("● АКТИВЕН" if v.get() else "● ВЫКЛЮЧЕН"), fg=GREEN if v.get() else RED)))

        def save_modules():
            new_disabled = [name for name, var in switches.items() if not var.get()]
            self.settings["disabled_tools"] = new_disabled
            os.environ["JARVIS_DISABLED_TOOLS"] = json.dumps(new_disabled, ensure_ascii=False)
            self._save_settings()
            win.destroy()
            self._reload_agent()

        bottom = tk.Frame(win, bg=BG)
        bottom.pack(fill="x", padx=20, pady=(0, 16))
        ttk.Button(bottom, text="Включить ВСЕ", command=lambda: [v.set(True) for v in switches.values()]).pack(side="left")
        ttk.Button(bottom, text="Выключить ВСЕ", command=lambda: [v.set(False) for v in switches.values()]).pack(side="left", padx=8)
        ttk.Button(bottom, text="СОХРАНИТЬ И ПЕРЕЗАПУСТИТЬ ЯДРО", style="Accent.TButton",
                   command=save_modules).pack(side="right")
        self.tool_status_label.config(text=f"Активно сейчас: {len(self.tool_names)} / {len(TOOLS)}")

    def show_settings(self):
        win = tk.Toplevel(self)
        win.title("JARVIS — Центр управления")
        win.configure(bg=PANEL)
        win.geometry("900x780")
        win.minsize(820, 700)
        win.transient(self)
        win.grab_set()
        tk.Label(win, text="ЦЕНТР УПРАВЛЕНИЯ JARVIS", bg=PANEL, fg=CYAN,
                 font=("Segoe UI", 19, "bold")).pack(anchor="w", padx=24, pady=(22, 4))
        tk.Label(win, text="Gemini — основной ИИ, Groq — независимый резерв. Gemini также обслуживает облачный STT и TTS.",
                 bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", padx=24, pady=(0, 16))

        body = tk.Frame(win, bg=PANEL)
        body.pack(fill="both", expand=True, padx=20)
        canvas = tk.Canvas(body, bg=PANEL, highlightthickness=0)
        scroll = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=PANEL)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        profiles = self.settings.get("agents", {})
        if not isinstance(profiles, dict):
            profiles = {}
        active = int(self.settings.get("active_agent", 0) or 0)
        names = ("FAST / Обычные", "REASONING / Рассуждения", "CODING / Код")
        defaults = (
            ("gemini", DEFAULT_URL, "gemini-3.8-flash"),
            ("gemini", DEFAULT_URL, "gemini-3.8-flash"),
            ("gemini", DEFAULT_URL, "gemini-3.8-flash"),
        )
        shared_key_row = tk.Frame(inner, bg="#091b29", highlightbackground=CYAN, highlightthickness=1)
        shared_key_row.pack(fill="x", pady=(0, 10))
        tk.Label(shared_key_row, text="GEMINI API KEY (GOOGLE AI STUDIO)", bg="#091b29", fg=CYAN, font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=14, pady=(10, 4))
        shared_key = tk.Entry(shared_key_row, bg=PANEL2, fg=TEXT, insertbackground=CYAN, relief="flat", show="", exportselection=True)
        shared_key.insert(0, str(self.settings.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY", "")))
        shared_key.pack(fill="x", padx=14, pady=(0, 6), ipady=8)
        def clear_entry(entry):
            entry.delete(0, "end")
            entry.focus_set()
        tk.Button(shared_key_row, text="ОЧИСТИТЬ КЛЮЧ GEMINI",
                  command=lambda: clear_entry(shared_key), bg="#572637", fg=TEXT,
                  activebackground="#7a3046", relief="flat", padx=10, pady=5).pack(anchor="e", padx=14, pady=(0, 8))
        # Make paste reliable in packaged Tkinter builds and provide an explicit clipboard action.
        def paste_gemini_key():
            try:
                value = self.clipboard_get().strip()
                if value:
                    shared_key.delete(0, "end")
                    shared_key.insert(0, value)
                    shared_key.icursor("end")
                    shared_key.focus_set()
            except tk.TclError:
                messagebox.showwarning("Буфер обмена", "Не удалось прочитать ключ из буфера обмена.", parent=win)
        paste_row = tk.Frame(shared_key_row, bg="#091b29")
        paste_row.pack(fill="x", padx=14, pady=(0, 12))
        tk.Button(paste_row, text="ВСТАВИТЬ ИЗ БУФЕРА", command=paste_gemini_key,
                  bg="#0e667a", fg=TEXT, activebackground="#148aa1", relief="flat", padx=12, pady=6).pack(side="left")
        tk.Label(paste_row, text="Ctrl+V также поддерживается; ключ сохраняется локально.",
                 bg="#091b29", fg=MUTED, font=("Segoe UI", 8)).pack(side="left", padx=10)
        shared_key.bind("<Control-v>", lambda _e: self.after(20, lambda: shared_key.icursor("end")))
        shared_key.bind("<Control-V>", lambda _e: self.after(20, lambda: shared_key.icursor("end")))

        groq_row = tk.Frame(inner, bg="#091b29", highlightbackground=LINE, highlightthickness=1)
        groq_row.pack(fill="x", pady=(0, 10))
        tk.Label(groq_row, text="РЕЗЕРВНЫЙ ПРОВАЙДЕР GROQ (НЕ ЗАВИСИТ ОТ GEMINI)", bg="#091b29", fg=TEXT,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=14, pady=(10, 4))
        groq_key = tk.Entry(groq_row, bg=PANEL2, fg=TEXT, insertbackground=CYAN, relief="flat", show="•", exportselection=False)
        groq_key.insert(0, str(self.settings.get("groq_api_key") or os.environ.get("GROQ_API_KEY", "")))
        groq_key.pack(fill="x", padx=14, pady=(0, 6), ipady=8)
        tk.Button(groq_row, text="ОЧИСТИТЬ КЛЮЧ GROQ",
                  command=lambda: clear_entry(groq_key), bg="#572637", fg=TEXT,
                  activebackground="#7a3046", relief="flat", padx=10, pady=5).pack(anchor="e", padx=14, pady=(0, 8))
        groq_fields = {}
        for label, key, default in (
            ("Модель Groq", "groq_model", self.settings.get("groq_model", "openai/gpt-oss-120b")),
            ("Тайм-аут Groq, сек.", "groq_timeout", self.settings.get("groq_timeout", "30")),
            ("Тайм-аут Gemini, сек.", "gemini_timeout", self.settings.get("gemini_timeout", "30")),
        ):
            row = tk.Frame(groq_row, bg="#091b29")
            row.pack(fill="x", padx=14, pady=3)
            tk.Label(row, text=label, width=22, anchor="w", bg="#091b29", fg=MUTED).pack(side="left")
            entry = tk.Entry(row, bg=PANEL2, fg=TEXT, insertbackground=CYAN, relief="flat")
            entry.insert(0, str(default))
            entry.pack(side="left", fill="x", expand=True, ipady=6)
            tk.Button(row, text="×", command=lambda e=entry: clear_entry(e), bg="#572637", fg=TEXT, relief="flat", width=3).pack(side="left", padx=(6, 0))
            groq_fields[key] = entry
        tk.Label(groq_row, text="Ключ создаётся отдельно в GroqCloud. Без ключа резервный провайдер отключён.",
                 bg="#091b29", fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", padx=14, pady=(6, 10))

        additional_row = tk.Frame(inner, bg="#091b29", highlightbackground=LINE, highlightthickness=1)
        additional_row.pack(fill="x", pady=(2, 10))
        tk.Label(additional_row, text="4. ADDITIONAL — резерв / второе мнение", bg="#091b29", fg=TEXT, font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=14, pady=(10, 4))
        additional_model = tk.Entry(additional_row, bg=PANEL2, fg=TEXT, insertbackground=CYAN, relief="flat")
        additional_model.insert(0, str(self.settings.get("additional_model", "gemini-3.8-flash")))
        additional_model.pack(fill="x", padx=14, pady=(0, 4), ipady=6)
        tk.Button(additional_row, text="ОЧИСТИТЬ", command=lambda: clear_entry(additional_model), bg="#572637", fg=TEXT, relief="flat", padx=8, pady=4).pack(anchor="e", padx=14, pady=(0, 8))

        integration_row = tk.Frame(inner, bg="#091b29", highlightbackground=LINE, highlightthickness=1)
        integration_row.pack(fill="x", pady=(2, 10))
        tk.Label(integration_row, text="ВНЕШНИЕ ИНТЕГРАЦИИ", bg="#091b29", fg=CYAN,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=14, pady=(10, 4))
        tk.Label(integration_row, text="Ключи хранятся только в локальных настройках JARVIS. Оставьте поле пустым, если сервис не используете.",
                 bg="#091b29", fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", padx=14, pady=(0, 6))
        integration_fields = {}
        for label, key, default, secret in (
            ("SMTP сервер", "smtp_host", self.settings.get("smtp_host", ""), False),
            ("SMTP порт", "smtp_port", self.settings.get("smtp_port", "587"), False),
            ("SMTP пользователь", "smtp_user", self.settings.get("smtp_user", ""), False),
            ("SMTP пароль", "smtp_password", self.settings.get("smtp_password", ""), True),
            ("SMTP отправитель", "smtp_from", self.settings.get("smtp_from", ""), False),
            ("Cloudflare API token", "cloudflare_token", self.settings.get("cloudflare_token", ""), True),
            ("ManageEngine URL", "manageengine_url", self.settings.get("manageengine_url", ""), False),
            ("ManageEngine API key", "manageengine_key", self.settings.get("manageengine_key", ""), True),
            ("Loader.io API key", "loaderio_key", self.settings.get("loaderio_key", ""), True),
        ):
            row = tk.Frame(integration_row, bg="#091b29")
            row.pack(fill="x", padx=14, pady=3)
            tk.Label(row, text=label, width=23, anchor="w", bg="#091b29", fg=MUTED).pack(side="left")
            entry = tk.Entry(row, bg=PANEL2, fg=TEXT, insertbackground=CYAN, relief="flat",
                             show="•" if secret else "", exportselection=False)
            entry.insert(0, str(default))
            entry.pack(side="left", fill="x", expand=True, ipady=6)
            tk.Button(row, text="×", command=lambda e=entry: clear_entry(e), bg="#572637",
                      fg=TEXT, relief="flat", width=3).pack(side="left", padx=(6, 0))
            integration_fields[key] = entry

        entries = []
        for i, title in enumerate(names):
            dprov, durl, dmodel = defaults[i]
            p = profiles.get(str(i), {})
            if not isinstance(p, dict):
                p = {}
            card = tk.Frame(inner, bg="#091b29", highlightbackground=CYAN if i == active else LINE, highlightthickness=1)
            card.pack(fill="x", pady=7)
            head = tk.Frame(card, bg="#091b29")
            head.pack(fill="x", padx=14, pady=(12, 4))
            tk.Label(head, text=f"{i+1}. {title}", bg="#091b29",
                     fg=CYAN if i == active else TEXT, font=("Segoe UI", 12, "bold")).pack(side="left")
            tk.Button(head, text="СДЕЛАТЬ АКТИВНЫМ", command=lambda idx=i: self._select_agent(idx, win),
                      bg="#0e667a", fg=TEXT, relief="flat", padx=10, pady=5).pack(side="right")
            fields = {}
            for label, key, default, secret in (
                ("Модель Gemini", "model", p.get("model", dmodel), False),
            ):
                row = tk.Frame(card, bg="#091b29")
                row.pack(fill="x", padx=14, pady=4)
                tk.Label(row, text=label, width=13, anchor="w", bg="#091b29", fg=MUTED).pack(side="left")
                e = tk.Entry(row, bg=PANEL2, fg=TEXT, insertbackground=CYAN, relief="flat",
                             show="•" if secret else "", exportselection=False)
                e.insert(0, str(default))
                e.pack(side="left", fill="x", expand=True, ipady=6)
                tk.Button(row, text="×", command=lambda entry=e: clear_entry(entry), bg="#572637", fg=TEXT, relief="flat", width=3).pack(side="left", padx=(6, 0))
                fields[key] = e
            entries.append(fields)

        voice_frame = tk.Frame(inner, bg="#091b29", highlightbackground=CYAN, highlightthickness=1)
        voice_frame.pack(fill="x", pady=10)
        tk.Label(voice_frame, text="ГОЛОС JARVIS / ОБЛАЧНЫЙ TTS", bg="#091b29", fg=CYAN,
                 font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=14, pady=(12, 6))
        voice_fields = {}
        for label, key, default, secret in (
            ("Облачный TTS", "tts_engine", self.settings.get("tts_engine", "gemini"), False),
            ("Голос Gemini", "tts_voice", self.settings.get("tts_voice", "Charon"), False),
            ("Модель TTS", "tts_model", self.settings.get("tts_model", "gemini-3.8-flash-tts"), False),
            ("Тайм-аут TTS, сек.", "tts_timeout", self.settings.get("tts_timeout", "45"), False),
            ("Модель STT", "stt_model", self.settings.get("stt_model", "gemini-3.8-flash"), False),
            ("Тайм-аут STT, сек.", "stt_timeout", self.settings.get("stt_timeout", "45"), False),
        ):
            row = tk.Frame(voice_frame, bg="#091b29")
            row.pack(fill="x", padx=14, pady=4)
            tk.Label(row, text=label, width=20, anchor="w", bg="#091b29", fg=MUTED).pack(side="left")
            e = tk.Entry(row, bg=PANEL2, fg=TEXT, insertbackground=CYAN, relief="flat", show="•" if secret else "")
            e.insert(0, str(default))
            e.pack(side="left", fill="x", expand=True, ipady=6)
            tk.Button(row, text="×", command=lambda entry=e: clear_entry(entry), bg="#572637", fg=TEXT, relief="flat", width=3).pack(side="left", padx=(6, 0))
            voice_fields[key] = e

        voice_var = tk.BooleanVar(value=self.settings.get("voice_enabled", True))
        tts_var = tk.BooleanVar(value=self.settings.get("tts_enabled", True))
        ttk.Checkbutton(inner, text="Голосовое прослушивание при старте", variable=voice_var).pack(anchor="w", padx=14, pady=6)
        ttk.Checkbutton(inner, text="Озвучивать ответы через TTS", variable=tts_var).pack(anchor="w", padx=14, pady=6)

        def save():
            new_profiles = {}
            for i, fields in enumerate(entries):
                new_profiles[str(i)] = {"provider": "gemini", "url": DEFAULT_URL, "model": fields["model"].get().strip() or "gemini-3.8-flash", "api_key": shared_key.get().strip(), "name": names[i]}
            self.settings["agents"] = new_profiles
            self.settings["gemini_api_key"] = shared_key.get().strip()
            self.settings["groq_api_key"] = groq_key.get().strip()
            for key, entry in integration_fields.items():
                self.settings[key] = entry.get().strip()
            for key, entry in groq_fields.items():
                self.settings[key] = entry.get().strip()
            self.settings.pop("hf_token", None)
            self.settings["additional_model"] = additional_model.get().strip() or "gemini-3.8-flash"
            self.settings["active_agent"] = active
            self.settings["voice_enabled"] = bool(voice_var.get())
            self.settings["tts_enabled"] = bool(tts_var.get())
            for k, e in voice_fields.items():
                self.settings[k] = e.get().strip()
            if self.settings.get("tts_engine", "gemini").strip().lower() not in {"gemini", "off"}:
                self.settings["tts_engine"] = "gemini"
            self._apply_saved_settings()
            self._save_settings()
            win.destroy()
            self._reload_agent()

        action_row = tk.Frame(win, bg=PANEL)
        action_row.pack(fill="x", padx=24, pady=18)
        connection_status = tk.Label(action_row, text="Проверка использует сохранённые настройки.", bg=PANEL, fg=MUTED, font=("Segoe UI", 8))
        connection_status.pack(side="left", fill="x", expand=True)
        def test_connection():
            agent = self.agent
            if agent is None:
                connection_status.config(text="Ядро ещё запускается. Сначала сохраните настройки и дождитесь запуска.", fg=YELLOW)
                return
            connection_status.config(text="Проверяю соединение с ИИ…", fg=YELLOW)
            def worker():
                try:
                    provider = getattr(agent, "provider", None)
                    if provider is None:
                        raise RuntimeError("Провайдер ИИ не создан")
                    answer = provider.generate("Ответь одним словом: подключение работает", tools=None)
                    result = "СВЯЗЬ ЕСТЬ: " + str(answer).strip().replace("\\n", " ")[:120]
                    color = GREEN
                except Exception as exc:
                    result = "НЕТ СВЯЗИ: " + str(exc)[:220]
                    color = RED
                self.after(0, lambda: connection_status.config(text=result, fg=color) if win.winfo_exists() else None)
            threading.Thread(target=worker, daemon=True).start()
        tk.Button(action_row, text="ПРОВЕРИТЬ СВЯЗЬ", command=test_connection,
                  bg="#123e55", fg=TEXT, activebackground="#1b526c", relief="flat", padx=10, pady=7).pack(side="left", padx=(8, 10))
        ttk.Button(action_row, text="СОХРАНИТЬ И ПЕРЕЗАПУСТИТЬ", style="Accent.TButton", command=save).pack(side="right")

    def _select_agent(self, idx, parent=None):
        self.settings["active_agent"] = idx
        self._apply_saved_settings()
        self._save_settings()
        self._reload_agent()
        if parent and parent.winfo_exists():
            parent.destroy()

    def _reload_agent(self):
        self.agent = None
        self.status.config(text="● RESTARTING", fg=YELLOW)
        self._start_agent()

    def _close(self):
        self._voice_loop_running = False
        tts.stop()
        try:
            self._visual_server.shutdown()
            self._visual_server.server_close()
        except Exception:
            pass
        self.destroy()


if __name__ == "__main__":
    JarvisDesktop().mainloop()