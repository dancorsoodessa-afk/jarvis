"""Enhanced BOTok trading workspace layered over the stable paper dashboard."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
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
        self.whale_status_var = tk.StringVar(value="Nansen: требуется API-ключ")
        tk.Label(side, textvariable=self.whale_status_var, bg=PANEL, fg=MUTED,
                 wraplength=210, justify="left", font=("Segoe UI", 9)).pack(
                     anchor="w", padx=10, pady=(0, 8)
                 )
        ttk_button = tk.Button(
            side, text="ПРОВЕРИТЬ NANSEN", command=self._check_nansen,
            bg="#153b52", fg=TEXT, activebackground="#205a78",
            activeforeground=TEXT, relief="flat", padx=8, pady=6,
        )
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
        symbol = self._chart_symbol
        ticker = runtime.state.tickers.get(symbol)
        if ticker is None and runtime.state.tickers:
            symbol, ticker = next(iter(runtime.state.tickers.items()))
        if ticker is None:
            return
        book = runtime.state.orderbooks.get(symbol)
        bids = float(sum(level.amount for level in book.bids)) if book else 0.0
        asks = float(sum(level.amount for level in book.asks)) if book else 0.0
        self._chart_queue.put((symbol, float(ticker.last), bids, asks))

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

    def _check_nansen(self):
        def check():
            try:
                from .whale_sources import NansenMCPClient
                client = NansenMCPClient()
                if not client.configured:
                    status = "Nansen не подключён. Нужен NANSEN_API_KEY; реальные кошельки не подменяются демо-данными."
                else:
                    tools = client.relevant_tools()
                    status = f"Nansen MCP: соединение успешно, доступно аналитических tools: {len(tools)}. Рейтинг кошельков появится после выбора API-схемы."
            except Exception as exc:
                status = f"Nansen MCP недоступен: {exc}"
            self._chart_queue.put(("__nansen_status__", status, 0.0, 0.0))
        threading.Thread(target=check, name="botok-nansen-check", daemon=True).start()

    def _drain_chart_queue(self):
        if self._closed:
            return
        latest = None
        try:
            while True:
                latest = self._chart_queue.get_nowait()
                if latest[0] == "__nansen_status__":
                    self.whale_status_var.set(latest[1])
                    latest = None
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
