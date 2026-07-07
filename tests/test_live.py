import pandas as pd
import pytest

from setquant.backtest.live import (
    latest_formation_month,
    realized_month_return,
    target_portfolio,
)


def _periods(symbols):
    return pd.DataFrame({
        "index": "SET100",
        "period_start": pd.to_datetime(["2026-01-01"] * len(symbols)),
        "period_end": pd.to_datetime(["2026-12-31"] * len(symbols)),
        "symbol": symbols, "source": "test",
    })


def _monthly(rows):
    return pd.DataFrame(rows, columns=["date", "ticker", "monthly_ret", "mom_12_1"]) \
        .assign(date=lambda d: pd.to_datetime(d["date"]))


def test_latest_formation_ignores_partial_current_month():
    m = _monthly([("2026-05-31", "A.BK", 0.0, 1.0),
                  ("2026-06-30", "A.BK", 0.0, 1.0),
                  ("2026-07-31", "A.BK", 0.0, 1.0)])  # partial month row
    assert latest_formation_month(m, today="2026-07-05") == pd.Timestamp("2026-06-30")


def test_target_portfolio_selects_members_by_signal():
    m = _monthly([("2026-06-30", "A.BK", 0.0, 2.0),
                  ("2026-06-30", "B.BK", 0.0, 1.0),
                  ("2026-06-30", "OUT.BK", 0.0, 9.9)])
    tp = target_portfolio(m, _periods(["A", "B"]), {}, pd.Timestamp("2026-06-30"),
                          top_frac=0.5, min_names=2)
    assert list(tp["ticker"]) == ["A.BK"]
    assert tp["weight"].sum() == pytest.approx(1.0)


def test_universe_expiry_raises_loudly():
    m = _monthly([("2027-01-31", "A.BK", 0.0, 1.0)])
    with pytest.raises(ValueError, match="universe table ends"):
        target_portfolio(m, _periods(["A"]), {}, pd.Timestamp("2027-01-31"), min_names=1)


def test_realized_return_counts_missing_names():
    hold = pd.DataFrame({"ticker": ["A.BK", "GONE.BK"], "weight": 0.5,
                         "formation": pd.Timestamp("2026-05-31"), "signal": "mom_12_1"})
    m = _monthly([("2026-06-30", "A.BK", 0.10, 1.0),
                  ("2026-06-30", "B.BK", 0.02, 1.0)])
    port, bench, missing = realized_month_return(
        hold, m, _periods(["A", "B", "GONE"]), {}, pd.Timestamp("2026-06-30"))
    assert port == pytest.approx(0.10)     # mean of the names that still price
    assert missing == 1                    # ...but the gap is reported
    assert bench == pytest.approx(0.06)
