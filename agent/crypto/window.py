"""Compact, button-first crypto dashboard for the JARVIS desktop app."""
from __future__ import annotations

import json
import os
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from .analysis import analyze
from .market import MarketDataError, PublicMarketClient
from .risk import build_plan


BG = "#07111d"
PANEL = "#0c1c2b"
LINE = "#1d5268"
CYAN = "#65eaff"
TEXT = "#eaf8ff"
MUTED = "#91a9b8"
GREEN = "#5be0a0"
RED = "#ff7086"
AMBER = "#ffd27a"


class CryptoWindow(tk.Toplevel):
    """A dashboard whose primary workflow is selecting and pressing buttons."""

    SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT")
    TIMEFRAMES = ("15m", "1h", "4h", "1d")

    def __init__(self, master):
        super().__init__(master)
        self.title("JARVIS — CRYPTO INTELLIGENCE")
        self.geometry("1040x760")
        self.minsize(900, 650)
        self.configure(bg=BG)
        self.client = PublicMarketClient()
        self.symbol = "BTCUSDT"
        self.timeframe = "1h"
        self.capital = tk.DoubleVar(value=1000.0)
        self.risk_pct = tk.DoubleVar(value=1.0)
        self._busy = False
        self._auto_refresh = False
        self._refresh_job = None
        self._snapshot = None
        self._report = None
        self._plan = None
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._close_window)
        self.refresh()

    def _button(self, parent, label, command, accent=False):
        return tk.Button(
            parent, text=label, command=command,
            bg="#0c5268" if accent else "#102536",
            fg=TEXT if accent else "#c7d9e4",
            activebackground="#14748c", activeforeground="white",
            relief="flat", bd=0, padx=13, pady=9,
            font=("Segoe UI", 9, "bold"), cursor="hand2",
            highlightthickness=1, highlightbackground=LINE,
        )

    def _build(self):
        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", padx=18, pady=(16, 10))
        tk.Label(header, text="CRYPTO INTELLIGENCE", bg=BG, fg=CYAN,
                 font=("Segoe UI", 20, "bold")).pack(side="left")
        self.status = tk.Label(header, text="ПОДКЛЮЧЕНИЕ…", bg=BG, fg=AMBER,
                               font=("Consolas", 9, "bold"))
        self.status.pack(side="right")

        controls = tk.Frame(self, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        controls.pack(fill="x", padx=18, pady=6)
        tk.Label(controls, text="МОНЕТА", bg=PANEL, fg=MUTED,
                 font=("Consolas", 8, "bold")).pack(side="left", padx=(12, 6))
        self.symbol_buttons = {}
        for symbol in self.SYMBOLS:
            button = self._button(controls, symbol.replace("USDT", ""), lambda s=symbol: self.select_symbol(s))
            button.pack(side="left", padx=3, pady=8)
            self.symbol_buttons[symbol] = button
        tk.Label(controls, text="ТАЙМФРЕЙМ", bg=PANEL, fg=MUTED,
                 font=("Consolas", 8, "bold")).pack(side="left", padx=(18, 6))
        for timeframe in self.TIMEFRAMES:
            self._button(controls, timeframe, lambda t=timeframe: self.select_timeframe(t)).pack(side="left", padx=3)
        self.auto_button = self._button(controls, "АВТООБНОВЛЕНИЕ: ВЫКЛ", self.toggle_auto_refresh)
        self.auto_button.pack(side="right", padx=4)
        self._button(controls, "ОБНОВИТЬ РЫНОК", self.refresh, True).pack(side="right", padx=4)

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=18, pady=10)
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        left = tk.Frame(body, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        right = tk.Frame(body, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        right.grid(row=0, column=1, sticky="nsew", padx=(7, 0))

        tk.Label(left, text="РЫНОЧНЫЕ ДАННЫЕ", bg=PANEL, fg=CYAN,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=16, pady=(14, 8))
        self.price_label = tk.Label(left, text="—", bg=PANEL, fg=TEXT,
                                    font=("Segoe UI", 27, "bold"))
        self.price_label.pack(anchor="w", padx=16)
        self.change_label = tk.Label(left, text="Ожидание данных", bg=PANEL, fg=MUTED,
                                     font=("Consolas", 10))
        self.change_label.pack(anchor="w", padx=16, pady=(2, 12))
        self.source_label = tk.Label(left, text="Источники: —", bg=PANEL, fg=MUTED,
                                     font=("Consolas", 8))
        self.source_label.pack(anchor="w", padx=16)
        self.exchange_label = tk.Label(left, text="Сравнение бирж: —", bg=PANEL, fg=MUTED,
                                       font=("Consolas", 8), justify="left", anchor="w")
        self.exchange_label.pack(anchor="w", padx=16, pady=(5, 0))
        self.analysis_label = tk.Label(left, text="Нажмите «ОБНОВИТЬ РЫНОК» для анализа.",
                                       bg=PANEL, fg=TEXT, justify="left", anchor="nw",
                                       font=("Segoe UI", 10), wraplength=550)
        self.analysis_label.pack(fill="both", expand=True, padx=16, pady=16)

        tk.Label(right, text="ТОРГОВЫЙ ПЛАН", bg=PANEL, fg=CYAN,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=16, pady=(14, 8))
        self.signal_label = tk.Label(right, text="HOLD", bg=PANEL, fg=AMBER,
                                     font=("Segoe UI", 23, "bold"))
        self.signal_label.pack(anchor="w", padx=16)
        self.plan_label = tk.Label(right, text="Сигнал ещё не рассчитан.",
                                   bg=PANEL, fg=TEXT, justify="left", anchor="nw",
                                   font=("Consolas", 9), wraplength=350)
        self.plan_label.pack(fill="both", expand=True, padx=16, pady=12)

        risk_box = tk.Frame(right, bg="#091521")
        risk_box.pack(fill="x", padx=12, pady=(0, 10))
        tk.Label(risk_box, text="КАПИТАЛ, USDT", bg="#091521", fg=MUTED,
                 font=("Consolas", 8)).grid(row=0, column=0, sticky="w", padx=8, pady=6)
        tk.Spinbox(risk_box, from_=10, to=10000000, increment=100,
                   textvariable=self.capital, width=12, bg="#102536", fg=TEXT,
                   buttonbackground="#16445a", relief="flat").grid(row=0, column=1, padx=8)
        tk.Label(risk_box, text="РИСК НА СДЕЛКУ, %", bg="#091521", fg=MUTED,
                 font=("Consolas", 8)).grid(row=1, column=0, sticky="w", padx=8, pady=6)
        tk.Spinbox(risk_box, from_=0.1, to=2.0, increment=0.1,
                   textvariable=self.risk_pct, width=12, bg="#102536", fg=TEXT,
                   buttonbackground="#16445a", relief="flat").grid(row=1, column=1, padx=8)
        self._button(right, "ПЕРЕСЧИТАТЬ РИСК", self.recalculate, True).pack(fill="x", padx=12, pady=(0, 8))
        self._button(right, "СОХРАНИТЬ ПЛАН", self.save_plan).pack(fill="x", padx=12, pady=(0, 12))

        footer = tk.Label(
            self,
            text="ТОЛЬКО АНАЛИЗ И РАСЧЁТЫ • ОРДЕРА НЕ ОТПРАВЛЯЮТСЯ • ДАННЫЕ ПУБЛИЧНЫХ API",
            bg=BG, fg=MUTED, font=("Consolas", 8),
        )
        footer.pack(fill="x", padx=18, pady=(0, 12))

    def select_symbol(self, symbol):
        self.symbol = symbol
        self.refresh()

    def select_timeframe(self, timeframe):
        self.timeframe = timeframe
        self.refresh()

    def refresh(self):
        if self._busy:
            return
        self._busy = True
        self.status.config(text="ПОЛУЧЕНИЕ ДАННЫХ…", fg=AMBER)
        self.analysis_label.config(text="Запрашиваю публичные рыночные данные Binance / Bybit…")
        def worker():
            try:
                snapshots = self.client.fetch_all(self.symbol, self.timeframe)
                snapshot = snapshots[0]
                report = analyze(snapshot)
                self.after(0, lambda: self._show_result(snapshot, report, snapshots))
            except Exception as exc:
                error = str(exc)
                self.after(0, lambda message=error: self._show_error(message))
        threading.Thread(target=worker, daemon=True).start()

    def _show_result(self, snapshot, report, snapshots):
        self._busy = False
        self._snapshot, self._report = snapshot, report
        self.status.config(text=f"ONLINE · {snapshot.exchange}", fg=GREEN)
        self.price_label.config(text=f"{snapshot.price:,.6f} USDT")
        color = GREEN if snapshot.change_24h_pct >= 0 else RED
        self.change_label.config(text=f"24ч: {snapshot.change_24h_pct:+.2f}%   |   Объём: {snapshot.quote_volume_24h:,.0f} USDT", fg=color)
        self.source_label.config(text=f"Источники: {', '.join(item.exchange for item in snapshots)} · {__import__('time').strftime('%H:%M:%S')}")
        prices = "   |   ".join(f"{item.exchange}: {item.price:,.6f}" for item in snapshots)
        self.exchange_label.config(text="Сравнение бирж: " + prices)
        self.signal_label.config(text=report.direction, fg=GREEN if report.direction == "LONG" else RED if report.direction == "SHORT" else AMBER)
        lines = [
            f"EMA 9:  {report.ema9:,.6f}",
            f"EMA 21: {report.ema21:,.6f}",
            f"EMA 50: {report.ema50:,.6f}",
            f"RSI 14: {report.rsi14:.1f}",
            f"ATR 14: {report.atr14:,.6f}",
            f"Поддержка: {report.support:,.6f}",
            f"Сопротивление: {report.resistance:,.6f}",
            "",
            "ОБОСНОВАНИЕ:",
            *[f"• {reason}" for reason in report.reasons],
            "",
            *[f"ВНИМАНИЕ: {warning}" for warning in report.warnings],
            f"Оценка согласованности: {report.confidence}/85",
        ]
        self.analysis_label.config(text="\n".join(lines))
        self.recalculate()

    def _show_error(self, error):
        self._busy = False
        self._snapshot = None
        self._report = None
        self._plan = None
        self.status.config(text="НЕТ ДАННЫХ", fg=RED)
        self.analysis_label.config(text="Не удалось получить свежие данные. Сигнал не формируется.\n\n" + error)
        self.signal_label.config(text="NO TRADE", fg=AMBER)
        self.plan_label.config(text="План недоступен: источник данных не подтвердил актуальную цену.")

    def recalculate(self):
        if not self._snapshot or not self._report or self._report.direction not in {"LONG", "SHORT"}:
            self._plan = None
            self.plan_label.config(text="Нет подтверждённого направления. Действие: HOLD / NO TRADE.")
            return
        try:
            plan = build_plan(
                self._report.direction, self._snapshot.price, self._report.atr14,
                self.capital.get(), self.risk_pct.get(), 2.0, 1.0,
            )
            self._plan = plan
            self.plan_label.config(text="\n".join([
                f"Направление: {plan.direction}",
                f"Вход: {plan.entry:,.6f}",
                f"Stop Loss: {plan.stop_loss:,.6f}",
                f"Take Profit 1: {plan.take_profit_1:,.6f}",
                f"Take Profit 2: {plan.take_profit_2:,.6f}",
                f"Количество: {plan.quantity:.6f}",
                f"Объём позиции: {plan.position_value:,.2f} USDT",
                f"Риск: {plan.risk_amount:,.2f} USDT",
                f"Risk/Reward: 1:{plan.reward_risk_1:.1f}",
                "Плечо: не используется (Spot)",
                "",
                "План расчётный, не является ордером.",
            ]))
        except Exception as exc:
            self._plan = None
            self.plan_label.config(text="Проверьте капитал и риск.\n" + str(exc))

    def toggle_auto_refresh(self):
        self._auto_refresh = not self._auto_refresh
        self.auto_button.config(text="АВТООБНОВЛЕНИЕ: ВКЛ" if self._auto_refresh else "АВТООБНОВЛЕНИЕ: ВЫКЛ")
        if self._auto_refresh:
            self._schedule_auto_refresh()
        elif self._refresh_job is not None:
            self.after_cancel(self._refresh_job)
            self._refresh_job = None

    def _close_window(self):
        self._auto_refresh = False
        if self._refresh_job is not None:
            try:
                self.after_cancel(self._refresh_job)
            except tk.TclError:
                pass
        self.destroy()

    def _schedule_auto_refresh(self):
        if not self._auto_refresh or not self.winfo_exists():
            return
        if not self._busy:
            self.refresh()
        self._refresh_job = self.after(20000, self._schedule_auto_refresh)

    def save_plan(self):
        if not self._plan:
            messagebox.showinfo("JARVIS CRYPTO", "Нет готового торгового плана для сохранения.", parent=self)
            return
        directory = Path(os.environ.get("APPDATA", str(Path.home()))) / "JARVIS" / "crypto"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "trade_plans.json"
        record = {
            "saved_at": time.time(),
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "exchange": self._snapshot.exchange,
            "direction": self._plan.direction,
            "entry": self._plan.entry,
            "stop_loss": self._plan.stop_loss,
            "take_profit_1": self._plan.take_profit_1,
            "take_profit_2": self._plan.take_profit_2,
            "quantity": self._plan.quantity,
            "position_value": self._plan.position_value,
            "risk_amount": self._plan.risk_amount,
            "risk_percent": self.risk_pct.get(),
        }
        try:
            existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
            if not isinstance(existing, list):
                existing = []
            existing.append(record)
            path.write_text(json.dumps(existing[-500:], ensure_ascii=False, indent=2), encoding="utf-8")
        except (OSError, ValueError) as exc:
            messagebox.showerror("JARVIS CRYPTO", "Не удалось сохранить план: " + str(exc), parent=self)
            return
        messagebox.showinfo(
            "План сохранён",
            f"План добавлен в журнал: {path}\nРеальный ордер не отправлялся.",
            parent=self,
        )
