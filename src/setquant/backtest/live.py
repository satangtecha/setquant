"""Live paper-trading logic.

Discipline rules (the whole point of a live log):
- Rebalance once per month, from the last COMPLETE month-end. Never
  re-run mid-month to get a nicer portfolio.
- Every rebalance and every realized month is appended to files under
  research/live/ and committed to git. History is never edited.
- Unlike the backtest engine, live selection cannot require next-month
  returns (they don't exist yet) — only the signal must be present.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from setquant.universe import members_on, to_data_symbol, to_yahoo


def latest_formation_month(monthly: pd.DataFrame, today=None) -> pd.Timestamp:
    """Last month-end strictly before the current calendar month.

    Running on 2026-07-05 must form on 2026-06-30 — the partial July
    row in the gold table is not a complete month and must be ignored.
    """
    today = pd.Timestamp(today) if today is not None else pd.Timestamp.now()
    cutoff = today.normalize().replace(day=1)
    months = sorted(m for m in pd.to_datetime(monthly["date"].unique()) if m < cutoff)
    if not months:
        raise ValueError("no complete month in the gold table")
    return pd.Timestamp(months[-1])


def target_portfolio(
    monthly: pd.DataFrame,
    periods: pd.DataFrame,
    aliases: dict[str, str],
    formation: pd.Timestamp,
    signal: str = "mom_12_1",
    top_frac: float = 0.10,
    min_names: int = 20,
    index_name: str = "SET100",
) -> pd.DataFrame:
    if formation > periods["period_end"].max():
        raise ValueError(
            "universe table ends before the formation date — download the "
            "new SET constituent list, run scripts/parse_universe_pdfs.py, "
            "then rerun"
        )
    members = {
        to_yahoo(to_data_symbol(s, aliases))
        for s in members_on(periods, formation, index_name)
    }
    snap = (
        monthly[(monthly["date"] == formation) & monthly["ticker"].isin(members)]
        .dropna(subset=[signal])
    )
    if len(snap) < min_names:
        raise ValueError(f"only {len(snap)} eligible names at {formation:%Y-%m} — data problem?")

    k = max(1, int(len(snap) * top_frac))
    top = snap.nlargest(k, signal)
    return pd.DataFrame({
        "ticker": sorted(top["ticker"]),
        "weight": 1.0 / k,
        "formation": formation,
        "signal": signal,
    })


def realized_month_return(
    holdings: pd.DataFrame,
    monthly: pd.DataFrame,
    periods: pd.DataFrame,
    aliases: dict[str, str],
    month: pd.Timestamp,
    index_name: str = "SET100",
) -> tuple[float, float, int]:
    """(portfolio_ret, ew_benchmark_ret, n_missing) for one realized month.

    Held names with no return that month (halt/delisting) are reported
    in n_missing, never silently dropped from the log.
    """
    rets = monthly[monthly["date"] == month].set_index("ticker")["monthly_ret"]
    got = [rets.get(t) for t in holdings["ticker"]]
    have = [r for r in got if pd.notna(r)]
    n_missing = len(got) - len(have)
    port = float(pd.Series(have).mean()) if have else float("nan")

    formation = pd.Timestamp(holdings["formation"].iloc[0])
    members = {
        to_yahoo(to_data_symbol(s, aliases))
        for s in members_on(periods, formation, index_name)
    }
    bench = (
        monthly[(monthly["date"] == month) & monthly["ticker"].isin(members)]["monthly_ret"]
        .dropna()
    )
    return port, float(bench.mean()), n_missing
