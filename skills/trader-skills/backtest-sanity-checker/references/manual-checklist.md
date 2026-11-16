# Manual backtest checklist

Mark each: OK / Problem / Unknown (ask the user).

## Look-ahead (using information you would not have had)
- [ ] Signal on bar t uses only data up to bar t, and the trade fills at bar t+1 (or at t's close only if the signal is known before the close).
- [ ] In vectorised code the position is shifted: `returns * position.shift(1)`, not `returns * position`.
- [ ] No indicator, scaler, model or threshold is fitted on the whole dataset (fit only on data before each decision).
- [ ] No `center=True` rolling windows, no `bfill` of future values, no use of the day's high/low to decide a trade filled at that day's open.
- [ ] Earnings, fundamentals and news are used from their *release* date, not the period end date.

## Data
- [ ] Universe is point-in-time: includes stocks that were later delisted or dropped from the index (survivorship bias).
- [ ] Prices adjusted consistently for splits and dividends; signals not mixing adjusted and unadjusted series.
- [ ] Time zones and trading calendar match (no weekend trades for stocks, no missing holidays).
- [ ] Enough history to include at least one bad market regime (e.g. 2020 crash, 2022 bear market).

## Execution realism
- [ ] Costs: commission + bid-ask spread + slippage, per side. Small caps, options and crypto alts need much more than large caps.
- [ ] Stops and limits: gaps through a stop fill at the open, not the stop price; limits don't always fill.
- [ ] Position size is possible vs the stock's daily volume; shorting is possible (borrow, fees).
- [ ] Capital and margin: no overlapping positions using more capital than exists.

## Overfitting
- [ ] Number of parameters is small relative to the number of trades (rule of thumb: 20+ trades per parameter).
- [ ] Results hold when each parameter is nudged ±20% (a plateau, not a spike).
- [ ] An out-of-sample period was held back and only tested once.
- [ ] The user knows how many variants were tried; the more variants, the higher the bar (the script prints a rough one).

## Comparison
- [ ] Compared with buy-and-hold of the same asset over the same dates, and with time-in-market taken into account.
- [ ] Drawdown and longest losing streak are ones the user has actually seen in the results.
