"""Native Windows desktop UI for JARVIS.

The GUI talks to the real JarvisAgent. Settings persist between launches;
the cloud API key is stored in Windows Credential Manager when keyring is
available. Voice input records from the default microphone and transcribes
Russian speech through the voice backend.
"""

import json
import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from agent.runtime import build_agent
from agent import voice

BG = "#05080f"
PANEL = "#0b111b"
PANEL2 = "#101a27"
LINE = "#1d3142"
CYAN = "#37d5ee"
TEXT = "#e7f6ff"
MUTED = "#7890a3"
GREEN = "#55e39b"
RED = "#ff647c"
SERVICE = "JARVIS Desktop"
APP_DIR = Path(os.environ.get("APPDATA", Path.home())) / "JARVIS"
SETTINGS_FILE = APP_DIR / "settings.json"
DEFAULT_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o-mini"


def _load_saved_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _load_key() -> str:
    try:
        import keyring
        return keyring.get_password(SERVICE, "cloud_api_key") or ""
    except Exception:
        return ""


def _save_key(value: str) -> None:
    try:
        import keyring
        if value:
            keyring.set_password(SERVICE, "cloud_api_key", value)
        else:
            try:
                keyring.delete_password(SERVICE, "cloud_api_key")
            except Exception:
                pass
    except Exception:
        if value:
            os.environ["JARVIS_CLOUD_KEY"] = value


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
        self._recording = False
        self._apply_saved_settings()
        self._build_style()
        self._build_ui()
        self._start_agent()
        self.after(80, self._drain_events)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _apply_saved_settings(self):
        saved = _load_saved_settings()
        url = saved.get("url") or os.environ.get("JARVIS_CLOUD_URL") or DEFAULT_URL
        model = saved.get("model") or os.environ.get("JARVIS_CLOUD_MODEL") or DEFAULT_MODEL
        key = _load_key() or os.environ.get("JARVIS_CLOUD_KEY", "")
        os.environ["JARVIS_CLOUD_URL"] = url
        os.environ["JARVIS_CLOUD_MODEL"] = model
        if key:
            os.environ["JARVIS_CLOUD_KEY"] = key

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
        for text, command in [("◈  Система", self.show_system), ("◉  Память", self.show_memory), ("⌁  Инструменты", self.show_tools), ("⚙  Настройки", self.show_settings)]:
            ttk.Button(side, text=text, command=command).pack(fill="x", padx=12, pady=5)
        tk.Label(side, text="QUICK ACTIONS", bg=PANEL, fg=MUTED, font=("Segoe UI", 9, "bold"), padx=18, pady=18).pack(anchor="w")
        for label, command in [("Статус системы", "/status"), ("Время", "/now"), ("Что ты умеешь?", "Что ты умеешь?"), ("Список инструментов", "/tools")]:
            ttk.Button(side, text=label, command=lambda c=command: self.send(c)).pack(fill="x", padx=12, pady=4)

    def _build_center(self):
        center = tk.Frame(self, bg=BG); center.grid(row=1, column=1, sticky="nsew", padx=6, pady=(0, 12))
        center.grid_rowconfigure(1, weight=1); center.grid_columnconfigure(0, weight=1)
        hud = tk.Frame(center, bg=BG, height=210); hud.grid(row=0, column=0, sticky="ew"); hud.grid_propagate(False)
        self.canvas = tk.Canvas(hud, width=220, height=200, bg=BG, highlightthickness=0); self.canvas.pack(side="left", padx=28); self._draw_orb()
        self.hud_text = tk.Label(hud, text="Инициализация ядра…", bg=BG, fg=CYAN, font=("Segoe UI", 12, "bold"), justify="left"); self.hud_text.pack(side="left", anchor="center")
        chat_frame = tk.Frame(center, bg=PANEL, highlightbackground=LINE, highlightthickness=1); chat_frame.grid(row=1, column=0, sticky="nsew")
        chat_frame.grid_rowconfigure(0, weight=1); chat_frame.grid_columnconfigure(0, weight=1)
        self.chat = tk.Text(chat_frame, bg=PANEL, fg=TEXT, insertbackground=CYAN, relief="flat", wrap="word", padx=18, pady=16, font=("Segoe UI", 11), state="disabled")
        self.chat.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(chat_frame, command=self.chat.yview); scroll.grid(row=0, column=1, sticky="ns"); self.chat.configure(yscrollcommand=scroll.set)
        input_frame = tk.Frame(center, bg=BG); input_frame.grid(row=2, column=0, sticky="ew", pady=(10, 0)); input_frame.grid_columnconfigure(0, weight=1)
        self.input = tk.Entry(input_frame, bg=PANEL2, fg=TEXT, insertbackground=CYAN, relief="flat", font=("Segoe UI", 11)); self.input.grid(row=0, column=0, sticky="ew", ipady=12, padx=(0, 8)); self.input.bind("<Return>", lambda _e: self.send())
        self.voice_button = ttk.Button(input_frame, text="🎙 ГОЛОС", command=self.start_voice); self.voice_button.grid(row=0, column=1, padx=(0, 8), ipady=3)
        self.send_button = ttk.Button(input_frame, text="SEND", style="Accent.TButton", command=self.send); self.send_button.grid(row=0, column=2, ipadx=10, ipady=3)

    def _build_right(self):
        right = tk.Frame(self, bg=PANEL, highlightbackground=LINE, highlightthickness=1); right.grid(row=1, column=2, sticky="nsew", padx=(6, 12), pady=(0, 12))
        tk.Label(right, text="LIVE STATUS", bg=PANEL, fg=MUTED, font=("Segoe UI", 9, "bold"), padx=16, pady=18).pack(anchor="w")
        self.metrics = {}
        for name in ("Core", "AI Provider", "Memory", "Tools", "Voice"):
            row = tk.Frame(right, bg=PANEL); row.pack(fill="x", padx=16, pady=7)
            tk.Label(row, text=name, bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(side="left")
            value = tk.Label(row, text="—", bg=PANEL, fg=CYAN, font=("Segoe UI", 9, "bold")); value.pack(side="right"); self.metrics[name] = value
        tk.Label(right, text="AGENT TOOLS", bg=PANEL, fg=MUTED, font=("Segoe UI", 9, "bold"), padx=16, pady=18).pack(anchor="w")
        self.tools_label = tk.Label(right, text="Загрузка…", bg=PANEL, fg=TEXT, justify="left", wraplength=210, padx=16); self.tools_label.pack(anchor="w")

    def _draw_orb(self):
        self.canvas.delete("all"); cx, cy = 100, 98
        for r in (78, 62, 45, 28): self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r, outline="#1b7f99" if r > 30 else CYAN, width=1)
        self.canvas.create_oval(cx-10, cy-10, cx+10, cy+10, fill=CYAN, outline=""); self.canvas.create_text(cx, cy+118, text="J·A·R", fill=CYAN, font=("Segoe UI", 16, "bold"))

    def _start_agent(self):
        def work():
            try: self.events.put(("ready", build_agent(), None))
            except Exception as exc: self.events.put(("agent_error", str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def _drain_events(self):
        try:
            while True:
                event = self.events.get_nowait(); kind = event[0]
                if kind == "ready":
                    self.agent = event[1]; self.tool_names = list(self.agent.tools.names()); provider = getattr(self.agent.provider, "name", "unknown").upper()
                    self.status.config(text="● ONLINE", fg=GREEN); self.hud_text.config(text="Ядро активно\nAI: " + provider)
                    self.metrics["Core"].config(text="ONLINE", fg=GREEN); self.metrics["AI Provider"].config(text=provider); self.metrics["Memory"].config(text="ACTIVE", fg=GREEN); self.metrics["Tools"].config(text=str(len(self.tool_names)))
                    voice_ok = voice.available(); self.metrics["Voice"].config(text="READY" if voice_ok else "NOT INSTALLED", fg=GREEN if voice_ok else RED)
                    self.tools_label.config(text="\n".join("• /" + n for n in self.tool_names)); self._append("JARVIS", "Система готова. Я подключён к реальному ядру и готов выполнять команды.")
                elif kind == "reply":
                    self._append("JARVIS", event[1]); self.busy = False; self.send_button.config(state="normal"); self.status.config(text="● ONLINE", fg=GREEN)
                elif kind == "voice_text":
                    self.voice_button.config(state="normal", text="🎙 ГОЛОС"); self.input.delete(0, "end"); self.input.insert(0, event[1]); self.send(event[1])
                elif kind == "voice_error":
                    self.voice_button.config(state="normal", text="🎙 ГОЛОС"); self._append("VOICE", "Ошибка: " + event[1])
                elif kind == "agent_error":
                    self.status.config(text="● ERROR", fg=RED); self._append("SYSTEM", "Не удалось запустить ядро: " + event[1]); self.busy = False; self.send_button.config(state="normal")
        except queue.Empty: pass
        self.after(80, self._drain_events)

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
        if self._recording or self.agent is None: return
        if not voice.available(): self._append("VOICE", "Голосовой ввод недоступен. Пересоберите приложение из актуальной foundation-ветки."); return
        self._recording = True; self.voice_button.config(state="disabled", text="🎙 СЛУШАЮ…"); self._append("VOICE", "Говорите сейчас. Запись длится до 7 секунд…")
        def work():
            try: self.events.put(("voice_text", voice.record_and_transcribe(7)))
            except Exception as exc: self.events.put(("voice_error", str(exc)))
            finally: self._recording = False
        threading.Thread(target=work, daemon=True).start()

    def show_system(self): self.send("/status")
    def show_memory(self): self.send("/recall")
    def show_tools(self): self._append("JARVIS", "Доступные инструменты:\n" + "\n".join("• /" + n for n in self.tool_names))

    def show_settings(self):
        win = tk.Toplevel(self); win.title("JARVIS — Настройки"); win.configure(bg=PANEL); win.geometry("620x400"); win.transient(self); win.grab_set()
        fields = [("Cloud URL", "url", os.environ.get("JARVIS_CLOUD_URL", DEFAULT_URL)), ("Cloud model", "model", os.environ.get("JARVIS_CLOUD_MODEL", DEFAULT_MODEL)), ("Cloud key", "key", os.environ.get("JARVIS_CLOUD_KEY", ""))]; entries = {}
        for i, (label, name, value) in enumerate(fields):
            tk.Label(win, text=label, bg=PANEL, fg=MUTED).grid(row=i, column=0, sticky="w", padx=20, pady=(20 if i == 0 else 10, 4))
            entry = tk.Entry(win, bg=PANEL2, fg=TEXT, insertbackground=CYAN, relief="flat", width=52, show="•" if name == "key" else ""); entry.insert(0, value); entry.grid(row=i, column=1, padx=20, pady=(20 if i == 0 else 10, 4), ipady=7); entries[name] = entry
        tk.Label(win, text="URL и модель сохраняются в %APPDATA%\\JARVIS. API-ключ хранится в Windows Credential Manager.", bg=PANEL, fg=MUTED, wraplength=560, justify="left").grid(row=3, column=0, columnspan=2, padx=20, pady=14)
        def apply():
            url = entries["url"].get().strip() or DEFAULT_URL; model = entries["model"].get().strip() or DEFAULT_MODEL; key = entries["key"].get().strip()
            os.environ["JARVIS_CLOUD_URL"] = url; os.environ["JARVIS_CLOUD_MODEL"] = model
            if key: os.environ["JARVIS_CLOUD_KEY"] = key
            elif "JARVIS_CLOUD_KEY" in os.environ: del os.environ["JARVIS_CLOUD_KEY"]
            try:
                APP_DIR.mkdir(parents=True, exist_ok=True); SETTINGS_FILE.write_text(json.dumps({"url": url, "model": model}, ensure_ascii=False, indent=2), encoding="utf-8"); _save_key(key)
            except OSError as exc: messagebox.showerror("JARVIS", f"Не удалось сохранить настройки: {exc}", parent=win); return
            win.destroy(); self._reload_agent()
        ttk.Button(win, text="Сохранить и подключить AI", style="Accent.TButton", command=apply).grid(row=4, column=0, columnspan=2, pady=18, ipadx=12)

    def _reload_agent(self):
        self.status.config(text="● RESTARTING", fg=CYAN); self.agent = None; self._start_agent()
    def _close(self): self.destroy()


if __name__ == "__main__":
    JarvisDesktop().mainloop()
