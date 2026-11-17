---
name: backtest-sanity-checker
description: Checks a trading backtest for the mistakes that make results look better than they are - look-ahead bias, impossible fills, missing costs, too few trades, profit from a handful of outliers, unstable years, and overfitting from trying many variants. Use when the user shares a backtest (trade log CSV, strategy code, or results screenshot/summary) and asks whether it is realistic, robust, or "too good to be true". Reports red/amber flags with evidence. Does not judge whether to trade the strategy.
license: MIT. See LICENSE in the repository root.
compatibility: The automatic checks need Python 3.8+ (standard library only). Without a shell, run the manual checklist only.
metadata:
  author: TapeSkills
  version: "1.0"
---

# Backtest Sanity Checker (TapeSkills, free)

Goal: tell the user, with evidence, which parts of their backtest they can trust and which need fixing. This is a methodology check, not an opinion on the strategy.

## Rules
- Never say a strategy "works", "will make money", or should be traded, sized or leveraged. Say what the evidence shows and what would need fixing.
- Every number you report comes from the script output, the user's files, or a calculation you show.
- If asked "should I trade this?", reply: "I can't tell you whether to trade it. I can show what the backtest does and doesn't prove." Then continue.
- End with: *Methodology check only, not financial advice. Past and simulated results do not predict future returns.*

## Step 1. Collect inputs
Ask for whatever is missing (any subset works):
1. Trade log CSV with entry_date, exit_date, entry_price, exit_price (side optional). Most platforms export one.
2. The price file the backtest used (date, close; open/high/low if available).
3. The strategy code or rules in words.
4. Assumed costs (commission + spread + slippage), number of tuned parameters, and roughly how many variants they tried.

## Step 2. Run the automatic checks (if you have a shell)
```bash
python3 scripts/check_backtest.py trades.csv --prices prices.csv --cost-bps 5 --params 2 --variants-tried 20 --out report.md
```
It checks: data hygiene, whether fill prices exist in the price data and on which day (a fill at an *earlier* day's close than the trade date is the classic look-ahead signature), headline stats, cost sensitivity and break-even cost, dependence on the best trades, year-by-year stability, and a rough multiple-testing bar.

## Step 3. Manual review
Go through [references/manual-checklist.md](references/manual-checklist.md). For code, look especially for: signals computed with the same bar's close and filled at that close or earlier, missing `.shift(1)`, indicators or scalers fitted on the full dataset, `center=True` rolling windows, today's index members used for past dates (survivorship), unadjusted prices around splits, and stops filled at the exact stop price on gaps.

## Step 4. Write the report
Use [assets/report-template.md](assets/report-template.md): verdict line in neutral words ("3 red flags, 2 amber: results are not reliable until fixed"), flags with evidence, what to fix first, how to re-test. Keep it under one page plus the script output as an appendix.

## Worked example
`examples/` rebuilds a real test on S&P 500 data from FRED: the same 10-day moving-average rule with and without a look-ahead bug. The bug turns +125.67% into +25,280.93% over ten years, and the checker flags it as RED from the fill prices alone. See `examples/README.md`.
