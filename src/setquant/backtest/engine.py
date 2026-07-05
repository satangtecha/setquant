"""Monthly cross-sectional backtest engine.

Correctness rules this engine enforces:
- Point-in-time universe: at formation month t we only look at stocks
  that were index members ON t (past members included, future ones not).
- No look-ahead: selection at t uses only the signal known at t; the
  position earns the NEXT month's return.
- Costs are explicit: cost_per_side x turnover, charged when the
  portfolio changes. Turnover ignores intra-month weight drift — a
  documented simplification that slightly UNDERSTATES costs.
- A held stock with no next-month return (delisting gap in the data)
  is excluded at formation. Documented limitation.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from setquant.universe import members_on, to_data_symbol, to_yahoo


@dataclass
class BacktestResult:
    monthly: pd.DataFrame
    params: dict = field(default_factory=dict)


def run_monthly_backtest(
    monthly: pd.DataFrame,
    periods: pd.DataFrame,
    aliases: dict[str, str],
    signal: str = "mom_12_1",
    top_frac: float = 0.10,
    cost_per_side: float = 0.0025,
    min_names: int = 20,
    index_name: str = "SET100",
) -> BacktestResult:
    """monthly: gold table with [date, ticker, monthly_ret, <signal>]."""
    df = monthly.sort_values(["ticker", "date"]).copy()
    df["next_ret"] = df.groupby("ticker")["monthly_ret"].shift(-1)

    months = sorted(df["date"].unique())
    by_month = {t: g for t, g in df.groupby("date")}

    prev_weights: dict[str, float] = {}
    rows = []
    for i, t in enumerate(months[:-1]):
        member_tickers = {
            to_yahoo(to_data_symbol(s, aliases))
            for s in members_on(periods, t, index_name)
        }
        snap = by_month[t]
        elig = snap[snap["ticker"].isin(member_tickers)].dropna(subset=[signal, "next_ret"])
        if len(elig) < min_names:
            prev_weights = {}
            continue

        k = max(1, int(len(elig) * top_frac))
        top = elig.nlargest(k, signal)
        bottom = elig.nsmallest(k, signal)

        weights = {tk: 1.0 / k for tk in top["ticker"]}
        turnover = sum(
            abs(weights.get(tk, 0.0) - prev_weights.get(tk, 0.0))
            for tk in set(weights) | set(prev_weights)
        )
        cost = cost_per_side * turnover

        gross = float(top["next_ret"].mean())
        rows.append({
            "date": months[i + 1],          # month in which the return is realized
            "formation_date": t,
            "gross_ret": gross,
            "net_ret": gross - cost,
            "bench_ret": float(elig["next_ret"].mean()),
            "spread_gross": gross - float(bottom["next_ret"].mean()),
            "n_eligible": len(elig),
            "n_held": k,
            "turnover": turnover,
            "cost": cost,
        })
        prev_weights = weights

    out = pd.DataFrame(rows)
    params = {
        "signal": signal, "top_frac": top_frac, "cost_per_side": cost_per_side,
        "min_names": min_names, "index_name": index_name,
    }
    return BacktestResult(monthly=out, params=params)
