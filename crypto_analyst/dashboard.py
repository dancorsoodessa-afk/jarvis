"""Tkinter Crypto Analyst workspace for the JARVIS desktop application."""

from __future__ import annotations

import asyncio
import queue
import threading
import time
from collections import deque
from tkinter import ttk
import tkinter as tk
from decimal import Decimal
from .whale_dashboard import WhaleRadarWindow

from .config import CryptoConfig
from .engine import ScalpingEngine
from .okx_universe import OKXInstrumentDiscovery
from .okx_ws import OKXPublicFeed
from .paper import PaperBroker
from .risk import RiskManager
from .runtime import PaperScalpingRuntime
from .whale_intel import CoinLobsterWhaleClient


BG = "#07111d"
PANEL = "#0c1c2c"
TEXT = "#eaf6ff"
MUTED = "#8da9bb"
CYAN = "#69e6f5"
GREEN = "#63e6a5"
RED = "#ff7185"


class CryptoDashboard(tk.Toplevel):
    """Public market scanner and paper-only trading workspace."""

    def __init__(self, master):
        super().__init__(master)
        self.title("JARVIS — CRYPTO ANALYST / PAPER TRADING")
        self.geometry("1100x720")
        self.minsize(850, 560)
        self.configure(bg=BG)
        self._events: queue.Queue = queue.Queue()
        self._stop_flag = threading.Event()
        self._worker_thread: threading.Thread | None = None
        self._runtime: PaperScalpingRuntime | None = None
        self._whale_refresh = threading.Event()
        self._whale_thread: threading.Thread | None = None
        self._price_history: list[float] = []
        self._chart_symbol = "BTC-USDT-SWAP"
        self._last_ui_update = 0.0
        self._closed = False
        self._price_history = deque(maxlen=180)
        self._chart_symbol = None
        self._whale_window = None
        self.config_model = CryptoConfig()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(200, self._drain_events)

    def _build_ui(self):
        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", padx=18, pady=(16, 10))
        tk.Label(
            header, text="JARVIS CRYPTO ANALYST", bg=BG, fg=CYAN,
            font=("Segoe UI", 18, "bold"),
        ).pack(anchor="w")
        tk.Label(
            header,
            text="OKX PUBLIC MARKET DATA  •  DETERMINISTIC SCALPING  •  PAPER ONLY",
            bg=BG, fg=MUTED, font=("Consolas", 9, "bold"),
        ).pack(anchor="w", pady=(3, 0))

        safety = tk.Label(
            self,
            text="PAPER TRADING ONLY — REAL EXCHANGE ORDERS ARE DISABLED",
            bg="#183328", fg=GREEN, font=("Consolas", 10, "bold"), padx=12, pady=9,
        )
        safety.pack(fill="x", padx=18, pady=(0, 12))

        controls = tk.Frame(self, bg=PANEL, highlightbackground="#1e465c", highlightthickness=1)
        controls.pack(fill="x", padx=18, pady=(0, 12))
        self.start_button = ttk.Button(controls, text="ЗАПУСТИТЬ СКАНИРОВАНИЕ", command=self.start)
        self.start_button.pack(side="left", padx=12, pady=12)
        self.stop_button = ttk.Button(controls, text="ОСТАНОВИТЬ", command=self.stop, state="disabled")
        self.stop_button.pack(side="left", padx=(0, 12), pady=12)
        self.emergency_button = ttk.Button(controls, text="АВАРИЙНЫЙ СТОП", command=self.emergency_stop, state="disabled")
        self.emergency_button.pack(side="left", padx=(0, 12), pady=12)
        self.refresh_button = ttk.Button(controls, text="ОБНОВИТЬ КИТОВ", command=self.refresh_whales)
        self.refresh_button.pack(side="left", padx=(0, 12), pady=12)
        self.whale_button = ttk.Button(controls, text="WHALE RADAR · TOP 200", command=self.open_whales)
        self.whale_button.pack(side="left", padx=(0, 12), pady=12)
        self.status_var = tk.StringVar(value="ОСТАНОВЛЕНО")
        tk.Label(
            controls, textvariable=self.status_var, bg=PANEL, fg=CYAN,
            font=("Consolas", 10, "bold"),
        ).pack(side="left", padx=10)

        metrics = tk.Frame(self, bg=BG)
        metrics.pack(fill="x", padx=18, pady=(0, 12))
        self.metric_vars = {}
        for key, title in (
            ("symbols", "ИНСТРУМЕНТЫ"),
            ("events", "СОБЫТИЯ WS"),
            ("orders", "PAPER-ОРДЕРА"),
            ("positions", "ОТКРЫТЫЕ ПОЗИЦИИ"),
            ("balance", "ВИРТУАЛЬНЫЙ БАЛАНС"),
            ("oi", "OPEN INTEREST"),
            ("funding", "FUNDING RATE"),
            ("liquidations", "ЛИКВИДАЦИИ"),
        ):
            card = tk.Frame(metrics, bg=PANEL, highlightbackground="#1e465c", highlightthickness=1)
            card.pack(side="left", fill="both", expand=True, padx=(0, 7))
            tk.Label(card, text=title, bg=PANEL, fg=MUTED, font=("Consolas", 8, "bold")).pack(
                anchor="w", padx=10, pady=(9, 2)
            )
            value = tk.StringVar(value="—")
            self.metric_vars[key] = value
            tk.Label(card, textvariable=value, bg=PANEL, fg=TEXT, font=("Segoe UI", 13, "bold")).pack(
                anchor="w", padx=10, pady=(0, 9)
            )

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=1)
        self.chart = tk.Canvas(body, height=190, bg="#081522", highlightthickness=1, highlightbackground="#1e465c")
        self.chart.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        self.chart.bind("<Configure>", lambda _event: self._draw_chart())
        self._draw_chart()
        self.log = tk.Text(
            body, bg="#081522", fg=TEXT, insertbackground=CYAN,
            relief="flat", wrap="word", font=("Consolas", 9), padx=12, pady=10,
            state="disabled",
        )
        self.log.grid(row=1, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(body, command=self.log.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scroll.set)
        self._append("Система готова. Для старта используются публичные данные OKX без API-ключей.")

    def open_whales(self):
        if self._whale_window is not None and self._whale_window.winfo_exists():
            self._whale_window.lift()
            return
        self._whale_window = WhaleRadarWindow(self)

    def _draw_chart(self):
        if not hasattr(self, "chart"):
            return
        canvas = self.chart
        canvas.delete("all")
        width = max(200, canvas.winfo_width())
        height = max(120, canvas.winfo_height())
        left, right, top, bottom = 62, width - 18, 18, height - 30
        canvas.create_text(14, 10, anchor="nw", fill=CYAN,
                           text=f"LIVE PRICE · {self._chart_symbol or 'WAITING FOR OKX TICKER'}",
                           font=("Consolas", 9, "bold"))
        for index in range(5):
            y = top + (bottom - top) * index / 4
            canvas.create_line(left, y, right, y, fill="#18364a")
        values = [price for _stamp, _symbol, price in self._price_history]
        if len(values) < 2:
            canvas.create_text(width / 2, height / 2, fill=MUTED,
                               text="Ожидание потока котировок OKX…",
                               font=("Segoe UI", 10))
            return
        low, high = min(values), max(values)
        spread = high - low
        if spread <= 0:
            spread = max(abs(high) * 0.0001, 0.00000001)
        points = []
        for index, value in enumerate(values):
            x = left + (right - left) * index / max(1, len(values) - 1)
            y = bottom - (value - low) / spread * (bottom - top)
            points.extend((x, y))
        canvas.create_line(*points, fill=CYAN, width=2, smooth=True)
        canvas.create_text(8, top, anchor="w", fill=MUTED,
                           text=f"{high:.6g}", font=("Consolas", 8))
        canvas.create_text(8, bottom, anchor="w", fill=MUTED,
                           text=f"{low:.6g}", font=("Consolas", 8))
        canvas.create_text(right, top, anchor="ne", fill=GREEN,
                           text=f"{values[-1]:.8g}", font=("Consolas", 9, "bold"))

    def _record_price(self, payload):
        try:
            symbol = str(payload["symbol"])
            price = float(payload["price"])
            if price <= 0:
                return
        except (KeyError, TypeError, ValueError):
            return
        if self._chart_symbol is None or symbol == "BTC-USDT-SWAP":
            self._chart_symbol = symbol
            self._price_history.append((payload.get("timestamp"), symbol, price))
            self._draw_chart()

    def _append(self, message: str):
        self.log.configure(state="normal")
        self.log.insert("end", f"[{time.strftime('%H:%M:%S')}] {message}\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def start(self):
        if self._worker_thread and self._worker_thread.is_alive():
            return
        self._stop_flag.clear()
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.emergency_button.configure(state="normal")
        self.status_var.set("ПОЛУЧАЮ СПИСОК ИНСТРУМЕНТОВ…")
        self._whale_thread = threading.Thread(target=self._whale_worker, name="jarvis-whales", daemon=True)
        self._whale_thread.start()
        self._worker_thread = threading.Thread(target=self._worker, name="jarvis-crypto", daemon=True)
        self._worker_thread.start()

    def _whale_worker(self):
        client = CoinLobsterWhaleClient()
        while not self._stop_flag.is_set():
            try:
                self._events.put(("whales", client.fetch_snapshot("BTC")))
            except Exception as exc:
                self._events.put(("whale_error", str(exc)))
            self._whale_refresh.wait(30.0)
            self._whale_refresh.clear()

    def refresh_whales(self):
        self._whale_refresh.set()
        self._append("Запрошено обновление whale feed.")

    def emergency_stop(self):
        self.stop()
        self.status_var.set("АВАРИЙНАЯ ОСТАНОВКА")
        self._append("EMERGENCY STOP: потоки остановлены; новые paper-сигналы запрещены.")

    def _draw_chart(self):
        canvas = getattr(self, "chart", None)
        if canvas is None:
            return
        canvas.delete("all")
        width, height = max(200, canvas.winfo_width()), max(120, canvas.winfo_height())
        left, right, top, bottom = 60, width - 15, 12, height - 24
        for i in range(5):
            y = top + (bottom - top) * i / 4
            canvas.create_line(left, y, right, y, fill="#1b3448", dash=(2, 4))
        values = self._price_history
        if len(values) < 2:
            canvas.create_text(width / 2, height / 2, text="ОЖИДАНИЕ OKX TICKER STREAM", fill=MUTED, font=("Consolas", 10))
            return
        low, high = min(values), max(values)
        span = max(high - low, abs(high) * 0.00001, 0.0000001)
        points = []
        for i, value in enumerate(values):
            points.extend((left + (right-left) * i / max(1, len(values)-1), bottom - (value-low)/span*(bottom-top)))
        canvas.create_line(*points, fill=CYAN, width=2, smooth=True)
        canvas.create_text(8, top, anchor="w", text=f"{high:.6g}", fill=MUTED, font=("Consolas", 8))
        canvas.create_text(8, bottom, anchor="w", text=f"{low:.6g}", fill=MUTED, font=("Consolas", 8))

    def _show_whales(self, snapshot):
        for item in self.whale_tree.get_children():
            self.whale_tree.delete(item)
        for trade in snapshot.trades[:200]:
            stamp = time.strftime("%H:%M:%S", time.localtime(trade.timestamp_ms / 1000)) if trade.timestamp_ms else "—"
            wallet = trade.wallet[:16] + "…" if len(trade.wallet) > 18 else (trade.wallet or "—")
            self.whale_tree.insert("", "end", values=(stamp, trade.coin, trade.side.upper(), f"{trade.usd:,.0f}", trade.venue, wallet))
        self._append(f"CoinLobster: получено {len(snapshot.trades)} сделок; аккаунтов Hyperliquid: {len(snapshot.accounts)}.")
        if not snapshot.accounts:
            self._append("Provider board не вернул список аккаунтов; топ-200 не подменяется выдуманными данными.")
        for warning in snapshot.warnings:
            self._append("Whale feed warning: " + warning)

    def _worker(self):
        try:
            discovery = OKXInstrumentDiscovery()
            instruments = discovery.discover_liquid_instruments(
                include_spot=True,
                include_swaps=True,
                max_symbols=self.config_model.max_symbols,
                min_quote_volume_usdt=Decimal("250000"),
            )
            symbols = [item.symbol for item in instruments]
            if not symbols:
                raise RuntimeError("OKX не вернул подходящие ликвидные USDT-инструменты.")
            contract_multipliers = {
                item.symbol: item.contract_multiplier for item in instruments
            }
            derivative_symbols = {
                item.symbol for item in instruments if item.market_type == "swap"
            }
            runtime = PaperScalpingRuntime(
                engine=ScalpingEngine(whitelist=set(symbols)),
                risk_manager=RiskManager(),
                broker=PaperBroker(starting_balance=Decimal("10000")),
                contract_multipliers=contract_multipliers,
                derivative_symbols=derivative_symbols,
            )
            self._runtime = runtime
            self._events.put(("symbols", len(symbols)))
            self._events.put(("status", f"ПОДПИСКА OKX: {len(symbols)} ИНСТРУМЕНТОВ"))
            self._events.put(("log", f"Найдено ликвидных инструментов: {len(symbols)}. Запускаю публичные WebSocket-потоки."))
            feed = OKXPublicFeed(
                symbols,
                self._handle_market_message,
                derivative_symbols=derivative_symbols,
            )
            asyncio.run(self._run_feed(feed))
            self._events.put(("status", "ОСТАНОВЛЕНО"))
        except Exception as exc:
            self._events.put(("error", str(exc)))

    async def _run_feed(self, feed: OKXPublicFeed):
        stop_event = asyncio.Event()

        async def watch_stop():
            while not self._stop_flag.is_set():
                await asyncio.sleep(0.15)
            stop_event.set()

        watcher = asyncio.create_task(watch_stop())
        try:
            await feed.run(stop_event)
        finally:
            watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)

    def _handle_market_message(self, message: dict):
        runtime = self._runtime
        if runtime is None or self._stop_flag.is_set():
            return
        now_ms = int(time.time() * 1000)
        signals = runtime.on_market_message(message, now_ms)
        channel = (message.get("arg") or {}).get("channel", "unknown")
        if channel == "tickers":
            for row in message.get("data") or []:
                if isinstance(row, dict) and row.get("last"):
                    self._events.put(("price", {
                        "symbol": str((message.get("arg") or {}).get("instId") or ""),
                        "price": row.get("last"),
                        "timestamp": row.get("ts"),
                    }))
        if signals:
            for signal in signals:
                self._events.put((
                    "signal",
                    f"{signal.side.upper()} {signal.symbol} | вход {signal.entry} | "
                    f"SL {signal.stop_loss} | TP {signal.take_profit} | "
                    f"imbalance {signal.imbalance:.3f} | delta {signal.trade_delta}",
                ))
        if time.monotonic() - self._last_ui_update >= 1.0:
            self._last_ui_update = time.monotonic()
            sample_symbol = next(iter(runtime.derivative_symbols), None)
            oi_row = runtime.state.open_interest.get(sample_symbol, {}) if sample_symbol else {}
            funding_row = runtime.state.funding_rates.get(sample_symbol, {}) if sample_symbol else {}
            self._events.put(("metrics", {
                "events": runtime.event_count,
                "orders": len(runtime.broker.orders),
                "positions": runtime.broker.open_position_count(),
                "balance": runtime.broker.cash,
                "oi": oi_row.get("oiUsd") or oi_row.get("oi") or "—",
                "funding": funding_row.get("fundingRate") or "—",
                "liquidations": len(runtime.state.liquidations),
            }))
            if ticker:
                self._events.put(("price", (ticker.symbol, float(ticker.last))))
            self._events.put(("activity", channel))

    def stop(self):
        self._stop_flag.set()
        self.status_var.set("ОСТАНАВЛИВАЮ…")
        self.stop_button.configure(state="disabled")
        self.emergency_button.configure(state="disabled")
        self._whale_refresh.set()

    def _drain_events(self):
        if self._closed:
            return
        try:
            while True:
                kind, payload = self._events.get_nowait()
                if kind == "status":
                    self.status_var.set(payload)
                    if payload == "ОСТАНОВЛЕНО":
                        self.start_button.configure(state="normal")
                        self.stop_button.configure(state="disabled")
                        self.emergency_button.configure(state="disabled")
                elif kind == "symbols":
                    self.metric_vars["symbols"].set(str(payload))
                elif kind == "log":
                    self._append(payload)
                elif kind == "signal":
                    self._append("PAPER SIGNAL: " + payload)
                elif kind == "price":
                    self._record_price(payload)
                elif kind == "activity":
                    self.status_var.set(f"LIVE • OKX {str(payload).upper()}")
                elif kind == "price":
                    symbol, value = payload
                    self._chart_symbol = symbol
                    self._price_history.append(value)
                    self._price_history = self._price_history[-240:]
                    self._draw_chart()
                elif kind == "whales":
                    self._show_whales(payload)
                elif kind == "whale_error":
                    self._append("CoinLobster: " + str(payload))
                elif kind == "metrics":
                    values = payload
                    if values["events"] is not None:
                        self.metric_vars["events"].set(str(values["events"]))
                    self.metric_vars["orders"].set(str(values["orders"]))
                    self.metric_vars["positions"].set(str(values["positions"]))
                    self.metric_vars["balance"].set(f'{values["balance"]:.2f} USDT')
                    self.metric_vars["oi"].set(str(values["oi"]))
                    self.metric_vars["funding"].set(str(values["funding"]))
                    self.metric_vars["liquidations"].set(str(values["liquidations"]))
                elif kind == "error":
                    self.status_var.set("ОШИБКА")
                    self._append("Ошибка: " + str(payload))
                    self.start_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    self.emergency_button.configure(state="disabled")
        except queue.Empty:
            pass
        if not self._closed:
            self.after(200, self._drain_events)

    def close(self):
        self._closed = True
        self._stop_flag.set()
        self._whale_refresh.set()
        try:
            self.destroy()
        except tk.TclError:
            pass
