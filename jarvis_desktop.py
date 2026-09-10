"""Native Windows desktop UI for JARVIS.

The GUI uses the real JarvisAgent directly, so every chat message, tool call,
memory action, and provider request goes through the same core as the CLI.
"""

import os
import queue
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from agent.runtime import build_agent

BG = "#05080f"
PANEL = "#0b111b"
PANEL2 = "#101a27"
LINE = "#1d3142"
CYAN = "#37d5ee"
TEXT = "#e7f6ff"
MUTED = "#7890a3"
GREEN = "#55e39b"


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

        self._build_style()
        self._build_ui()
        self._start_agent()
        self.after(80, self._drain_events)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _build_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TButton", background=PANEL2, foreground=TEXT,
                        bordercolor=LINE, padding=(12, 9), font=("Segoe UI", 10))
        style.map("TButton", background=[("active", "#153043")],
                  foreground=[("active", "white")])
        style.configure("Accent.TButton", background="#103744", foreground=CYAN,
                        bordercolor=CYAN)
        style.configure("TLabel", background=BG, foreground=TEXT,
                        font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background=BG, foreground=MUTED,
                        font=("Segoe UI", 9))
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL,
                        foreground=TEXT, bordercolor=LINE, rowheight=28)
        style.configure("Treeview.Heading", background=PANEL2, foreground=CYAN,
                        font=("Segoe UI", 9, "bold"))

    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = tk.Frame(self, bg=BG, height=72)
        header.grid(row=0, column=0, columnspan=3, sticky="ew")
        header.grid_columnconfigure(1, weight=1)
        tk.Label(header, text="JARVIS", bg=BG, fg=CYAN,
                 font=("Segoe UI", 24, "bold"), padx=24).grid(row=0, column=0, pady=18)
        tk.Label(header, text="PERSONAL AI SYSTEM  /  COMMAND CENTER", bg=BG,
                 fg=MUTED, font=("Segoe UI", 9, "bold")).grid(row=0, column=1, sticky="w")
        self.status = tk.Label(header, text="●  STARTING", bg=BG, fg=MUTED,
                               font=("Segoe UI", 10, "bold"), padx=24)
        self.status.grid(row=0, column=2, sticky="e")

        self._build_sidebar()
        self._build_center()
        self._build_right()

    def _build_sidebar(self):
        side = tk.Frame(self, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        side.grid(row=1, column=0, sticky="nsew", padx=(12, 6), pady=(0, 12))
        tk.Label(side, text="CONTROL", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 9, "bold"), padx=18, pady=18).pack(anchor="w")
        buttons = [
            ("◈  Система", self.show_system),
            ("◉  Память", self.show_memory),
            ("⌁  Инструменты", self.show_tools),
            ("⚙  Настройки", self.show_settings),
        ]
        for text, command in buttons:
            ttk.Button(side, text=text, command=command).pack(fill="x", padx=12, pady=5)

        tk.Label(side, text="QUICK ACTIONS", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 9, "bold"), padx=18, pady=18).pack(anchor="w")
        quick = [
            ("Статус системы", "/status"),
            ("Время", "/now"),
            ("Что ты умеешь?", "Что ты умеешь?"),
            ("Список инструментов", "/tools"),
        ]
        for label, command in quick:
            ttk.Button(side, text=label,
                       command=lambda c=command: self.send(c)).pack(fill="x", padx=12, pady=4)

    def _build_center(self):
        center = tk.Frame(self, bg=BG)
        center.grid(row=1, column=1, sticky="nsew", padx=6, pady=(0, 12))
        center.grid_rowconfigure(1, weight=1)
        center.grid_columnconfigure(0, weight=1)

        hud = tk.Frame(center, bg=BG, height=210)
        hud.grid(row=0, column=0, sticky="ew")
        hud.grid_propagate(False)
        self.canvas = tk.Canvas(hud, width=220, height=200, bg=BG, highlightthickness=0)
        self.canvas.pack(side="left", padx=28)
        self._draw_orb(0)
        self.hud_text = tk.Label(hud, text="Инициализация ядра…", bg=BG, fg=CYAN,
                                 font=("Segoe UI", 12, "bold"), justify="left")
        self.hud_text.pack(side="left", anchor="center")

        chat_frame = tk.Frame(center, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        chat_frame.grid(row=1, column=0, sticky="nsew")
        chat_frame.grid_rowconfigure(0, weight=1)
        chat_frame.grid_columnconfigure(0, weight=1)
        self.chat = tk.Text(chat_frame, bg=PANEL, fg=TEXT, insertbackground=CYAN,
                            relief="flat", wrap="word", padx=18, pady=16,
                            font=("Segoe UI", 11), state="disabled")
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
        self.send_button = ttk.Button(input_frame, text="SEND", style="Accent.TButton",
                                      command=self.send)
        self.send_button.grid(row=0, column=1, ipadx=10, ipady=3)

    def _build_right(self):
        right = tk.Frame(self, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        right.grid(row=1, column=2, sticky="nsew", padx=(6, 12), pady=(0, 12))
        tk.Label(right, text="LIVE STATUS", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 9, "bold"), padx=16, pady=18).pack(anchor="w")
        self.metrics = {}
        for name in ("Core", "AI Provider", "Memory", "Tools", "Voice"):
            row = tk.Frame(right, bg=PANEL)
            row.pack(fill="x", padx=16, pady=7)
            tk.Label(row, text=name, bg=PANEL, fg=MUTED,
                     font=("Segoe UI", 9)).pack(side="left")
            value = tk.Label(row, text="—", bg=PANEL, fg=CYAN,
                             font=("Segoe UI", 9, "bold"))
            value.pack(side="right")
            self.metrics[name] = value

        tk.Label(right, text="AGENT TOOLS", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 9, "bold"), padx=16, pady=18).pack(anchor="w")
        self.tools_label = tk.Label(right, text="Загрузка…", bg=PANEL, fg=TEXT,
                                    justify="left", wraplength=210, padx=16)
        self.tools_label.pack(anchor="w")

    def _draw_orb(self, phase):
        self.canvas.delete("all")
        cx, cy = 100, 98
        for r in (78, 62, 45, 28):
            self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r,
                                    outline="#1b7f99" if r > 30 else CYAN,
                                    width=1)
        self.canvas.create_oval(cx-10, cy-10, cx+10, cy+10,
                                fill=CYAN, outline="")
        self.canvas.create_text(cx, cy+118, text="J·A·R", fill=CYAN,
                                font=("Segoe UI", 16, "bold"))
        self.after(900, lambda: self._draw_orb((phase + 1) % 2))

    def _start_agent(self):
        def work():
            try:
                agent = build_agent()
                names = list(agent.tools.names())
                self.events.put(("ready", agent, names))
            except Exception as exc:
                self.events.put(("agent_error", str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def _drain_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "ready":
                    self.agent, self.tool_names = event[1], event[2]
                    provider = getattr(self.agent.provider, "name", "unknown").upper()
                    self.status.config(text="●  ONLINE", fg=GREEN)
                    self.hud_text.config(text="Ядро активно\nAI: " + provider)
                    self.metrics["Core"].config(text="ONLINE", fg=GREEN)
                    self.metrics["AI Provider"].config(text=provider)
                    self.metrics["Memory"].config(text="ACTIVE", fg=GREEN)
                    self.metrics["Tools"].config(text=str(len(self.tool_names)))
                    self.metrics["Voice"].config(text="READY")
                    self.tools_label.config(text="\n".join("• /" + n for n in self.tool_names))
                    self._append("JARVIS", "Система готова. Я подключён к реальному ядру и готов выполнять команды.")
                elif kind == "reply":
                    self._append("JARVIS", event[1])
                    self.busy = False
                    self.send_button.config(state="normal")
                    self.status.config(text="●  ONLINE", fg=GREEN)
                elif kind == "agent_error":
                    self.status.config(text="●  ERROR", fg="#ff647c")
                    self._append("SYSTEM", "Не удалось запустить ядро: " + event[1])
                    self.busy = False
                    self.send_button.config(state="normal")
        except queue.Empty:
            pass
        self.after(80, self._drain_events)

    def _append(self, who, text):
        self.chat.configure(state="normal")
        self.chat.insert("end", f"{who}\n", "who")
        self.chat.insert("end", text + "\n\n", "body")
        self.chat.tag_configure("who", foreground=CYAN, font=("Segoe UI", 9, "bold"))
        self.chat.tag_configure("body", foreground=TEXT)
        self.chat.see("end")
        self.chat.configure(state="disabled")

    def send(self, text=None):
        if text is None:
            text = self.input.get()
        text = text.strip()
        if not text or self.agent is None or self.busy:
            return
        self.input.delete(0, "end")
        self._append("ВЫ", text)
        self.busy = True
        self.send_button.config(state="disabled")
        self.status.config(text="●  PROCESSING", fg=CYAN)

        def work():
            try:
                result = self.agent.handle(text)
                reply = result.text
                if result.needs_confirmation:
                    # Confirmation is handled explicitly in the desktop UI.
                    reply = "ТРЕБУЕТСЯ ПОДТВЕРЖДЕНИЕ\n\n" + reply
                    self.events.put(("reply", reply))
                else:
                    self.events.put(("reply", reply))
            except Exception as exc:
                self.events.put(("reply", "Ошибка: " + str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def show_system(self):
        self.send("/status")

    def show_memory(self):
        self.send("/recall")

    def show_tools(self):
        if not self.tool_names:
            self.send("/tools")
            return
        self._append("JARVIS", "Доступные инструменты:\n" + "\n".join("• /" + n for n in self.tool_names))

    def show_settings(self):
        win = tk.Toplevel(self)
        win.title("JARVIS — Настройки")
        win.configure(bg=PANEL)
        win.geometry("520x360")
        win.transient(self)
        win.grab_set()
        fields = [
            ("Cloud URL", "JARVIS_CLOUD_URL"),
            ("Cloud model", "JARVIS_CLOUD_MODEL"),
            ("Cloud key", "JARVIS_CLOUD_KEY"),
        ]
        entries = {}
        for i, (label, env) in enumerate(fields):
            tk.Label(win, text=label, bg=PANEL, fg=MUTED,
                     font=("Segoe UI", 9)).grid(row=i, column=0, sticky="w", padx=20, pady=(18 if i == 0 else 10, 4))
            entry = tk.Entry(win, bg=PANEL2, fg=TEXT, insertbackground=CYAN,
                             relief="flat", width=46, show="•" if "KEY" in env else "")
            entry.insert(0, os.environ.get(env, ""))
            entry.grid(row=i, column=1, padx=20, pady=(18 if i == 0 else 10, 4), ipady=7)
            entries[env] = entry
        tk.Label(win, text="Ключ не показывается и не сохраняется в проект.",
                 bg=PANEL, fg=MUTED).grid(row=3, column=0, columnspan=2, padx=20, pady=12)

        def apply():
            for env, entry in entries.items():
                value = entry.get().strip()
                if value:
                    os.environ[env] = value
                elif env in os.environ:
                    del os.environ[env]
            win.destroy()
            self._reload_agent()

        ttk.Button(win, text="Применить и перезапустить ядро", style="Accent.TButton",
                   command=apply).grid(row=4, column=0, columnspan=2, pady=18, ipadx=12)

    def _reload_agent(self):
        self.status.config(text="●  RESTARTING", fg=CYAN)
        self.agent = None
        self._start_agent()

    def _close(self):
        self.destroy()


if __name__ == "__main__":
    JarvisDesktop().mainloop()
