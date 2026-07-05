import numpy as np
import pandas as pd
import pytest

from setquant.backtest.engine import run_monthly_backtest
from setquant.backtest.metrics import max_drawdown, summarize


def _periods(symbols, start="2024-01-01", end="2024-12-31"):
    return pd.DataFrame({
        "index": "SET100",
        "period_start": pd.to_datetime([start] * len(symbols)),
        "period_end": pd.to_datetime([end] * len(symbols)),
        "symbol": symbols,
        "source": "test",
    })


def _monthly(data):
    """data: {ticker: [(date, ret, signal), ...]}"""
    rows = [
        {"date": pd.Timestamp(d), "ticker": tk, "monthly_ret": r, "mom_12_1": s}
        for tk, obs in data.items() for d, r, s in obs
    ]
    return pd.DataFrame(rows)


def test_non_member_never_selected_even_with_best_signal():
    dates = ["2024-01-31", "2024-02-29"]
    monthly = _monthly({
        "IN.BK":  [(dates[0], 0.0, 1.0), (dates[1], 0.01, 1.0)],
        "OUT.BK": [(dates[0], 0.0, 9.9), (dates[1], 5.00, 9.9)],  # huge signal+return
    })
    periods = _periods(["IN"])  # OUT is not a member
    res = run_monthly_backtest(monthly, periods, {}, top_frac=1.0, min_names=1,
                               cost_per_side=0.0)
    assert len(res.monthly) == 1
    assert res.monthly.iloc[0]["gross_ret"] == pytest.approx(0.01)


def test_no_lookahead_selection_ignores_next_month_return():
    dates = ["2024-01-31", "2024-02-29"]
    monthly = _monthly({
        "HI_SIG.BK": [(dates[0], 0.0, 2.0), (dates[1], 0.00, 2.0)],
        "HI_RET.BK": [(dates[0], 0.0, 0.1), (dates[1], 1.00, 0.1)],  # +100% next month
    })
    periods = _periods(["HI_SIG", "HI_RET"])
    res = run_monthly_backtest(monthly, periods, {}, top_frac=0.5, min_names=2,
                               cost_per_side=0.0)
    # engine must pick the high-SIGNAL stock and miss the +100%
    assert res.monthly.iloc[0]["gross_ret"] == pytest.approx(0.0)


def test_turnover_cost_charged_on_full_switch():
    dates = ["2024-01-31", "2024-02-29", "2024-03-31"]
    monthly = _monthly({
        "A.BK": [(dates[0], 0.0, 2.0), (dates[1], 0.0, 0.1), (dates[2], 0.0, 0.1)],
        "B.BK": [(dates[0], 0.0, 0.1), (dates[1], 0.0, 2.0), (dates[2], 0.0, 2.0)],
    })
    periods = _periods(["A", "B"])
    c = 0.0025
    res = run_monthly_backtest(monthly, periods, {}, top_frac=0.5, min_names=2,
                               cost_per_side=c)
    m = res.monthly
    assert m.iloc[0]["turnover"] == pytest.approx(1.0)      # initial buy of A
    assert m.iloc[0]["net_ret"] == pytest.approx(0.0 - c * 1.0)
    assert m.iloc[1]["turnover"] == pytest.approx(2.0)      # sell A, buy B
    assert m.iloc[1]["net_ret"] == pytest.approx(0.0 - c * 2.0)


def test_max_drawdown_known_series():
    rets = pd.Series([0.10, -0.50, 0.25])
    assert max_drawdown(rets) == pytest.approx(-0.50)


def test_summarize_keys():
    s = summarize(pd.Series(np.full(24, 0.01)))
    assert s["n_months"] == 24
    assert s["cagr"] == pytest.approx(1.01 ** 12 - 1)
