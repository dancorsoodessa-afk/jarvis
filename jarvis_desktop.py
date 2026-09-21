"""Native Windows desktop UI for JARVIS with live module controls."""

import json
import math
import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import mimetypes

from agent.runtime import build_agent
from agent import tts, voice
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
        self.title("JARVIS — NEXT COMMAND CENTER")
        self.geometry("1420x900")
        self.minsize(1180, 740)
        self.configure(bg=BG)
        self.agent = None
        self.busy = False
        self.events = queue.Queue()
        self.tool_names = []
        self.attachments = []
        self._voice_loop_running = False
        self._orb_phase = 0.0
        self._visual_state = "IDLE"
        self._visual_level = 0.0
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
        os.environ["JARVIS_ELEVENLABS_API_KEY"] = self.settings.get("elevenlabs_api_key") or os.environ.get("JARVIS_ELEVENLABS_API_KEY", "")
        os.environ["JARVIS_ELEVENLABS_VOICE_ID"] = self.settings.get("elevenlabs_voice_id") or os.environ.get("JARVIS_ELEVENLABS_VOICE_ID", "srULqtwUV9XZPg1ZCO5w")
        os.environ["JARVIS_ELEVENLABS_MODEL"] = self.settings.get("elevenlabs_model") or os.environ.get("JARVIS_ELEVENLABS_MODEL", "eleven_flash_v2_5")
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
                        padding=(12, 9), font=("Segoe UI", 10, "bold"), relief="flat")
        style.map("TButton", background=[("active", "#1b526c")], foreground=[("active", "white")])
        style.configure("Accent.TButton", background="#0e667a", foreground="#f4ffff",
                        bordercolor=CYAN, padding=(14, 9), font=("Segoe UI", 10, "bold"))
        style.map("Accent.TButton", background=[("active", "#148aa1")])
        style.configure("TCheckbutton", background=PANEL2, foreground=TEXT, font=("Segoe UI", 9))
        style.map("TCheckbutton", background=[("active", PANEL2)], foreground=[("active", TEXT)])

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=0, minsize=235)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        top = tk.Frame(self, bg="#0b2233", height=76, highlightbackground=LINE, highlightthickness=1)
        top.grid(row=0, column=0, columnspan=2, sticky="ew", padx=14, pady=(14, 8))
        top.grid_propagate(False)
        top.grid_columnconfigure(1, weight=1)
        tk.Label(top, text="JARVIS", bg="#0b2233", fg=CYAN, font=("Segoe UI", 24, "bold")).grid(row=0, column=0, rowspan=2, padx=(22, 16))
        tk.Label(top, text="COMMAND DECK", bg="#0b2233", fg=TEXT, font=("Segoe UI", 11, "bold")).grid(row=0, column=1, sticky="sw")
        tk.Label(top, text="AI  •  MEMORY  •  VOICE  •  TOOLS", bg="#0b2233", fg=MUTED, font=("Segoe UI", 8, "bold")).grid(row=1, column=1, sticky="nw", pady=(2, 14))
        self.status = tk.Label(top, text="● INITIALIZING", bg="#0b2233", fg=YELLOW, font=("Segoe UI", 10, "bold"), padx=20)
        self.status.grid(row=0, column=2, rowspan=2, sticky="e", padx=14)
        self._build_sidebar()
        self._build_center()

    def _build_sidebar(self):
        side = tk.Frame(self, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        side.grid(row=1, column=0, sticky="nsew", padx=(14, 8), pady=(0, 14))
        side.configure(width=235)
        tk.Label(side, text="CONTROL", bg=PANEL, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=18, pady=(20, 10))
        self.tools_button = ttk.Button(side, text="◈  Модули", command=self.show_tools)
        self.tools_button.pack(fill="x", padx=12, pady=4, ipady=5)
        ttk.Button(side, text="⚙  Настройки", command=self.show_settings).pack(fill="x", padx=12, pady=4, ipady=5)
        ttk.Button(side, text="🔊  Голос: ВКЛ", command=self.toggle_voice).pack(fill="x", padx=12, pady=4, ipady=5)
        self.voice_control = side.winfo_children()[-1]
        ttk.Button(side, text="🗣  TTS: ВКЛ", command=self.toggle_tts).pack(fill="x", padx=12, pady=4, ipady=5)
        self.tts_control = side.winfo_children()[-1]
        tk.Frame(side, bg=LINE, height=1).pack(fill="x", padx=16, pady=18)
        tk.Label(side, text="SYSTEM", bg=PANEL, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=18, pady=(0, 6))
        self.side_core = tk.Label(side, text="● CORE  —  BOOT", bg=PANEL, fg=YELLOW, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=18, pady=5)
        self.side_voice = tk.Label(side, text="● VOICE  —  READY", bg=PANEL, fg=GREEN, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=18, pady=5)
        self.side_memory = tk.Label(side, text="● MEMORY  —  ACTIVE", bg=PANEL, fg=GREEN, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=18, pady=5)
        tk.Frame(side, bg=LINE, height=1).pack(fill="x", padx=16, pady=18)
        ttk.Button(side, text="↻  Перезапустить ядро", command=self._reload_agent).pack(fill="x", padx=12, pady=4)
        ttk.Button(side, text="■  Остановить голос", command=self._stop_voice).pack(fill="x", padx=12, pady=4)
        tk.Label(side, text="JARVIS ONLINE\nЛокальное управление • память • инструменты", bg=PANEL, fg=MUTED, wraplength=195, justify="left", font=("Segoe UI", 8), padx=18, pady=20).pack(side="bottom", anchor="w")

    def _build_center(self):
        center = tk.Frame(self, bg=BG)
        center.grid(row=1, column=1, sticky="nsew", padx=(0, 14), pady=(0, 14))
        center.grid_rowconfigure(1, weight=1)
        center.grid_columnconfigure(0, weight=1)
        hud = tk.Frame(center, bg="#0c2b40", highlightbackground=LINE, highlightthickness=1, height=300)
        hud.grid(row=0, column=0, sticky="ew", pady=(0, 9))
        hud.grid_propagate(False)
        hud.grid_columnconfigure(1, weight=1)
        self.canvas = tk.Canvas(hud, width=380, height=290, bg="#0c2b40", highlightthickness=0)
        self.canvas.grid(row=0, column=0, padx=8)
        self._draw_orb()
        info = tk.Frame(hud, bg="#0c2b40")
        info.grid(row=0, column=1, sticky="nsew", padx=(8, 22))
        tk.Label(info, text="JARVIS CORE", bg="#0c2b40", fg=CYAN, font=("Segoe UI", 20, "bold")).pack(anchor="w", pady=(42, 2))
        tk.Label(info, text="PERSONAL AI COMMAND CENTER", bg="#0c2b40", fg=MUTED, font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 14))
        self.hud_text = tk.Label(info, text="СИСТЕМА ЗАПУСКАЕТСЯ\nJARVIS CORE", bg="#0c2b40", fg=TEXT, font=("Segoe UI", 12, "bold"), justify="left")
        self.hud_text.pack(anchor="w", pady=4)
        self.metrics = {}
        metric_frame = tk.Frame(info, bg="#0c2b40")
        metric_frame.pack(fill="x", pady=(14, 0))
        for name in ("Core", "AI Provider", "Memory", "Tools", "Voice", "TTS"):
            row = tk.Frame(metric_frame, bg="#0c2b40")
            row.pack(fill="x", pady=2)
            tk.Label(row, text=name.upper(), width=13, anchor="w", bg="#0c2b40", fg=MUTED, font=("Segoe UI", 8, "bold")).pack(side="left")
            value = tk.Label(row, text="—", anchor="w", bg="#0c2b40", fg=GREEN, font=("Segoe UI", 8, "bold"))
            value.pack(side="left")
            self.metrics[name] = value
        chat_frame = tk.Frame(center, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        chat_frame.grid(row=1, column=0, sticky="nsew")
        chat_frame.grid_rowconfigure(0, weight=1)
        chat_frame.grid_columnconfigure(0, weight=1)
        self.chat = tk.Text(chat_frame, bg="#0a2030", fg=TEXT, insertbackground=CYAN, relief="flat", wrap="word", padx=24, pady=20, font=("Segoe UI", 11), state="disabled")
        self.chat.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(chat_frame, command=self.chat.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.chat.configure(yscrollcommand=scroll.set)
        input_frame = tk.Frame(center, bg=BG)
        input_frame.grid(row=2, column=0, sticky="ew", pady=(9, 0))
        input_frame.grid_columnconfigure(0, weight=1)
        self.input = tk.Entry(input_frame, bg="#123b52", fg=TEXT, insertbackground=CYAN, relief="flat", font=("Segoe UI", 11))
        self.input.grid(row=0, column=0, sticky="ew", ipady=13, padx=(0, 7))
        self.input.bind("<Return>", lambda _e: self.send())
        self.attach_button = ttk.Button(input_frame, text="📎", command=self.pick_attachments)
        self.attach_button.grid(row=0, column=1, padx=3, ipady=4)
        self.voice_button = ttk.Button(input_frame, text="🎙", command=self.start_voice)
        self.voice_button.grid(row=0, column=2, padx=3, ipady=4)
        self.send_button = ttk.Button(input_frame, text="ОТПРАВИТЬ", style="Accent.TButton", command=self.send)
        self.send_button.grid(row=0, column=3, padx=(3,0), ipadx=12, ipady=4)
        self.attachment_label = tk.Label(center, text="Вложений нет", bg=BG, fg=MUTED, font=("Segoe UI", 8), anchor="w")
        self.attachment_label.grid(row=3, column=0, sticky="ew", pady=(4,0))
        self.enabled_label = tk.Label(center, text="", bg=BG, fg=MUTED, font=("Segoe UI", 8), anchor="e")
        self.enabled_label.grid(row=4, column=0, sticky="e", pady=(2,0))

    def _build_right(self):
        return

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

    def _draw_orb(self):
        self.canvas.delete("all")
        cx, cy = 175, 132
        phase = self._orb_phase
        state = self._visual_state
        level = self._visual_level
        speed = {"IDLE": 0.018, "LISTENING": 0.07, "THINKING": 0.11, "SPEAKING": 0.08, "ERROR": 0.16}.get(state, 0.04)
        pulse = 1.0 + 0.10 * math.sin(phase * 3.0)
        if state in ("LISTENING", "SPEAKING"):
            pulse += level * 0.28
        core = RED if state == "ERROR" else (YELLOW if state == "THINKING" else CYAN)
        dim = "#23566e"
        self.canvas.create_oval(48, 48, 302, 218, outline="#123e55", width=1)
        self.canvas.create_oval(66, 62, 284, 202, outline=dim, width=2)
        self.canvas.create_oval(92, 80, 258, 184, outline="#2a7591", width=1)
        for i in range(56):
            a = phase * 0.75 + i * math.pi * 2 / 56
            wobble = math.sin(a * 2.0 + phase) * 8
            r = (67 + wobble) * pulse
            x = cx + math.cos(a) * r
            y = cy + math.sin(a) * r * 0.60
            size = 1.2 + (math.sin(a * 3.0) + 1) * 0.8
            self.canvas.create_oval(x-size, y-size, x+size, y+size, fill=core if i % 4 == 0 else dim, outline="")
        for i in range(12):
            a = -phase * 0.45 + i * math.pi / 6
            x1, y1 = cx + math.cos(a) * 32, cy + math.sin(a) * 20
            x2, y2 = cx + math.cos(a) * 112, cy + math.sin(a) * 67
            self.canvas.create_line(x1, y1, x2, y2, fill="#24637d", width=1)
        core_r = 16 * pulse
        self.canvas.create_oval(cx-core_r, cy-core_r, cx+core_r, cy+core_r, fill=core, outline="")
        self.canvas.create_oval(cx-core_r*.42, cy-core_r*.42, cx+core_r*.42, cy+core_r*.42, fill="#f5ffff", outline="")
        self.canvas.create_text(cx, 244, text="J  A  R  V  I  S", fill=core, font=("Segoe UI", 12, "bold"))
        self._orb_phase += speed
        self._orb_after = self.after(70, self._draw_orb)

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
            wake_words = ("jarvis", "джарвис")
            while self._voice_loop_running and self.settings.get("voice_enabled", True):
                try:
                    heard = voice.listen_for_phrase(
                        silence_seconds=0.55,
                        max_seconds=8.0,
                        start_timeout=2.0,
                        on_speech_start=on_speech_start,
                    )
                    if not heard or not self._voice_loop_running:
                        continue
                    normalized = " ".join(heard.lower().split())
                    command = None
                    for word in wake_words:
                        if normalized.startswith(word):
                            command = normalized[len(word):].strip(" ,.!")
                            break
                    if command is None:
                        continue
                    if not command:
                        self.events.put(("voice_status", "Jarvis активирован. Слушаю вас."))
                        command = voice.listen_for_phrase(
                            silence_seconds=0.55,
                            max_seconds=8.0,
                            start_timeout=4.0,
                            on_speech_start=on_speech_start,
                        )
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
                    self._set_visual_state("SPEAKING", 0.65)
                    self._append("JARVIS", reply)
                    self.busy = False
                    self.send_button.config(state="normal")
                    self.attach_button.config(state="normal")
                    self.status.config(text="● ONLINE", fg=GREEN)
                    self._set_visual_state("IDLE", 0.0)
                    if self.settings.get("tts_enabled", True):
                        threading.Thread(target=self._speak_reply, args=(reply,), daemon=True).start()
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
                    self._append("VOICE", "Ошибка: " + event[1])
                elif kind == "tts_error":
                    self._append("VOICE", "Ошибка TTS: " + event[1])
                    self.metrics["TTS"].config(fg=RED)
                elif kind == "agent_error":
                    self._set_visual_state("ERROR")
                    self.status.config(text="● ERROR", fg=RED)
                    self._append("SYSTEM", "Не удалось запустить ядро: " + event[1])
                    self.busy = False
                    self.send_button.config(state="normal")
        except queue.Empty:
            pass
        self.after(80, self._drain_events)

    def _speak_reply(self, text):
        try:
            self._set_visual_state("SPEAKING", 0.8)
            tts.speak_and_play(text)
            self._set_visual_state("IDLE", 0.0)
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
            p=Path(x["path"]); line=f"- {x['name']} | {x['mime']} | {x['size']} байт | путь: {p}"
            if p.suffix.lower() in {".txt",".md",".csv",".json",".xml",".log"} and x["size"]<=2*1024*1024:
                try: line+="\n  Содержимое:\n"+p.read_text(encoding="utf-8",errors="replace")[:120000]
                except OSError: pass
            parts.append(line)
        return "\n".join(parts)

    def _clear_attachments(self):
        self.attachments=[]; self._refresh_attachment_label()

    def send(self, text=None):
        if text is None: text=self.input.get()
        text=text.strip()
        if not text or self.agent is None or self.busy: return
        context=self._build_attachment_context()
        shown = text + (\n            "\n📎 " + ", ".join(x["name"] for x in self.attachments)\n            if self.attachments else ""\n        )\n        self.input.delete(0, "end")\n        self._append("ВЫ", shown)
        if self._handle_voice_setting_command(text):
            self._clear_attachments(); return
        prompt=text+("\n\n"+context if context else "")
        self.busy=True; self.send_button.config(state="disabled"); self.attach_button.config(state="disabled")
        self.status.config(text="● PROCESSING",fg=CYAN)
        def work():
            try: self.events.put(("reply",self.agent.handle(prompt).text))
            except Exception as exc: self.events.put(("reply","Ошибка: "+str(exc)))
        self._clear_attachments()
        threading.Thread(target=work,daemon=True).start()

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

    def _open_module_details(self, name, title, desc, enabled):
        items = []
        if name == "osint":
            items = [(n, d) for n, t, d, k in TOOLS if k == "intel"]
        elif name == "ps":
            try:
                import csv, subprocess
                out = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=8).stdout
                items = [(r[0], "PID " + r[1]) for r in csv.reader(out.splitlines()) if len(r) >= 2]
            except Exception:
                items = []
        elif name == "launch":
            try:
                import subprocess
                out = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-StartApps | Sort-Object Name | ForEach-Object { \"$($_.Name)|$($_.AppID)\" }"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=8).stdout
                items = [(a.strip(), b.strip()) for line in out.splitlines() if "|" in line for a, b in [line.split("|", 1)] if a.strip()]
            except Exception:
                items = []
        if not items: items = [(name, desc)]
        win = tk.Toplevel(self); win.title("JARVIS — " + title); win.configure(bg=BG); win.geometry("820x650")
        tk.Label(win, text=title, bg=BG, fg=CYAN, font=("Segoe UI", 18, "bold")).pack(anchor="w", padx=20, pady=(18, 4))
        tk.Label(win, text=("● АКТИВЕН" if enabled else "● ВЫКЛЮЧЕН"), bg=BG, fg=GREEN if enabled else RED, font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=20)
        tk.Label(win, text="Полный перечень: " + str(len(items)), bg=BG, fg=MUTED).pack(anchor="w", padx=20, pady=8)
        text = tk.Text(win, bg=PANEL, fg=TEXT, relief="flat", wrap="word", font=("Segoe UI", 10))
        text.pack(fill="both", expand=True, padx=20, pady=10)
        for item, detail in items: text.insert("end", item + "  —  " + detail + "\n")
        text.configure(state="disabled")
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
            card = tk.Frame(inner, bg=PANEL2, highlightbackground=LINE, highlightthickness=1, cursor="hand2")
            card.grid(row=row, column=col, sticky="ew", padx=8, pady=7)
            icon = tk.Canvas(card, width=70, height=70, bg=PANEL2, highlightthickness=0, cursor="hand2")
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
            state_label = tk.Label(body, text=("● АКТИВЕН" if enabled_var.get() else "● ВЫКЛЮЧЕН"), bg=PANEL2, fg=GREEN if enabled_var.get() else RED, font=("Segoe UI", 8, "bold"), cursor="hand2")
            state_label.pack(anchor="w", pady=(5, 0))
            state_label.bind("<Button-1>", lambda e, v=enabled_var, l=state_label: (v.set(not v.get()), l.config(text=("● АКТИВЕН" if v.get() else "● ВЫКЛЮЧЕН"), fg=GREEN if v.get() else RED)))
            card.bind("<Button-1>", lambda e, n=name, t=title, d=desc, v=enabled_var: self._open_module_details(n, t, d, v.get()))
            icon.bind("<Button-1>", lambda e, n=name, t=title, d=desc, v=enabled_var: self._open_module_details(n, t, d, v.get()))

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
        win.geometry("820x700")
        win.transient(self)
        win.grab_set()
        saved = self.settings
        fields = [
            ("Провайдер", "provider", os.environ.get("JARVIS_PROVIDER", saved.get("provider", DEFAULT_PROVIDER))),
            ("OpenAI-compatible URL", "url", os.environ.get("JARVIS_CHAT_URL", saved.get("url", DEFAULT_URL))),
            ("Модель", "model", os.environ.get("JARVIS_CHAT_MODEL", saved.get("model", ""))),
            ("API ключ", "api_key", os.environ.get("JARVIS_CHAT_KEY", saved.get("api_key", ""))),
            ("ElevenLabs API ключ", "elevenlabs_api_key", os.environ.get("JARVIS_ELEVENLABS_API_KEY", saved.get("elevenlabs_api_key", ""))),
            ("ElevenLabs Voice ID", "elevenlabs_voice_id", os.environ.get("JARVIS_ELEVENLABS_VOICE_ID", saved.get("elevenlabs_voice_id", "srULqtwUV9XZPg1ZCO5w"))),
            ("ElevenLabs модель", "elevenlabs_model", os.environ.get("JARVIS_ELEVENLABS_MODEL", saved.get("elevenlabs_model", "eleven_flash_v2_5"))),
        ]
        entries = {}
        for i, (label, name, value) in enumerate(fields):
            tk.Label(win, text=label, bg=PANEL, fg=MUTED).grid(row=i, column=0, sticky="w", padx=20, pady=(20 if i == 0 else 10, 4))
            entry = tk.Entry(win, bg=PANEL2, fg=TEXT, insertbackground=CYAN, relief="flat", width=60,
                             show="•" if name in {"api_key", "elevenlabs_api_key"} else "")
            entry.insert(0, value)
            entry.grid(row=i, column=1, padx=20, pady=(20 if i == 0 else 10, 4), ipady=7)
            entries[name] = entry
        voice_var = tk.BooleanVar(value=self.settings.get("voice_enabled", True))
        tts_var = tk.BooleanVar(value=self.settings.get("tts_enabled", True))
        ttk.Checkbutton(win, text="Включать голосовое прослушивание при старте", variable=voice_var).grid(row=7, column=1, sticky="w", padx=20, pady=8)
        ttk.Checkbutton(win, text="Озвучивать ответы JARVIS через TTS", variable=tts_var).grid(row=8, column=1, sticky="w", padx=20, pady=8)
        tk.Label(win, text="Настройки сохраняются в %APPDATA%\\JARVIS\\settings.json и применяются сразу после перезапуска ядра.",
                 bg=PANEL, fg=MUTED, wraplength=700, justify="left").grid(row=9, column=0, columnspan=2, padx=20, pady=14)
        def save():
            for name, entry in entries.items():
                self.settings[name] = entry.get().strip()
            self.settings["voice_enabled"] = bool(voice_var.get())
            self.settings["tts_enabled"] = bool(tts_var.get())
            self._apply_saved_settings()
            self._save_settings()
            win.destroy()
            self._reload_agent()
        ttk.Button(win, text="СОХРАНИТЬ И ПЕРЕЗАПУСТИТЬ", style="Accent.TButton", command=save).grid(row=10, column=1, sticky="e", padx=20, pady=10)

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