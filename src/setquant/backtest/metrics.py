"""Performance metrics. Conventions (stated, not hidden):
- Risk-free rate = 0 (Thai short rates were ~0.5-2.5% over the sample;
  a constant rf shifts all Sharpe ratios equally and changes no ranking).
- Annualization: 12 monthly periods.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

PERIODS_PER_YEAR = 12


def cagr(rets: pd.Series) -> float:
    total = float((1 + rets).prod())
    years = len(rets) / PERIODS_PER_YEAR
    return total ** (1 / years) - 1 if years > 0 and total > 0 else float("nan")


def ann_vol(rets: pd.Series) -> float:
    return float(rets.std(ddof=1)) * np.sqrt(PERIODS_PER_YEAR)


def sharpe(rets: pd.Series) -> float:
    sd = rets.std(ddof=1)
    return float(rets.mean() / sd) * np.sqrt(PERIODS_PER_YEAR) if sd > 0 else float("nan")


def max_drawdown(rets: pd.Series) -> float:
    curve = (1 + rets).cumprod()
    return float((curve / curve.cummax() - 1).min())


def t_stat(rets: pd.Series) -> float:
    """t-statistic of the mean monthly return (H0: mean = 0)."""
    sd = rets.std(ddof=1)
    return float(rets.mean() / (sd / np.sqrt(len(rets)))) if sd > 0 else float("nan")


def summarize(rets: pd.Series) -> dict:
    return {
        "cagr": cagr(rets),
        "ann_vol": ann_vol(rets),
        "sharpe": sharpe(rets),
        "max_dd": max_drawdown(rets),
        "t_stat": t_stat(rets),
        "n_months": len(rets),
    }
