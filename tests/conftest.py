import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def fake_history() -> pd.DataFrame:
    """Shaped like `yf.Ticker(...).history(auto_adjust=False)` output."""
    idx = pd.date_range("2024-01-02", periods=30, freq="B", tz="Asia/Bangkok")
    rng = np.random.default_rng(42)
    close = 100 + rng.normal(0, 1, len(idx)).cumsum()
    return pd.DataFrame(
        {
            "Open": close + 0.5,
            "High": close + 1.0,
            "Low": close - 1.0,
            "Close": close,
            "Adj Close": close,
            "Volume": rng.integers(100_000, 1_000_000, len(idx)),
            "Dividends": 0.0,
            "Stock Splits": 0.0,
        },
        index=idx,
    )
