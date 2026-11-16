"""Simple read-only whale radar window for the BOTok desktop workspace."""
from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

from .whale_intel import WhaleIntelClient


BG = "#07111d"
PANEL = "#0c1c2c"
TEXT = "#eaf6ff"
MUTED = "#8da9bb"
CYAN = "#69e6f5"
GREEN = "#63e6a5"
RED = "#ff7185"


class WhaleRadarWindow(tk.Toplevel):
    """Shows top 200 Hyperliquid leaderboard accounts and wallet-attributed whale fills."""

    def __init__(self, master):
        super().__init__(master)
        self.title("BOTok — WHALE RADAR / TOP 200")
        self.geometry("1180x760")
        self.minsize(900, 600)
        self.configure(bg=BG)
        self._events: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._client: WhaleIntelClient | None = None
        self._thread: threading.Thread | None = None
        self._closed = False
        self._build()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(150, self._drain)
        self.start()

    def _build(self):
        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", padx=16, pady=(14, 8))
        tk.Label(header, text="WHALE RADAR · TOP 200", bg=BG, fg=CYAN,
                 font=("Segoe UI", 18, "bold")).pack(anchor="w")
        tk.Label(
            header,
            text="HYPERLIQUID PNL LEADERBOARD + COINLOBSTER WALLET-ATTRIBUTED WHALE FILLS · READ ONLY",
            bg=BG, fg=MUTED, font=("Consolas", 8, "bold"),
        ).pack(anchor="w", pady=(3, 0))

        controls = tk.Frame(self, bg=PANEL)
        controls.pack(fill="x", padx=16, pady=(0, 10))
        ttk.Button(controls, text="ОБНОВИТЬ", command=self.refresh).pack(side="left", padx=8, pady=8)
        ttk.Button(controls, text="ПАУЗА", command=self.pause).pack(side="left", padx=4, pady=8)
        ttk.Button(controls, text="ПРОДОЛЖИТЬ", command=self.start).pack(side="left", padx=4, pady=8)
        self.status = tk.StringVar(value="Подключение к публичным источникам…")
        tk.Label(controls, textvariable=self.status, bg=PANEL, fg=CYAN,
                 font=("Consolas", 9, "bold")).pack(side="left", padx=12)

        body = ttk.Notebook(self)
        body.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        accounts_tab = tk.Frame(body, bg=BG)
        trades_tab = tk.Frame(body, bg=BG)
        body.add(accounts_tab, text="ТОП-200 ТРЕЙДЕРОВ")
        body.add(trades_tab, text="СДЕЛКИ КИТОВ")

        self.accounts = self._tree(
            accounts_tab,
            ("rank", "address", "name", "pnl", "roi", "volume", "equity"),
            ("№", "Адрес", "Имя", "PnL USD", "ROI", "Оборот USD", "Equity USD"),
            (48, 330, 140, 110, 80, 120, 120),
        )
        self.trades = self._tree(
            trades_tab,
            ("time", "venue", "coin", "side", "price", "size", "wallet"),
            ("Время", "Биржа", "Актив", "Сторона", "Цена", "Объём USD", "Кошелёк"),
            (145, 115, 90, 80, 110, 120, 330),
        )
        self.note = tk.Label(
            self, bg=BG, fg=MUTED, justify="left", anchor="w",
            text="Источник рейтинга: публичный Hyperliquid leaderboard (окно 30 дней). "
                 "Сделки: публичный CoinLobster whale feed. Частота обновления зависит от API и ограничений источников.",
            font=("Segoe UI", 8), wraplength=1100,
        )
        self.note.pack(fill="x", padx=18, pady=(0, 10))

    @staticmethod
    def _tree(parent, columns, headings, widths):
        frame = tk.Frame(parent, bg=BG)
        frame.pack(fill="both", expand=True, padx=8, pady=8)
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=22)
        for column, heading, width in zip(columns, headings, widths):
            tree.heading(column, text=heading)
            tree.column(column, width=width, minwidth=55, stretch=True)
        yscroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        xscroll = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        return tree

    def refresh(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self.status.set("Обновляю рейтинг и ленту…")
        self._thread = threading.Thread(target=self._poll, daemon=True, name="botok-whales")
        self._thread.start()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="botok-whales")
        self._thread.start()

    def _poll(self):
        snapshot = WhaleIntelClient().fetch_snapshot(account_limit=200)
        self._events.put(("snapshot", snapshot))

    def _poll_loop(self):
        client = WhaleIntelClient()
        self._client = client
        while not self._stop.is_set():
            snapshot = client.fetch_snapshot(account_limit=200)
            self._events.put(("snapshot", snapshot))
            self._stop.wait(client.poll_interval_seconds)

    def pause(self):
        self._stop.set()
        self.status.set("ПАУЗА")

    def _drain(self):
        if self._closed:
            return
        try:
            while True:
                kind, payload = self._events.get_nowait()
                if kind != "snapshot":
                    continue
                for tree in (self.accounts, self.trades):
                    tree.delete(*tree.get_children())
                for item in payload.get("accounts", []):
                    self.accounts.insert("", "end", values=(
                        item.rank, item.address, item.name,
                        f"{item.pnl_usd:,.2f}", f"{item.roi * 100:.2f}%",
                        f"{item.volume_usd:,.2f}", f"{item.equity_usd:,.2f}",
                    ))
                combined = payload.get("hyperliquid_trades", []) + payload.get("exchange_trades", [])
                for item in combined:
                    self.trades.insert("", "end", values=(
                        item.timestamp, item.venue, item.coin, item.side,
                        f"{item.price:g}", f"{item.size_usd:,.2f}", item.address,
                    ))
                errors = payload.get("errors") or []
                count = len(payload.get("accounts", []))
                self.status.set(
                    f"Обновлено {time.strftime('%H:%M:%S')} · {count}/200 аккаунтов · "
                    f"{len(combined)} сделок" + (f" · {len(errors)} ошибок источника" if errors else "")
                )
                source = str(payload.get("source") or "Whale data providers")
                if errors:
                    self.note.configure(text=source + " · Ошибки источников: " + " | ".join(errors)[:750])
                else:
                    self.note.configure(text=source + " · Рейтинг Hyperliquid кэшируется на 15 минут; частота сделок зависит от провайдера. NANSEN_API_KEY включает Nansen API и более редкий опрос, чтобы контролировать расход кредитов.")
        except queue.Empty:
            pass
        if not self._closed:
            self.after(250, self._drain)

    def close(self):
        self._closed = True
        self._stop.set()
        try:
            self.destroy()
        except tk.TclError:
            pass
