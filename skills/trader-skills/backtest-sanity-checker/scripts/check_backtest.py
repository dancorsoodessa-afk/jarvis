#!/usr/bin/env python3
"""TapeSkills Backtest Sanity Checker (MIT licence). Standard library only, Python 3.8+.

Reads a trade log (and optionally the price file the backtest used) and prints a
markdown report of red flags: impossible fills, possible look-ahead, too few trades,
profit concentration, cost sensitivity, unstable sub-periods and overfitting risk.

Usage:
  python3 check_backtest.py trades.csv [--prices prices.csv] [--cost-bps 10]
                            [--params 3] [--variants-tried 20] [--out report.md]

trades.csv needs: entry_date, exit_date, entry_price, exit_price
  optional: side (long/short, default long). Column names are matched loosely.
prices.csv needs: a date column and a close column (open/high/low used if present).
Dates: YYYY-MM-DD (or anything starting with that).
"""
import argparse, csv, math, statistics, sys
from datetime import date

ALIASES = {
    "entry_date": ["entry_date", "entry date", "entrydate", "open_date", "date_in", "entry_time", "entry"],
    "exit_date": ["exit_date", "exit date", "exitdate", "close_date", "date_out", "exit_time", "exit"],
    "entry_price": ["entry_price", "entry price", "entryprice", "price_in", "buy_price", "open_price"],
    "exit_price": ["exit_price", "exit price", "exitprice", "price_out", "sell_price", "close_price"],
    "side": ["side", "direction", "type", "position"],
}
PRICE_ALIASES = {
    "date": ["date", "observation_date", "datetime", "time", "timestamp", "day"],
    "close": ["close", "adj close", "adj_close", "adjclose", "price", "last", "sp500"],
    "open": ["open"], "high": ["high"], "low": ["low"],
}

def norm(s): return s.strip().lower().replace("-", "_")

def find_col(header, names):
    h = {norm(c): c for c in header}
    for n in names:
        if norm(n) in h: return h[norm(n)]
    return None

def pdate(s):
    s = (s or "").strip()[:10]
    try: return date.fromisoformat(s)
    except ValueError: return None

def pnum(s):
    try: return float(str(s).replace(",", "").replace("$", "").strip())
    except (ValueError, TypeError): return None

def load_trades(path):
    rows, bad = [], []
    with open(path, newline="", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        cols = {k: find_col(r.fieldnames, v) for k, v in ALIASES.items()}
        missing = [k for k in ("entry_date", "exit_date", "entry_price", "exit_price") if not cols[k]]
        if missing: sys.exit(f"trades file is missing columns: {missing}. Found: {r.fieldnames}")
        for i, row in enumerate(r, start=2):
            t = {"line": i, "ed": pdate(row[cols["entry_date"]]), "xd": pdate(row[cols["exit_date"]]),
                 "ep": pnum(row[cols["entry_price"]]), "xp": pnum(row[cols["exit_price"]]),
                 "side": (row.get(cols["side"]) or "long").strip().lower() if cols["side"] else "long"}
            t["side"] = "short" if t["side"].startswith(("s", "-")) else "long"
            if None in (t["ed"], t["xd"], t["ep"], t["xp"]) or t["ep"] <= 0 or t["xp"] <= 0:
                bad.append(i); continue
            t["ret"] = (t["xp"] / t["ep"] - 1) * (1 if t["side"] == "long" else -1)
            rows.append(t)
    return rows, bad

def load_prices(path):
    out = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        c = {k: find_col(r.fieldnames, v) for k, v in PRICE_ALIASES.items()}
        if not c["date"]: sys.exit(f"prices file needs a date column. Found: {r.fieldnames}")
        if not c["close"]:
            nums = [x for x in r.fieldnames if x != c["date"]]
            c["close"] = nums[0] if len(nums) == 1 else None
        if not c["close"]: sys.exit(f"prices file needs a close column. Found: {r.fieldnames}")
        for row in r:
            d, cl = pdate(row[c["date"]]), pnum(row[c["close"]])
            if d and cl:
                out[d] = {k: pnum(row[c[k]]) if c[k] else None for k in ("open", "high", "low")}
                out[d]["close"] = cl
    return out

def max_drawdown(rets):
    eq, peak, mdd = 1.0, 1.0, 0.0
    for x in rets:
        eq *= 1 + x; peak = max(peak, eq); mdd = min(mdd, eq / peak - 1)
    return mdd

def compound(rets):
    eq = 1.0
    for x in rets: eq *= 1 + x
    return eq - 1

def pct(x): return f"{x*100:.2f}%"

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("trades"); ap.add_argument("--prices")
    ap.add_argument("--cost-bps", type=float, default=None, help="your assumed round-trip cost per trade in basis points")
    ap.add_argument("--params", type=int, default=None, help="number of tuned parameters in the strategy")
    ap.add_argument("--variants-tried", type=int, default=None, help="how many versions/parameter sets were tried before this one")
    ap.add_argument("--out")
    a = ap.parse_args()

    trades, bad = load_trades(a.trades)
    trades.sort(key=lambda t: (t["ed"], t["xd"]))
    flags, L = [], []
    def flag(level, text): flags.append((level, text))
    L.append("# Backtest sanity check\n")
    L.append(f"Trade file: `{a.trades}`" + (f" | Price file: `{a.prices}`" if a.prices else " | Price file: not supplied (fill checks skipped)"))
    if not trades: sys.exit("no valid trades found")
    n = len(trades)
    first, last = trades[0]["ed"], max(t["xd"] for t in trades)
    L.append(f"Period: {first} to {last} | Trades: {n} | Unreadable rows: {len(bad)}\n")

    # 1. Data hygiene
    L.append("## 1. Data hygiene")
    neg = [t["line"] for t in trades if t["xd"] < t["ed"]]
    dup = n - len({(t["ed"], t["xd"], t["ep"], t["xp"], t["side"]) for t in trades})
    overlap = sum(1 for a_, b_ in zip(trades, trades[1:]) if b_["ed"] < a_["xd"])
    L.append(f"- Exit before entry: {len(neg)} | Duplicate trades: {dup} | Trades opened before the previous one closed: {overlap}")
    if neg: flag("RED", f"{len(neg)} trades exit before they enter (lines {neg[:5]}...). The log or the code is broken.")
    if dup: flag("AMBER", f"{dup} duplicate trades. Check the trade log for double counting.")
    if bad: flag("AMBER", f"{len(bad)} rows could not be read (lines {bad[:5]}).")
    if overlap: L.append("  - Overlapping trades: the compounded figures below assume one position at a time, so treat them as rough.")
    weekend = [t["line"] for t in trades if t["ed"].weekday() >= 5 or t["xd"].weekday() >= 5]
    if weekend: flag("AMBER", f"{len(weekend)} trades enter or exit on a Saturday/Sunday (lines {weekend[:5]}). Fine for crypto, suspicious for stocks.")

    # 2. Fills vs the price data
    if a.prices:
        px = load_prices(a.prices)
        days = sorted(px); idx = {d: i for i, d in enumerate(days)}
        L.append("\n## 2. Are the fills possible? (checked against the price file)")
        nodate, outside, off = 0, 0, {"entry": {}, "exit": {}}
        for t in trades:
            for kind, d, p in (("entry", t["ed"], t["ep"]), ("exit", t["xd"], t["xp"])):
                if d not in idx: nodate += 1; continue
                bar = px[d]
                if bar["high"] and bar["low"] and not (bar["low"] * 0.9999 <= p <= bar["high"] * 1.0001): outside += 1
                i = idx[d]; hit = None
                for k in (0, -1, 1, -2, 2):   # which day's close does this fill price equal?
                    j = i + k
                    if 0 <= j < len(days) and abs(px[days[j]]["close"] / p - 1) < 1e-4: hit = k; break
                if hit is None and bar.get("open") and abs(bar["open"] / p - 1) < 1e-4: hit = "open"
                off[kind][hit] = off[kind].get(hit, 0) + 1
        L.append(f"- Fill dates missing from price data (holidays, wrong calendar, or bad dates): {nodate} of {2*n}")
        if nodate > 0.02 * 2 * n: flag("AMBER", f"{nodate} fill dates are not trading days in the price file.")
        if outside: flag("RED", f"{outside} fills are outside that day's high-low range: impossible prices.")
        for kind in ("entry", "exit"):
            o = off[kind]; tot = sum(o.values()) or 1
            desc = ", ".join(f"{('same-day close' if k == 0 else 'open' if k == 'open' else 'no exact match' if k is None else f'close {k:+d} day(s)')}: {v}" for k, v in sorted(o.items(), key=lambda kv: -kv[1]))
            L.append(f"- {kind.title()} prices match: {desc}")
            if o.get(-1, 0) + o.get(-2, 0) > 0.3 * tot:
                flag("RED", f"{o.get(-1,0)+o.get(-2,0)} of {tot} {kind} prices equal an EARLIER day's close than the {kind} date. "
                     "Classic look-ahead: the signal uses today's data but the fill is at yesterday's price (e.g. a missing .shift(1)).")
        same_close = off["entry"].get(0, 0)
        if same_close > 0.5 * n:
            flag("AMBER", "Most entries fill at the same day's close. That is only realistic if the signal is known BEFORE the close "
                 "(e.g. market-on-close order using data up to a few minutes earlier). If the signal uses that close, shift fills to the next bar.")
        # buy and hold benchmark
        span = [d for d in days if first <= d <= last]
        if len(span) > 1:
            bh = px[span[-1]]["close"] / px[span[0]]["close"] - 1
            in_mkt = set()
            for t in trades:
                for d in span:
                    if t["ed"] < d <= t["xd"]: in_mkt.add(d)
            expo = len(in_mkt) / (len(span) - 1)
            L.append(f"- Buy-and-hold over the same dates: {pct(bh)} | Strategy time in market: {pct(expo)}")
    else:
        bh = None

    # 3. Headline stats (per-trade, one position at a time, no leverage)
    rets = [t["ret"] for t in trades]
    wins = [r for r in rets if r > 0]; losses = [r for r in rets if r <= 0]
    tot = compound(rets); years = max((last - first).days / 365.25, 1e-9)
    cagr = (1 + tot) ** (1 / years) - 1 if tot > -1 else -1
    mean, sd = statistics.mean(rets), (statistics.stdev(rets) if n > 1 else 0)
    tstat = mean / (sd / math.sqrt(n)) if sd > 0 else float("inf")
    pf = sum(wins) / -sum(losses) if losses and sum(losses) < 0 else float("inf")
    hold = statistics.mean((t["xd"] - t["ed"]).days for t in trades)
    L.append("\n## 3. Headline numbers (from the trade log, before any costs you add)")
    L.append("| Metric | Value |\n|---|---|")
    for k, v in [("Total return (compounded, 1 position at a time)", pct(tot)), ("Annualised (CAGR)", pct(cagr)),
                 ("Win rate", pct(len(wins) / n)), ("Average trade", f"{mean*1e4:.1f} bps"),
                 ("Average win / average loss", f"{(statistics.mean(wins) if wins else 0)*1e4:.1f} / {(statistics.mean(losses) if losses else 0)*1e4:.1f} bps"),
                 ("Profit factor", f"{pf:.2f}"), ("Max drawdown (trade-by-trade)", pct(max_drawdown(rets))),
                 ("Average holding period", f"{hold:.1f} calendar days"), ("t-stat of average trade", f"{tstat:.2f}")]:
        L.append(f"| {k} | {v} |")
    if n < 30: flag("RED", f"Only {n} trades. Too few to tell skill from luck.")
    elif n < 100: flag("AMBER", f"{n} trades. Results can swing a lot with a different sample.")
    if len(wins) / n > 0.8 and pf < 3: flag("AMBER", "Win rate above 80% with a modest profit factor: check for small wins and rare large losses (or a missing stop-loss in the log).")
    if len(wins) / n > 0.9 and pf > 20:
        flag("RED", f"Win rate {pct(len(wins)/n)} with profit factor {pf:.0f}: too good to be true for almost any real strategy. Assume a bug (look-ahead, wrong prices) until proven otherwise.")
    if tstat > 6: flag("AMBER", f"t-stat {tstat:.1f} is unusually high for a trading strategy. Re-check for look-ahead or data errors before celebrating.")
    if tstat < 2: flag("AMBER", f"t-stat {tstat:.2f} < 2: the average trade is not clearly different from zero, even before costs.")

    # 4. Costs
    L.append("\n## 4. Cost sensitivity (round-trip cost per trade)")
    L.append("| Cost per round trip | Total return | Annualised |\n|---|---|---|")
    levels = sorted({0, 5, 10, 20, 50} | ({a.cost_bps} if a.cost_bps is not None else set()))
    for c in levels:
        tr = compound([r - c / 1e4 for r in rets]); cg = (1 + tr) ** (1 / years) - 1 if tr > -1 else -1
        L.append(f"| {c:g} bps | {pct(tr)} | {pct(cg)} |")
    L.append(f"- Break-even cost: about **{mean*1e4:.1f} bps per round trip** (the average trade). Above that, the strategy loses money.")
    if mean * 1e4 < 10: flag("RED", f"Average trade is only {mean*1e4:.1f} bps. Typical commissions + spread + slippage can erase it.")
    elif mean * 1e4 < 25: flag("AMBER", f"Average trade is {mean*1e4:.1f} bps. Costs matter; test with realistic spread and slippage.")
    if a.cost_bps is None: flag("AMBER", "No cost assumption given (--cost-bps). Results above are gross unless your log already includes costs.")

    # 5. Concentration and stability
    L.append("\n## 5. Is the profit fragile?")
    srt = sorted(rets, reverse=True); k = max(1, min(5, n // 10 or 1))
    without = compound(srt[k:])
    L.append(f"- Total return without the best {k} trades: {pct(without)} (with them: {pct(tot)})")
    if tot > 0 and without <= 0: flag("RED", f"Removing the best {k} trades wipes out the whole profit. The result depends on a few outliers.")
    by_year = {}
    for t in trades: by_year.setdefault(t["xd"].year, []).append(t["ret"])
    L.append("| Year | Trades | Return | Win rate |\n|---|---|---|---|")
    for y in sorted(by_year):
        rr = by_year[y]; L.append(f"| {y} | {len(rr)} | {pct(compound(rr))} | {pct(sum(r > 0 for r in rr)/len(rr))} |")
    pos_years = sum(compound(v) > 0 for v in by_year.values())
    half = n // 2
    if half >= 5:
        h1, h2 = compound(rets[:half]), compound(rets[half:])
        L.append(f"- First half of trades: {pct(h1)} | Second half: {pct(h2)}")
        if (h1 > 0) != (h2 > 0): flag("AMBER", "The first and second halves of the sample disagree in sign. The edge may be regime-dependent or decaying.")
    if len(by_year) >= 3 and pos_years / len(by_year) < 0.5: flag("AMBER", f"Only {pos_years} of {len(by_year)} years were profitable.")

    # 6. Overfitting
    L.append("\n## 6. Overfitting risk")
    if a.params:
        L.append(f"- Trades per tuned parameter: {n / a.params:.0f}")
        if n / a.params < 20: flag("AMBER", f"Fewer than 20 trades per tuned parameter ({n}/{a.params}). High risk the parameters fit noise.")
    else:
        L.append("- Number of tuned parameters not given (--params).")
    if a.variants_tried and a.variants_tried > 1:
        need = statistics.NormalDist().inv_cdf(1 - 0.05 / (2 * a.variants_tried))
        L.append(f"- You tried {a.variants_tried} variants. A rough multiple-testing bar (Bonferroni, 5%) for the t-stat is {need:.2f}; this result is {tstat:.2f}.")
        if tstat < need: flag("AMBER", f"After trying {a.variants_tried} variants, a t-stat of {tstat:.2f} is below the ~{need:.2f} bar. The best variant may be luck.")
    else:
        L.append("- How many variants were tried is unknown (--variants-tried). The more you tried, the higher the bar.")
    if a.prices and bh is not None and tot < bh:
        L.append(f"- Note: buy-and-hold returned {pct(bh)} over the same dates vs {pct(tot)} for the strategy (strategy was in the market less of the time).")

    # Summary first
    order = {"RED": 0, "AMBER": 1}
    flags.sort(key=lambda f: order[f[0]])
    summary = ["## Summary of flags", ""]
    if not flags: summary.append("- GREEN: no automatic red flags. Still do the manual code checklist.")
    for lvl, txt in flags: summary.append(f"- **{lvl}**: {txt}")
    summary.append("\n*Automatic checks only. They cannot see survivorship bias, adjusted vs unadjusted prices, or look-ahead inside indicators: use the manual checklist.*\n")
    report = "\n".join(L[:3] + summary + L[3:]) + "\n"
    if a.out: open(a.out, "w").write(report)
    print(report)

if __name__ == "__main__":
    main()
