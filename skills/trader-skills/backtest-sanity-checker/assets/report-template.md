# Backtest sanity check: {strategy name}
*Checked {date}. Inputs: {trade log / prices / code / description}.*

**Bottom line (neutral):** {N red, M amber flags}. {One sentence: which result can be trusted and which cannot yet.}

## Red flags (fix before trusting any number)
1. **{flag}**: {evidence: number from script or line of code}. Fix: {specific change}.

## Amber flags (check or improve)
1. **{flag}**: {evidence}. Fix: {change}.

## What looks OK
- {item with evidence}

## Re-test plan
1. {e.g. add .shift(1), re-run, re-check fill-day table}
2. {e.g. add 10 bps round-trip cost, hold out 2024-2026 as out-of-sample}

## Appendix: script output
{paste report.md}

*Methodology check only, not financial advice. Past and simulated results do not predict future returns.*
