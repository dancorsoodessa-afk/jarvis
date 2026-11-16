"""Enhanced BOTok trading workspace layered over the stable paper dashboard."""

from __future__ import annotations

import json
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk
from collections import deque

from .dashboard import BG, CYAN, GREEN, MUTED, PANEL, RED, TEXT, CryptoDashboard


class BOTokDashboard(CryptoDashboard):
    """Live price/depth visualization with optional Nansen MCP status."""

    def _build_ui(self):
        super()._build_ui()
        self.title("BOTok — LIVE MARKET / PAPER TRADING")
        self.geometry("1320x850")
        self.minsize(1000, 700)
        self._chart_queue = queue.Queue()
        self._nansen_api_key = self._load_nansen_key()
        self._coinglass_api_key = self._load_coinglass_key()
        self._whale_refresh_scheduled = False
        self._price_history = deque(maxlen=240)
        self._chart_symbol = "BTC-USDT-SWAP"
        self._last_price = None
        self._bid_volume = 0.0
        self._ask_volume = 0.0
        body = self.log.master
        # The base dashboard keeps a lightweight fallback chart for standalone use;
        # BOTok replaces it with the richer price/depth visualization below.
        self.chart.grid_forget()
        self.log.grid_forget()
        scrollbars = body.grid_slaves(row=0, column=1)
        chart_panel = tk.Frame(body, bg=BG)
        chart_panel.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        body.grid_rowconfigure(0, weight=4)
        body.grid_rowconfigure(1, weight=1)
        self.log.grid(row=1, column=0, sticky="nsew")
        for scrollbar in scrollbars:
            scrollbar.grid(row=1, column=1, sticky="ns")
        chart_panel.grid_columnconfigure(0, weight=4)
        chart_panel.grid_columnconfigure(1, weight=1)
        chart_panel.grid_rowconfigure(1, weight=1)

        header = tk.Frame(chart_panel, bg=BG)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        self.live_symbol_var = tk.StringVar(value="BTC-USDT-SWAP")
        tk.Label(header, textvariable=self.live_symbol_var, bg=BG, fg=CYAN,
                 font=("Segoe UI", 12, "bold")).pack(side="left")
        self.live_price_var = tk.StringVar(value="ОЖИДАНИЕ OKX")
        tk.Label(header, textvariable=self.live_price_var, bg=BG, fg=GREEN,
                 font=("Consolas", 14, "bold")).pack(side="right")

        self.price_canvas = tk.Canvas(chart_panel, bg="#081522", height=300,
                                      highlightthickness=1, highlightbackground="#1e465c")
        self.price_canvas.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        self.price_canvas.bind("<Configure>", lambda _event: self._draw_price_chart())

        side = tk.Frame(chart_panel, bg=PANEL, highlightbackground="#1e465c", highlightthickness=1)
        side.grid(row=1, column=1, sticky="nsew")
        tk.Label(side, text="ORDER BOOK PRESSURE", bg=PANEL, fg=CYAN,
                 font=("Consolas", 9, "bold")).pack(anchor="w", padx=10, pady=(10, 5))
        self.depth_canvas = tk.Canvas(side, bg="#081522", height=74,
                                      highlightthickness=0)
        self.depth_canvas.pack(fill="x", padx=9)
        self.depth_text_var = tk.StringVar(value="BID —  |  ASK —")
        tk.Label(side, textvariable=self.depth_text_var, bg=PANEL, fg=TEXT,
                 font=("Consolas", 9)).pack(anchor="w", padx=10, pady=6)
        tk.Label(side, text="SMART MONEY / TOP 200", bg=PANEL, fg=CYAN,
                 font=("Consolas", 9, "bold")).pack(anchor="w", padx=10, pady=(14, 4))
        self.whale_status_var = tk.StringVar(value="CoinGlass + Nansen: API-ключи не настроены")
        tk.Label(side, textvariable=self.whale_status_var, bg=PANEL, fg=MUTED,
                 wraplength=210, justify="left", font=("Segoe UI", 9)).pack(
                     anchor="w", padx=10, pady=(0, 8)
                 )
        ttk_button = tk.Button(
            side, text="ОБНОВИТЬ WHALE DATA", command=self._check_nansen,
            bg="#153b52", fg=TEXT, activebackground="#205a78",
            activeforeground=TEXT, relief="flat", padx=8, pady=6,
        )
        tk.Label(side, text="NANSEN API KEY", bg=PANEL, fg=MUTED,
                 font=("Consolas", 7, "bold")).pack(anchor="w", padx=10, pady=(4, 2))
        self.nansen_key_entry = tk.Entry(
            side, show="*", bg="#081522", fg=TEXT, insertbackground=CYAN,
            relief="flat", width=27,
        )
        if self._nansen_api_key:
            self.nansen_key_entry.insert(0, self._nansen_api_key)
        self.nansen_key_entry.pack(fill="x", padx=10, pady=(0, 5))
        tk.Button(
            side, text="СОХРАНИТЬ КЛЮЧ", command=self._save_nansen_key,
            bg="#153b52", fg=TEXT, activebackground="#205a78",
            activeforeground=TEXT, relief="flat", padx=8, pady=5,
        ).pack(anchor="w", padx=10, pady=(0, 10))
        tk.Label(side, text="COINGLASS API KEY", bg=PANEL, fg=MUTED,
                 font=("Consolas", 7, "bold")).pack(anchor="w", padx=10, pady=(4, 2))
        self.coinglass_key_entry = tk.Entry(
            side, show="*", bg="#081522", fg=TEXT, insertbackground=CYAN,
            relief="flat", width=27,
        )
        if self._coinglass_api_key:
            self.coinglass_key_entry.insert(0, self._coinglass_api_key)
        self.coinglass_key_entry.pack(fill="x", padx=10, pady=(0, 5))
        tk.Button(
            side, text="СОХРАНИТЬ COINGLASS KEY", command=self._save_coinglass_key,
            bg="#153b52", fg=TEXT, activebackground="#205a78",
            activeforeground=TEXT, relief="flat", padx=8, pady=5,
        ).pack(anchor="w", padx=10, pady=(0, 10))
        self.whale_tree = ttk.Treeview(
            side, columns=("notional", "pnl"), show="tree headings", height=8
        )
        self.whale_tree.heading("#0", text="WALLET")
        self.whale_tree.heading("notional", text="SIZE USD")
        self.whale_tree.heading("pnl", text="U.PNL")
        self.whale_tree.column("#0", width=90)
        self.whale_tree.column("notional", width=80, anchor="e")
        self.whale_tree.column("pnl", width=65, anchor="e")
        whale_scroll = ttk.Scrollbar(side, orient="vertical", command=self.whale_tree.yview)
        self.whale_tree.configure(yscrollcommand=whale_scroll.set)
        self.whale_tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=(0, 8))
        whale_scroll.pack(side="right", fill="y", padx=(0, 8), pady=(0, 8))
        ttk_button.pack(anchor="w", padx=10, pady=(0, 10))
        tk.Label(side, text="РЕЖИМ: PAPER ONLY", bg="#183328", fg=GREEN,
                 font=("Consolas", 9, "bold"), padx=8, pady=6).pack(
                     anchor="w", padx=10, pady=(0, 10)
                 )
        self.after(250, self._drain_chart_queue)
        self._check_nansen()

    def _record_price(self, _payload):
        # BOTok renders ticker events through its thread-safe chart queue.
        return

    def _handle_market_message(self, message: dict):
        super()._handle_market_message(message)
        runtime = self._runtime
        if runtime is None or self._stop_flag.is_set():
            return
        arg = message.get("arg") or {}
        channel = arg.get("channel")
        if channel not in {"tickers", "books5"}:
            return
        incoming_symbol = str(arg.get("instId") or "")
        if self._chart_symbol not in runtime.state.tickers and runtime.state.tickers:
            self._chart_symbol = next(iter(runtime.state.tickers))
        symbol = self._chart_symbol
        if incoming_symbol != symbol:
            return
        ticker = runtime.state.tickers.get(symbol)
        if ticker is None:
            return
        book = runtime.state.orderbooks.get(symbol)
        bids = float(sum(level.amount for level in book.bids)) if book else 0.0
        asks = float(sum(level.amount for level in book.asks)) if book else 0.0
        self._chart_queue.put((symbol, float(ticker.last), bids, asks))

    def _scheduled_whale_refresh(self):
        self._whale_refresh_scheduled = False
        if not self._closed and self._coinglass_api_key:
            self._check_nansen()

    def _draw_price_chart(self):
        canvas = getattr(self, "price_canvas", None)
        if canvas is None:
            return
        canvas.delete("all")
        width = max(120, canvas.winfo_width())
        height = max(100, canvas.winfo_height())
        for fraction in (0.2, 0.4, 0.6, 0.8):
            y = int(height * fraction)
            canvas.create_line(0, y, width, y, fill="#173246", dash=(2, 5))
        values = list(self._price_history)
        if len(values) < 2:
            canvas.create_text(width / 2, height / 2, text="LIVE PRICE CHART — WAITING FOR OKX",
                               fill=MUTED, font=("Consolas", 10))
            return
        low, high = min(values), max(values)
        span = max(high - low, abs(high) * 0.000001, 1e-12)
        coords = []
        for index, value in enumerate(values):
            x = 12 + index * (width - 24) / (len(values) - 1)
            y = height - 18 - (value - low) / span * (height - 36)
            coords.extend((x, y))
        canvas.create_line(*coords, fill=CYAN, width=2, smooth=True)
        canvas.create_text(10, 10, anchor="nw", text=f"H {high:.8g}",
                           fill=GREEN, font=("Consolas", 8))
        canvas.create_text(10, height - 8, anchor="sw", text=f"L {low:.8g}",
                           fill=RED, font=("Consolas", 8))

    def _draw_depth_chart(self):
        canvas = getattr(self, "depth_canvas", None)
        if canvas is None:
            return
        canvas.delete("all")
        width = max(100, canvas.winfo_width())
        height = max(40, canvas.winfo_height())
        total = self._bid_volume + self._ask_volume
        if total <= 0:
            canvas.create_text(width / 2, height / 2, text="NO BOOK DATA",
                               fill=MUTED, font=("Consolas", 8))
            return
        split = width * self._bid_volume / total
        canvas.create_rectangle(0, 0, split, height, fill="#1c805e", outline="")
        canvas.create_rectangle(split, 0, width, height, fill="#9b4055", outline="")
        canvas.create_text(width * 0.25, height / 2, text="BIDS", fill="white",
                           font=("Consolas", 8))
        canvas.create_text(width * 0.75, height / 2, text="ASKS", fill="white",
                           font=("Consolas", 8))

    def _settings_path(self):
        root = os.environ.get("APPDATA", os.path.expanduser("~"))
        return os.path.join(root, "JARVIS", "settings.json")

    def _load_secret(self, name):
        try:
            from agent.secrets import unprotect_secret
            with open(self._settings_path(), "r", encoding="utf-8") as handle:
                settings = json.load(handle)
            return unprotect_secret(settings.get(name, ""))
        except (OSError, ValueError, TypeError):
            return ""

    def _load_nansen_key(self):
        return self._load_secret("nansen_api_key")

    def _load_coinglass_key(self):
        return self._load_secret("coinglass_api_key")

    def _save_secret(self, name, value):
        from agent.secrets import protect_secret
        path = self._settings_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                settings = json.load(handle)
        except (OSError, ValueError):
            settings = {}
        settings[name] = protect_secret(value)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(settings, handle, ensure_ascii=False, indent=2)

    def _save_nansen_key(self):
        value = self.nansen_key_entry.get().strip()
        if not value:
            self.whale_status_var.set("Nansen key пустой.")
            return
        try:
            self._save_secret("nansen_api_key", value)
            self._nansen_api_key = value
            self.whale_status_var.set("Nansen key сохранён через Windows DPAPI.")
            self._check_nansen()
        except Exception as exc:
            self.whale_status_var.set(f"Ошибка сохранения Nansen key: {exc}")

    def _save_coinglass_key(self):
        value = self.coinglass_key_entry.get().strip()
        if not value:
            self.whale_status_var.set("CoinGlass key пустой.")
            return
        try:
            self._save_secret("coinglass_api_key", value)
            self._coinglass_api_key = value
            self.whale_status_var.set("CoinGlass key сохранён через Windows DPAPI.")
            self._check_nansen()
        except Exception as exc:
            self.whale_status_var.set(f"Ошибка сохранения CoinGlass key: {exc}")

    def _check_nansen(self):
        def check():
            messages = []
            wallets = []
            try:
                from .coinglass_whales import CoinGlassWhaleClient
                client = CoinGlassWhaleClient(api_key=self._coinglass_api_key)
                if client.configured:
                    wallets = client.top_wallets(limit=200)
                    messages.append(f"CoinGlass: {len(wallets)} кошельков с крупными открытыми позициями")
                else:
                    messages.append("CoinGlass: нужен API key")
            except Exception as exc:
                messages.append(f"CoinGlass: {exc}")
            try:
                from .whale_sources import NansenMCPClient
                client = NansenMCPClient(api_key=self._nansen_api_key)
                if client.configured:
                    tools = client.relevant_tools()
                    messages.append(f"Nansen MCP: подключён, аналитических tools {len(tools)}")
                else:
                    messages.append("Nansen: нужен API key для smart-money labels/trades")
            except Exception as exc:
                messages.append(f"Nansen MCP: {exc}")
            self._chart_queue.put(("__whale_rows__", wallets, 0.0, 0.0))
            self._chart_queue.put(("__nansen_status__", " | ".join(messages), 0.0, 0.0))
        threading.Thread(target=check, name="botok-whale-refresh", daemon=True).start()

    def _drain_chart_queue(self):
        if self._closed:
            return
        latest = None
        try:
            while True:
                item = self._chart_queue.get_nowait()
                if item[0] == "__nansen_status__":
                    self.whale_status_var.set(item[1])
                elif item[0] == "__whale_rows__":
                    self.whale_tree.delete(*self.whale_tree.get_children())
                    for wallet in item[1]:
                        address = wallet.address
                        short_address = address if len(address) <= 15 else f"{address[:7]}…{address[-5:]}"
                        self.whale_tree.insert(
                            "", "end", text=short_address,
                            values=(f"{wallet.gross_position_usd:,.0f}",
                                    f"{wallet.unrealized_pnl_usd:,.0f}"),
                        )
                    if item[1] and not self._whale_refresh_scheduled:
                        self._whale_refresh_scheduled = True
                        self.after(60000, self._scheduled_whale_refresh)
                else:
                    latest = item
        except queue.Empty:
            pass
        if latest is not None:
            symbol, price, bids, asks = latest
            self._chart_symbol = symbol
            self._price_history.append(price)
            self._last_price = price
            self._bid_volume, self._ask_volume = bids, asks
            self.live_symbol_var.set(symbol)
            self.live_price_var.set(f"{price:.8g}")
            self.depth_text_var.set(f"BID {bids:,.3f}  |  ASK {asks:,.3f}")
            self._draw_price_chart()
            self._draw_depth_chart()
        self.after(250, self._drain_chart_queue)
