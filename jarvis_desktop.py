"""Native Windows desktop UI for JARVIS using free/local providers."""

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

BG = "#05080f"
PANEL = "#0b111b"
PANEL2 = "#101a27"
LINE = "#1d3142"
CYAN = "#37d5ee"
TEXT = "#e7f6ff"
MUTED = "#7890a3"
GREEN = "#55e39b"
RED = "#ff647c"
APP_DIR = Path(os.environ.get("APPDATA", Path.home())) / "JARVIS"
SETTINGS_FILE = APP_DIR / "settings.json"
DEFAULT_PROVIDER = "openai-compatible"
DEFAULT_URL = "http://127.0.0.1:11434/v1/chat/completions"


def _load_saved_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


class JarvisDesktop(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("JARVIS — Personal AI System")
        self.geometry("1220x760")
        self.minsize(980, 620)
        self.configure(bg=BG)
        self.agent = None
        self.busy = False
        self.events = queue.Queue()
        self.tool_names = []
        self._voice_loop_running = False
        self._orb_phase = 0.0
        self._orb_after = None
        self._apply_saved_settings()
        self._build_style()
        self._build_ui()
        self._start_agent()
        self.after(80, self._drain_events)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _apply_saved_settings(self):
        saved = _load_saved_settings()
        provider = saved.get("provider") or os.environ.get("JARVIS_PROVIDER") or DEFAULT_PROVIDER
        url = saved.get("url") or os.environ.get("JARVIS_CHAT_URL") or DEFAULT_URL
        model = saved.get("model") or os.environ.get("JARVIS_CHAT_MODEL") or ""
        api_key = saved.get("api_key") or os.environ.get("JARVIS_CHAT_KEY") or ""
        os.environ["JARVIS_PROVIDER"] = provider
        os.environ["JARVIS_CHAT_URL"] = url
        os.environ["JARVIS_CHAT_KEY"] = api_key
        if model:
            os.environ["JARVIS_CHAT_MODEL"] = model

    def _build_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TButton", background=PANEL2, foreground=TEXT, bordercolor=LINE, padding=(12, 9), font=("Segoe UI", 10))
        style.map("TButton", background=[("active", "#153043")], foreground=[("active", "white")])
        style.configure("Accent.TButton", background="#103744", foreground=CYAN, bordercolor=CYAN)

    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)
        header = tk.Frame(self, bg=BG, height=72)
        header.grid(row=0, column=0, columnspan=3, sticky="ew")
        header.grid_columnconfigure(1, weight=1)
        tk.Label(header, text="JARVIS", bg=BG, fg=CYAN, font=("Segoe UI", 24, "bold"), padx=24).grid(row=0, column=0, pady=18)
        tk.Label(header, text="PERSONAL AI SYSTEM  /  COMMAND CENTER", bg=BG, fg=MUTED, font=("Segoe UI", 9, "bold")).grid(row=0, column=1, sticky="w")
        self.status = tk.Label(header, text="● STARTING", bg=BG, fg=MUTED, font=("Segoe UI", 10, "bold"), padx=24)
        self.status.grid(row=0, column=2, sticky="e")
        self._build_sidebar(); self._build_center(); self._build_right()

    def _build_sidebar(self):
        side = tk.Frame(self, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        side.grid(row=1, column=0, sticky="nsew", padx=(12, 6), pady=(0, 12))
        tk.Label(side, text="CONTROL", bg=PANEL, fg=MUTED, font=("Segoe UI", 9, "bold"), padx=18, pady=18).pack(anchor="w")
        ttk.Button(side, text="⌁  Инструменты", command=self.show_tools).pack(fill="x", padx=12, pady=5)
        ttk.Button(side, text="⚙  Настройки", command=self.show_settings).pack(fill="x", padx=12, pady=5)

    def _build_center(self):
        center = tk.Frame(self, bg=BG); center.grid(row=1, column=1, sticky="nsew", padx=6, pady=(0, 12))
        center.grid_rowconfigure(1, weight=1); center.grid_columnconfigure(0, weight=1)
        hud = tk.Frame(center, bg=BG, height=250); hud.grid(row=0, column=0, sticky="ew"); hud.grid_propagate(False)
        self.canvas = tk.Canvas(hud, width=300, height=235, bg=BG, highlightthickness=0); self.canvas.pack(side="left", padx=12); self._draw_orb()
        self.hud_text = tk.Label(hud, text="Инициализация ядра…", bg=BG, fg=CYAN, font=("Segoe UI", 12, "bold"), justify="left"); self.hud_text.pack(side="left", anchor="center")
        chat_frame = tk.Frame(center, bg=PANEL, highlightbackground=LINE, highlightthickness=1); chat_frame.grid(row=1, column=0, sticky="nsew")
        chat_frame.grid_rowconfigure(0, weight=1); chat_frame.grid_columnconfigure(0, weight=1)
        self.chat = tk.Text(chat_frame, bg=PANEL, fg=TEXT, insertbackground=CYAN, relief="flat", wrap="word", padx=18, pady=16, font=("Segoe UI", 11), state="disabled")
        self.chat.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(chat_frame, command=self.chat.yview); scroll.grid(row=0, column=1, sticky="ns"); self.chat.configure(yscrollcommand=scroll.set)
        input_frame = tk.Frame(center, bg=BG); input_frame.grid(row=2, column=0, sticky="ew", pady=(10, 0)); input_frame.grid_columnconfigure(0, weight=1)
        self.input = tk.Entry(input_frame, bg=PANEL2, fg=TEXT, insertbackground=CYAN, relief="flat", font=("Segoe UI", 11)); self.input.grid(row=0, column=0, sticky="ew", ipady=12, padx=(0, 8)); self.input.bind("<Return>", lambda _e: self.send())
        self.voice_button = ttk.Button(input_frame, text="🎙 АВТО", command=self.start_voice); self.voice_button.grid(row=0, column=1, padx=(0, 8), ipady=3)
        self.send_button = ttk.Button(input_frame, text="SEND", style="Accent.TButton", command=self.send); self.send_button.grid(row=0, column=2, ipadx=10, ipady=3)

    def _build_right(self):
        right = tk.Frame(self, bg=PANEL, highlightbackground=LINE, highlightthickness=1); right.grid(row=1, column=2, sticky="nsew", padx=(6, 12), pady=(0, 12))
        tk.Label(right, text="LIVE STATUS", bg=PANEL, fg=MUTED, font=("Segoe UI", 9, "bold"), padx=16, pady=18).pack(anchor="w")
        self.metrics = {}
        for name in ("Core", "AI Provider", "Memory", "Tools", "Voice"):
            row = tk.Frame(right, bg=PANEL); row.pack(fill="x", padx=16, pady=7)
            tk.Label(row, text=name, bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(side="left")
            value = tk.Label(row, text="—", bg=PANEL, fg=CYAN, font=("Segoe UI", 9, "bold")); value.pack(side="right"); self.metrics[name] = value

    def _draw_orb(self):
        self.canvas.delete("all")
        cx, cy = 150, 112
        phase = self._orb_phase
        # Perspective rings create a lightweight 3D reactor without external graphics libraries.
        for rx, ry, offset in ((104, 104, 0), (82, 48, 0.9), (82, 48, -0.9), (58, 28, 1.8)):
            a = phase + offset
            self.canvas.create_oval(cx-rx, cy-ry, cx+rx, cy+ry, outline="#1b6f88", width=1)
            dx = math.cos(a) * rx * 0.82
            dy = math.sin(a) * ry * 0.82
            self.canvas.create_oval(cx+dx-3, cy+dy-3, cx+dx+3, cy+dy+3, fill=CYAN, outline="")
        for i in range(20):
            a = phase * 1.7 + i * (math.pi * 2 / 20)
            z = (math.sin(a) + 1) / 2
            r = 72 + 24 * z
            x = cx + math.cos(a) * r
            y = cy + math.sin(a) * r * 0.55
            size = 1 + int(3 * z)
            self.canvas.create_oval(x-size, y-size, x+size, y+size, fill="#37d5ee", outline="")
        pulse = 12 + 4 * (math.sin(phase * 2) + 1)
        self.canvas.create_oval(cx-pulse, cy-pulse, cx+pulse, cy+pulse, fill=CYAN, outline="")
        self.canvas.create_text(cx, cy+126, text="J·A·R", fill=CYAN, font=("Segoe UI", 16, "bold"))
        self._orb_phase += 0.055
        self._orb_after = self.after(40, self._draw_orb)

    def _start_agent(self):
        def work():
            try: self.events.put(("ready", build_agent()))
            except Exception as exc: self.events.put(("agent_error", str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def _start_voice_loop(self):
        if self._voice_loop_running or not voice.available(): return
        self._voice_loop_running = True; self.voice_button.config(text="🎙 АВТО СЛУШАЮ")
        def on_speech_start():
            if tts.is_playing():
                tts.stop(); self.events.put(("voice_status", "Перебивание: голос JARVIS остановлен, слушаю вас."))
        def work():
            while self._voice_loop_running:
                try:
                    command = voice.listen_for_wake_and_command(on_speech_start=on_speech_start)
                    if command and self._voice_loop_running: self.events.put(("voice_text", command))
                except Exception as exc:
                    self.events.put(("voice_error", str(exc))); break
            self._voice_loop_running = False
        threading.Thread(target=work, daemon=True).start()

    def _drain_events(self):
        try:
            while True:
                event = self.events.get_nowait(); kind = event[0]
                if kind == "ready":
                    self.agent = event[1]; self.tool_names = list(self.agent.tools.names()); provider = getattr(self.agent.provider, "name", "unknown").upper()
                    self.status.config(text="● ONLINE", fg=GREEN); self.hud_text.config(text="Ядро активно\nAI: " + provider)
                    self.metrics["Core"].config(text="ONLINE", fg=GREEN); self.metrics["AI Provider"].config(text=provider); self.metrics["Memory"].config(text="ACTIVE", fg=GREEN); self.metrics["Tools"].config(text=str(len(self.tool_names)))
                    voice_ok = voice.available(); tts_engine = tts.current_engine()
                    self.metrics["Voice"].config(text=("STT + " + tts_engine.upper()) if voice_ok else tts_engine.upper(), fg=GREEN if tts_engine != "off" else RED)
                    self._append("JARVIS", "Система готова.")
                    if voice_ok: self._start_voice_loop()
                elif kind == "reply":
                    reply = event[1]; self._append("JARVIS", reply); self.busy = False; self.send_button.config(state="normal"); self.status.config(text="● ONLINE", fg=GREEN)
                    threading.Thread(target=self._speak_reply, args=(reply,), daemon=True).start()
                elif kind == "voice_text":
                    if self.busy: continue
                    self.input.delete(0, "end"); self.input.insert(0, event[1]); self.send(event[1])
                elif kind == "voice_status": self._append("VOICE", event[1])
                elif kind == "voice_error": self._append("VOICE", "Ошибка: " + event[1])
                elif kind == "tts_error": self._append("VOICE", "Ошибка TTS: " + event[1]); self.metrics["Voice"].config(fg=RED)
                elif kind == "agent_error":
                    self.status.config(text="● ERROR", fg=RED); self._append("SYSTEM", "Не удалось запустить ядро: " + event[1]); self.busy = False; self.send_button.config(state="normal")
        except queue.Empty: pass
        self.after(80, self._drain_events)

    def _speak_reply(self, text):
        try: tts.speak_and_play(text)
        except Exception as exc: self.events.put(("tts_error", str(exc)))

    def _append(self, who, text):
        self.chat.configure(state="normal"); self.chat.insert("end", f"{who}\n", "who"); self.chat.insert("end", text + "\n\n", "body")
        self.chat.tag_configure("who", foreground=CYAN, font=("Segoe UI", 9, "bold")); self.chat.tag_configure("body", foreground=TEXT); self.chat.see("end"); self.chat.configure(state="disabled")

    def send(self, text=None):
        if text is None: text = self.input.get()
        text = text.strip()
        if not text or self.agent is None or self.busy: return
        self.input.delete(0, "end"); self._append("ВЫ", text); self.busy = True; self.send_button.config(state="disabled"); self.status.config(text="● PROCESSING", fg=CYAN)
        def work():
            try: self.events.put(("reply", self.agent.handle(text).text))
            except Exception as exc: self.events.put(("reply", "Ошибка: " + str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def start_voice(self):
        if self._voice_loop_running:
            self._append("VOICE", "Автоматическое слушание уже включено."); return
        self._start_voice_loop()
        if not self._voice_loop_running: self._append("VOICE", "Голосовой ввод недоступен.")

    def show_tools(self): self._append("JARVIS", "Доступные инструменты:\n" + "\n".join("• /" + n for n in self.tool_names))

    def show_settings(self):
        win = tk.Toplevel(self); win.title("JARVIS — Настройки"); win.configure(bg=PANEL); win.geometry("720x430"); win.transient(self); win.grab_set()
        saved = _load_saved_settings()
        fields = [
            ("Провайдер", "provider", os.environ.get("JARVIS_PROVIDER", saved.get("provider", DEFAULT_PROVIDER))),
            ("OpenAI-compatible URL", "url", os.environ.get("JARVIS_CHAT_URL", saved.get("url", DEFAULT_URL))),
            ("Модель", "model", os.environ.get("JARVIS_CHAT_MODEL", saved.get("model", ""))),
            ("API ключ", "api_key", os.environ.get("JARVIS_CHAT_KEY", saved.get("api_key", ""))),
        ]
        entries = {}
        for i, (label, name, value) in enumerate(fields):
            tk.Label(win, text=label, bg=PANEL, fg=MUTED).grid(row=i, column=0, sticky="w", padx=20, pady=(20 if i == 0 else 10, 4))
            entry = tk.Entry(win, bg=PANEL2, fg=TEXT, insertbackground=CYAN, relief="flat", width=58, show="•" if name == "api_key" else "")
            entry.insert(0, value); entry.grid(row=i, column=1, padx=20, pady=(20 if i == 0 else 10, 4), ipady=7); entries[name] = entry
        tk.Label(win, text="Для OpenRouter/OpenAI-compatible укажи полный chat-completions URL и API ключ. Для локальных Ollama/llama.cpp/LM Studio ключ можно оставить пустым.", bg=PANEL, fg=MUTED, wraplength=660, justify="left").grid(row=4, column=0, columnspan=2, padx=20, pady=14)
        def apply():
            provider = entries["provider"].get().strip() or DEFAULT_PROVIDER
            url = entries["url"].get().strip() or DEFAULT_URL
            model = entries["model"].get().strip()
            api_key = entries["api_key"].get().strip()
            os.environ["JARVIS_PROVIDER"] = provider; os.environ["JARVIS_CHAT_URL"] = url; os.environ["JARVIS_CHAT_KEY"] = api_key
            if model: os.environ["JARVIS_CHAT_MODEL"] = model
            else: os.environ.pop("JARVIS_CHAT_MODEL", None)
            try:
                APP_DIR.mkdir(parents=True, exist_ok=True)
                SETTINGS_FILE.write_text(json.dumps({"provider": provider, "url": url, "model": model, "api_key": api_key}, ensure_ascii=False, indent=2), encoding="utf-8")
            except OSError as exc:
                messagebox.showerror("JARVIS", f"Не удалось сохранить настройки: {exc}", parent=win); return
            win.destroy(); self._reload_agent()
        ttk.Button(win, text="Сохранить и подключить AI", style="Accent.TButton", command=apply).grid(row=5, column=0, columnspan=2, pady=18, ipadx=12)

    def _reload_agent(self): self.status.config(text="● RESTARTING", fg=CYAN); self.agent = None; self._start_agent()

    def _close(self):
        self._voice_loop_running = False
        tts.stop()
        if self._orb_after:
            try: self.after_cancel(self._orb_after)
            except tk.TclError: pass
        self.destroy()


if __name__ == "__main__":
    JarvisDesktop().mainloop()
