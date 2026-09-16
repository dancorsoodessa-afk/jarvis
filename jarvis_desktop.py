"""Native Windows desktop UI for JARVIS with live module controls."""

import json
import math
import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from agent.runtime import build_agent
from agent import tts, voice
from agent.tools_catalog import TOOLS

BG = "#05080f"
PANEL = "#0b111b"
PANEL2 = "#101a27"
LINE = "#1d3142"
CYAN = "#37d5ee"
TEXT = "#e7f6ff"
MUTED = "#7890a3"
GREEN = "#55e39b"
RED = "#ff647c"
YELLOW = "#ffcf6b"
APP_DIR = Path(os.environ.get("APPDATA", Path.home())) / "JARVIS"
SETTINGS_FILE = APP_DIR / "settings.json"
DEFAULT_PROVIDER = "openai-compatible"
DEFAULT_URL = "http://127.0.0.1:11434/v1/chat/completions"


def _load_saved_settings() -> dict:
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


class JarvisDesktop(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("JARVIS — Personal AI System")
        self.geometry("1260x800")
        self.minsize(1040, 650)
        self.configure(bg=BG)
        self.agent = None
        self.busy = False
        self.events = queue.Queue()
        self.tool_names = []
        self._voice_loop_running = False
        self._orb_phase = 0.0
        self._orb_after = None
        self.settings = _load_saved_settings()
        self._apply_saved_settings()
        self._build_style()
        self._build_ui()
        self._start_agent()
        self.after(80, self._drain_events)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _apply_saved_settings(self):
        provider = self.settings.get("provider") or os.environ.get("JARVIS_PROVIDER") or DEFAULT_PROVIDER
        url = self.settings.get("url") or os.environ.get("JARVIS_CHAT_URL") or DEFAULT_URL
        model = self.settings.get("model") or os.environ.get("JARVIS_CHAT_MODEL") or ""
        api_key = self.settings.get("api_key") or os.environ.get("JARVIS_CHAT_KEY") or ""
        disabled = self.settings.get("disabled_tools", [])
        if not isinstance(disabled, list):
            disabled = []
        self.settings["disabled_tools"] = disabled
        self.settings.setdefault("voice_enabled", True)
        self.settings.setdefault("tts_enabled", True)
        self.settings.setdefault("tts_gender", "male")
        os.environ["JARVIS_PROVIDER"] = provider
        os.environ["JARVIS_CHAT_URL"] = url
        os.environ["JARVIS_CHAT_KEY"] = api_key
        os.environ["JARVIS_DISABLED_TOOLS"] = json.dumps(disabled, ensure_ascii=False)
        os.environ["JARVIS_TTS_GENDER"] = self.settings["tts_gender"]
        if model:
            os.environ["JARVIS_CHAT_MODEL"] = model
        else:
            os.environ.pop("JARVIS_CHAT_MODEL", None)

    def _save_settings(self):
        APP_DIR.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(self.settings, ensure_ascii=False, indent=2), encoding="utf-8")

    def _build_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TButton", background=PANEL2, foreground=TEXT, bordercolor=LINE,
                        padding=(12, 9), font=("Segoe UI", 10))
        style.map("TButton", background=[("active", "#153043")], foreground=[("active", "white")])
        style.configure("Accent.TButton", background="#103744", foreground=CYAN, bordercolor=CYAN)
        style.configure("TCheckbutton", background=PANEL2, foreground=TEXT, font=("Segoe UI", 9))
        style.map("TCheckbutton", background=[("active", PANEL2)], foreground=[("active", TEXT)])

    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)
        header = tk.Frame(self, bg=BG, height=72)
        header.grid(row=0, column=0, columnspan=3, sticky="ew")
        header.grid_columnconfigure(1, weight=1)
        tk.Label(header, text="JARVIS", bg=BG, fg=CYAN, font=("Segoe UI", 24, "bold"), padx=24).grid(row=0, column=0, pady=18)
        tk.Label(header, text="PERSONAL AI SYSTEM  /  COMMAND CENTER", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9, "bold")).grid(row=0, column=1, sticky="w")
        self.status = tk.Label(header, text="● STARTING", bg=BG, fg=MUTED,
                               font=("Segoe UI", 10, "bold"), padx=24)
        self.status.grid(row=0, column=2, sticky="e")
        self._build_sidebar()
        self._build_center()
        self._build_right()

    def _build_sidebar(self):
        side = tk.Frame(self, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        side.grid(row=1, column=0, sticky="nsew", padx=(12, 6), pady=(0, 12))
        tk.Label(side, text="CONTROL", bg=PANEL, fg=MUTED, font=("Segoe UI", 9, "bold"),
                 padx=18, pady=18).pack(anchor="w")
        self.tools_button = ttk.Button(side, text="⌁  Модули", command=self.show_tools)
        self.tools_button.pack(fill="x", padx=12, pady=5)
        ttk.Button(side, text="⚙  Настройки", command=self.show_settings).pack(fill="x", padx=12, pady=5)
        ttk.Button(side, text="🔊  Голос: ВКЛ", command=self.toggle_voice).pack(fill="x", padx=12, pady=5)
        self.voice_control = side.winfo_children()[-1]
        ttk.Button(side, text="🗣  TTS: ВКЛ", command=self.toggle_tts).pack(fill="x", padx=12, pady=5)
        self.tts_control = side.winfo_children()[-1]
        tk.Frame(side, bg=LINE, height=1).pack(fill="x", padx=12, pady=15)
        tk.Label(side, text="БЫСТРО", bg=PANEL, fg=MUTED, font=("Segoe UI", 8, "bold"),
                 padx=18, pady=4).pack(anchor="w")
        ttk.Button(side, text="↻  Перезапустить ядро", command=self._reload_agent).pack(fill="x", padx=12, pady=5)
        ttk.Button(side, text="⛔  Остановить голос", command=self._stop_voice).pack(fill="x", padx=12, pady=5)
        tk.Label(side, text="Выключенный модуль не передаётся ИИ как доступный инструмент.",
                 bg=PANEL, fg=MUTED, wraplength=210, justify="left", font=("Segoe UI", 8),
                 padx=16, pady=20).pack(side="bottom", anchor="w")

    def _build_center(self):
        center = tk.Frame(self, bg=BG)
        center.grid(row=1, column=1, sticky="nsew", padx=6, pady=(0, 12))
        center.grid_rowconfigure(1, weight=1)
        center.grid_columnconfigure(0, weight=1)
        hud = tk.Frame(center, bg=BG, height=250)
        hud.grid(row=0, column=0, sticky="ew")
        hud.grid_propagate(False)
        self.canvas = tk.Canvas(hud, width=300, height=235, bg=BG, highlightthickness=0)
        self.canvas.pack(side="left", padx=12)
        self._draw_orb()
        self.hud_text = tk.Label(hud, text="Инициализация ядра…", bg=BG, fg=CYAN,
                                 font=("Segoe UI", 12, "bold"), justify="left")
        self.hud_text.pack(side="left", anchor="center")
        chat_frame = tk.Frame(center, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        chat_frame.grid(row=1, column=0, sticky="nsew")
        chat_frame.grid_rowconfigure(0, weight=1)
        chat_frame.grid_columnconfigure(0, weight=1)
        self.chat = tk.Text(chat_frame, bg=PANEL, fg=TEXT, insertbackground=CYAN, relief="flat",
                            wrap="word", padx=18, pady=16, font=("Segoe UI", 11), state="disabled")
        self.chat.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(chat_frame, command=self.chat.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.chat.configure(yscrollcommand=scroll.set)
        input_frame = tk.Frame(center, bg=BG)
        input_frame.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        input_frame.grid_columnconfigure(0, weight=1)
        self.input = tk.Entry(input_frame, bg=PANEL2, fg=TEXT, insertbackground=CYAN,
                              relief="flat", font=("Segoe UI", 11))
        self.input.grid(row=0, column=0, sticky="ew", ipady=12, padx=(0, 8))
        self.input.bind("<Return>", lambda _e: self.send())
        self.voice_button = ttk.Button(input_frame, text="🎙 ГОЛОС", command=self.start_voice)
        self.voice_button.grid(row=0, column=1, padx=(0, 8), ipady=3)
        self.send_button = ttk.Button(input_frame, text="SEND", style="Accent.TButton", command=self.send)
        self.send_button.grid(row=0, column=2, ipadx=10, ipady=3)

    def _build_right(self):
        right = tk.Frame(self, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        right.grid(row=1, column=2, sticky="nsew", padx=(6, 12), pady=(0, 12))
        tk.Label(right, text="LIVE STATUS", bg=PANEL, fg=MUTED, font=("Segoe UI", 9, "bold"),
                 padx=16, pady=18).pack(anchor="w")
        self.metrics = {}
        for name in ("Core", "AI Provider", "Memory", "Tools", "Voice", "TTS"):
            row = tk.Frame(right, bg=PANEL)
            row.pack(fill="x", padx=16, pady=7)
            tk.Label(row, text=name, bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(side="left")
            value = tk.Label(row, text="—", bg=PANEL, fg=CYAN, font=("Segoe UI", 9, "bold"))
            value.pack(side="right")
            self.metrics[name] = value
        tk.Frame(right, bg=LINE, height=1).pack(fill="x", padx=16, pady=15)
        self.enabled_label = tk.Label(right, text="", bg=PANEL, fg=MUTED, wraplength=220,
                                      justify="left", font=("Segoe UI", 8), padx=16)
        self.enabled_label.pack(anchor="w")

    def _draw_orb(self):
        self.canvas.delete("all")
        cx, cy = 150, 112
        phase = self._orb_phase
        for rx, ry, offset in ((104, 104, 0), (82, 48, 0.9), (82, 48, -0.9), (58, 28, 1.8)):
            a = phase + offset
            dx = math.cos(a) * rx * 0.82
            dy = math.sin(a) * ry * 0.82
            self.canvas.create_oval(cx-rx, cy-ry, cx+rx, cy+ry, outline="#1b6f88", width=1)
            self.canvas.create_oval(cx+dx-3, cy+dy-3, cx+dx+3, cy+dy+3, fill=CYAN, outline="")
        for i in range(20):
            a = phase * 1.7 + i * (math.pi * 2 / 20)
            z = (math.sin(a) + 1) / 2
            r = 72 + 24 * z
            x = cx + math.cos(a) * r
            y = cy + math.sin(a) * r * 0.55
            size = 1 + int(3 * z)
            self.canvas.create_oval(x-size, y-size, x+size, y+size, fill=CYAN, outline="")
        pulse = 12 + 4 * (math.sin(phase * 2) + 1)
        self.canvas.create_oval(cx-pulse, cy-pulse, cx+pulse, cy+pulse, fill=CYAN, outline="")
        self.canvas.create_text(cx, cy+126, text="J·A·R", fill=CYAN, font=("Segoe UI", 16, "bold"))
        self._orb_phase += 0.055
        self._orb_after = self.after(40, self._draw_orb)

    def _start_agent(self):
        def work():
            try:
                self.events.put(("ready", build_agent()))
            except Exception as exc:
                self.events.put(("agent_error", str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def _start_voice_loop(self):
        if not self.settings.get("voice_enabled", True) or self._voice_loop_running or not voice.available():
            return
        self._voice_loop_running = True
        self.voice_button.config(text="🎙 СЛУШАЮ")
        self.voice_control.config(text="🔊  Голос: ВКЛ")
        def on_speech_start():
            if tts.is_playing():
                tts.stop()
                self.events.put(("voice_status", "Перебивание: TTS остановлен, слушаю вас."))
        def work():
            while self._voice_loop_running and self.settings.get("voice_enabled", True):
                try:
                    command = voice.listen_for_wake_and_command(on_speech_start=on_speech_start)
                    if command and self._voice_loop_running:
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
        self.metrics["TTS"].config(text=tts_engine.upper() if tts_ok else "OFF", fg=GREEN if tts_ok else RED)

    def _drain_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "ready":
                    self.agent = event[1]
                    self.tool_names = list(self.agent.tools.names())
                    provider = getattr(self.agent.provider, "name", "unknown").upper()
                    self.status.config(text="● ONLINE", fg=GREEN)
                    self.hud_text.config(text="Ядро активно\nAI: " + provider)
                    self.metrics["Core"].config(text="ONLINE", fg=GREEN)
                    self.metrics["AI Provider"].config(text=provider)
                    self.metrics["Memory"].config(text="ACTIVE", fg=GREEN)
                    self.metrics["Tools"].config(text=str(len(self.tool_names)), fg=GREEN)
                    self.tools_button.config(text=f"⌁  Модули ({len(self.tool_names)}/{len(TOOLS)})")
                    self.enabled_label.config(text=f"Активно модулей: {len(self.tool_names)} из {len(TOOLS)}\nОтключено: {len(TOOLS)-len(self.tool_names)}")
                    self._update_voice_status()
                    self._append("JARVIS", f"Система готова. Активных модулей: {len(self.tool_names)} из {len(TOOLS)}.")
                    if self.settings.get("voice_enabled", True):
                        self._start_voice_loop()
                elif kind == "reply":
                    reply = event[1]
                    self._append("JARVIS", reply)
                    self.busy = False
                    self.send_button.config(state="normal")
                    self.status.config(text="● ONLINE", fg=GREEN)
                    if self.settings.get("tts_enabled", True):
                        threading.Thread(target=self._speak_reply, args=(reply,), daemon=True).start()
                elif kind == "voice_text":
                    if self.busy:
                        continue
                    self.input.delete(0, "end")
                    self.input.insert(0, event[1])
                    self.send(event[1])
                elif kind == "voice_status":
                    self._append("VOICE", event[1])
                elif kind == "voice_error":
                    self._append("VOICE", "Ошибка: " + event[1])
                elif kind == "tts_error":
                    self._append("VOICE", "Ошибка TTS: " + event[1])
                    self.metrics["TTS"].config(fg=RED)
                elif kind == "agent_error":
                    self.status.config(text="● ERROR", fg=RED)
                    self._append("SYSTEM", "Не удалось запустить ядро: " + event[1])
                    self.busy = False
                    self.send_button.config(state="normal")
        except queue.Empty:
            pass
        self.after(80, self._drain_events)

    def _speak_reply(self, text):
        try:
            tts.speak_and_play(text)
        except Exception as exc:
            self.events.put(("tts_error", str(exc)))

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
            message = "Готово. Установил мужской голос JARVIS."
        elif any(phrase in normalized for phrase in female_phrases):
            gender = "female"
            message = "Готово. Установил женский голос JARVIS."
        else:
            return False
        self.settings["tts_gender"] = gender
        os.environ["JARVIS_TTS_GENDER"] = gender
        tts.set_gender(gender)
        self._save_settings()
        self.events.put(("reply", message))
        return True

    def send(self, text=None):
        if text is None:
            text = self.input.get()
        text = text.strip()
        if not text or self.agent is None or self.busy:
            return
        self.input.delete(0, "end")
        self._append("ВЫ", text)
        if self._handle_voice_setting_command(text):
            return
        self.busy = True
        self.send_button.config(state="disabled")
        self.status.config(text="● PROCESSING", fg=CYAN)
        def work():
            try:
                self.events.put(("reply", self.agent.handle(text).text))
            except Exception as exc:
                self.events.put(("reply", "Ошибка: " + str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def start_voice(self):
        if not self.settings.get("voice_enabled", True):
            self._append("VOICE", "Голос выключен. Нажмите кнопку «Голос: ВЫКЛ», чтобы включить.")
            return
        if self._voice_loop_running:
            self._append("VOICE", "Голосовой режим уже слушает.")
            return
        self._start_voice_loop()
        if not self._voice_loop_running:
            self._append("VOICE", "Голосовой ввод недоступен. Проверьте зависимости STT.")

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
        canvas.create_text(cx, 62, text=str(seed), fill=c1, font=("Segoe UI", 6, "bold"))

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
        tk.Label(win, text="Нажми переключатель — модуль будет исключён из ядра после перезапуска. Это уменьшает доступные функции и помогает разгрузить систему.",
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
            card = tk.Frame(inner, bg=PANEL2, highlightbackground=LINE, highlightthickness=1)
            card.grid(row=row, column=col, sticky="ew", padx=8, pady=7)
            icon = tk.Canvas(card, width=70, height=70, bg=PANEL2, highlightthickness=0)
            icon.pack(side="left", padx=10, pady=10)
            self._draw_tool_avatar(icon, kind, index)
            body = tk.Frame(card, bg=PANEL2)
            body.pack(side="left", fill="both", expand=True, padx=(0, 10), pady=10)
            tk.Label(body, text=title, bg=PANEL2, fg=TEXT, font=("Segoe UI", 10, "bold"),
                     anchor="w").pack(fill="x")
            tk.Label(body, text=f"/{name}", bg=PANEL2, fg=CYAN, font=("Consolas", 8),
                     anchor="w").pack(fill="x", pady=(2, 2))
            tk.Label(body, text=desc, bg=PANEL2, fg=MUTED, font=("Segoe UI", 8),
                     wraplength=310, justify="left", anchor="w").pack(fill="x")
            ttk.Checkbutton(body, text="АКТИВЕН", variable=enabled_var).pack(anchor="w", pady=(5, 0))

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
        win.title("JARVIS — Настройки")
        win.configure(bg=PANEL)
        win.geometry("760x500")
        win.transient(self)
        win.grab_set()
        saved = self.settings
        fields = [
            ("Провайдер", "provider", os.environ.get("JARVIS_PROVIDER", saved.get("provider", DEFAULT_PROVIDER))),
            ("OpenAI-compatible URL", "url", os.environ.get("JARVIS_CHAT_URL", saved.get("url", DEFAULT_URL))),
            ("Модель", "model", os.environ.get("JARVIS_CHAT_MODEL", saved.get("model", ""))),
            ("API ключ", "api_key", os.environ.get("JARVIS_CHAT_KEY", saved.get("api_key", ""))),
        ]
        entries = {}
        for i, (label, name, value) in enumerate(fields):
            tk.Label(win, text=label, bg=PANEL, fg=MUTED).grid(row=i, column=0, sticky="w", padx=20, pady=(20 if i == 0 else 10, 4))
            entry = tk.Entry(win, bg=PANEL2, fg=TEXT, insertbackground=CYAN, relief="flat", width=60,
                             show="•" if name == "api_key" else "")
            entry.insert(0, value)
            entry.grid(row=i, column=1, padx=20, pady=(20 if i == 0 else 10, 4), ipady=7)
            entries[name] = entry
        voice_var = tk.BooleanVar(value=self.settings.get("voice_enabled", True))
        tts_var = tk.BooleanVar(value=self.settings.get("tts_enabled", True))
        ttk.Checkbutton(win, text="Включать голосовое прослушивание при старте", variable=voice_var).grid(row=4, column=1, sticky="w", padx=20, pady=8)
        ttk.Checkbutton(win, text="Озвучивать ответы JARVIS через TTS", variable=tts_var).grid(row=5, column=1, sticky="w", padx=20, pady=8)
        tk.Label(win, text="Модули управления находятся в отдельном окне «Модули». Изменения применяются после пересборки ядра.",
                 bg=PANEL, fg=MUTED, wraplength=700, justify="left").grid(row=6, column=0, columnspan=2, padx=20, pady=14)
        def save():
            for name, entry in entries.items():
                self.settings[name] = entry.get().strip()
            self.settings["voice_enabled"] = bool(voice_var.get())
            self.settings["tts_enabled"] = bool(tts_var.get())
            self._apply_saved_settings()
            self._save_settings()
            win.destroy()
            self._reload_agent()
        ttk.Button(win, text="СОХРАНИТЬ И ПЕРЕЗАПУСТИТЬ", style="Accent.TButton", command=save).grid(row=7, column=1, sticky="e", padx=20, pady=10)

    def _reload_agent(self):
        self.agent = None
        self.status.config(text="● RESTARTING", fg=YELLOW)
        self._start_agent()

    def _close(self):
        self._voice_loop_running = False
        tts.stop()
        if self._orb_after:
            self.after_cancel(self._orb_after)
        self.destroy()


if __name__ == "__main__":
    JarvisDesktop().mainloop()
