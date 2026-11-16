"""Stable Tkinter Crypto Analyst workspace used by the BOTok dashboard."""

from __future__ import annotations

import asyncio
import queue
import threading
import time
import tkinter as tk
from decimal import Decimal
from tkinter import ttk

from .config import CryptoConfig
from .engine import ScalpingEngine
from .okx_universe import OKXInstrumentDiscovery
from .okx_ws import OKXPublicFeed
from .paper import PaperBroker
from .risk import RiskManager
from .runtime import PaperScalpingRuntime


BG = "#07111d"
PANEL = "#0c1c2c"
TEXT = "#eaf6ff"
MUTED = "#8da9bb"
CYAN = "#69e6f5"
GREEN = "#63e6a5"
RED = "#ff7185"


class CryptoDashboard(tk.Toplevel):
    """Public OKX market scanner and deterministic paper-only trading workspace."""

    def __init__(self, master):
        super().__init__(master)
        self.title("JARVIS — BOTok / PAPER TRADING")
        self.geometry("1200x780")
        self.minsize(900, 620)
        self.configure(bg=BG)
        self._events: queue.Queue = queue.Queue()
        self._stop_flag = threading.Event()
        self._worker_thread: threading.Thread | None = None
        self._runtime: PaperScalpingRuntime | None = None
        self._last_ui_update = 0.0
        self._closed = False
        self.config_model = CryptoConfig()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(200, self._drain_events)

    def _build_ui(self):
        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", padx=18, pady=(16, 10))
        tk.Label(header, text="BOTok · CRYPTO ANALYST", bg=BG, fg=CYAN,
                 font=("Segoe UI", 19, "bold")).pack(anchor="w")
        tk.Label(
            header,
            text="OKX PUBLIC MARKET DATA  •  DETERMINISTIC SCALPING  •  PAPER ONLY",
            bg=BG, fg=MUTED, font=("Consolas", 9, "bold"),
        ).pack(anchor="w", pady=(3, 0))

        tk.Label(
            self,
            text="PAPER TRADING ONLY — REAL EXCHANGE ORDERS ARE DISABLED",
            bg="#183328", fg=GREEN, font=("Consolas", 10, "bold"), padx=12, pady=9,
        ).pack(fill="x", padx=18, pady=(0, 12))

        controls = tk.Frame(self, bg=PANEL, highlightbackground="#1e465c", highlightthickness=1)
        controls.pack(fill="x", padx=18, pady=(0, 12))
        self.start_button = ttk.Button(controls, text="▶ СТАРТ", command=self.start)
        self.start_button.pack(side="left", padx=12, pady=10)
        self.stop_button = ttk.Button(controls, text="■ СТОП", command=self.stop, state="disabled")
        self.stop_button.pack(side="left", padx=(0, 8), pady=10)
        self.emergency_button = ttk.Button(
            controls, text="АВАРИЙНЫЙ СТОП", command=self.emergency_stop, state="disabled"
        )
        self.emergency_button.pack(side="left", padx=(0, 8), pady=10)
        self.status_var = tk.StringVar(value="ГОТОВ К ЗАПУСКУ")
        tk.Label(controls, textvariable=self.status_var, bg=PANEL, fg=CYAN,
                 font=("Consolas", 9, "bold")).pack(side="right", padx=12)

        metrics = tk.Frame(self, bg=BG)
        metrics.pack(fill="x", padx=18, pady=(0, 12))
        self.metric_vars = {}
        for key, title in (
            ("symbols", "ИНСТРУМЕНТЫ"), ("events", "СОБЫТИЯ WS"),
            ("orders", "PAPER-ОРДЕРА"), ("positions", "ПОЗИЦИИ"),
            ("balance", "ВИРТУАЛЬНЫЙ БАЛАНС"), ("oi", "OPEN INTEREST"),
            ("funding", "FUNDING RATE"), ("liquidations", "ЛИКВИДАЦИИ"),
        ):
            card = tk.Frame(metrics, bg=PANEL, highlightbackground="#1e465c", highlightthickness=1)
            card.pack(side="left", fill="both", expand=True, padx=(0, 6))
            tk.Label(card, text=title, bg=PANEL, fg=MUTED,
                     font=("Consolas", 7, "bold")).pack(anchor="w", padx=8, pady=(7, 1))
            value = tk.StringVar(value="—")
            self.metric_vars[key] = value
            tk.Label(card, textvariable=value, bg=PANEL, fg=TEXT,
                     font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=8, pady=(0, 7))

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=1)
        self.chart = tk.Canvas(
            body, height=190, bg="#081522",
            highlightthickness=1, highlightbackground="#1e465c",
        )
        self.chart.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        self.chart.bind("<Configure>", lambda _event: self._draw_chart())
        self.log = tk.Text(
            body, bg="#081522", fg=TEXT, insertbackground=CYAN,
            relief="flat", wrap="word", font=("Consolas", 9),
            padx=12, pady=10, state="disabled",
        )
        self.log.grid(row=1, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(body, command=self.log.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scroll.set)
        self._append("BOTok готов. Для старта используются публичные OKX WebSocket-данные.")

    def _draw_chart(self):
        canvas = getattr(self, "chart", None)
        if canvas is None:
            return
        canvas.delete("all")
        canvas.create_text(
            12, 10, anchor="nw", fill=CYAN,
            text="LIVE PRICE — график строится в BOTok dashboard",
            font=("Consolas", 9, "bold"),
        )

    def _record_price(self, _payload):
        # The enhanced BOTokDashboard owns the live chart queue.
        return

    def _append(self, message: str):
        if not hasattr(self, "log"):
            return
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
        self._worker_thread = threading.Thread(
            target=self._worker, name="botok-okx-market", daemon=True
        )
        self._worker_thread.start()

    def emergency_stop(self):
        self.stop()
        self.status_var.set("АВАРИЙНАЯ ОСТАНОВКА")
        self._append("EMERGENCY STOP: новые paper-сигналы остановлены.")

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
            self._events.put(("status", f"OKX LIVE · {len(symbols)} ИНСТРУМЕНТОВ"))
            self._events.put(("log", f"Найдено инструментов: {len(symbols)}. Запускаю публичные WebSocket-потоки."))
            feed = OKXPublicFeed(
                symbols, self._handle_market_message,
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
        for signal in signals:
            self._events.put((
                "signal",
                f"{signal.side.upper()} {signal.symbol} | entry {signal.entry} | "
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
            self._events.put(("activity", channel))

    def stop(self):
        self._stop_flag.set()
        self.status_var.set("ОСТАНАВЛИВАЮ…")
        self.stop_button.configure(state="disabled")
        self.emergency_button.configure(state="disabled")

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
                    self.status_var.set(f"LIVE · OKX {str(payload).upper()}")
                elif kind == "metrics":
                    values = payload
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
        try:
            self.destroy()
        except tk.TclError:
            pass
