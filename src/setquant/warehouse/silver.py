"""Silver layer: adjusted prices + data-quality flags.

Rules of this layer:
- Bronze is never modified. Silver documents every change it makes.
- We compute our own adjusted close from dividend/split events and
  cross-check it against the vendor's adj_close. Disagreement is a
  data-quality signal, not something to hide.

Adjustment method (standard backward adjustment):
On an event day t, the factor  f_t = ((prev_close - div_t) / prev_close) / split_t
applies to all prices strictly BEFORE t, so that returns computed from
the adjusted series equal total returns (dividends reinvested).
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from setquant import config

MARKET_DAY_QUORUM = 0.30   # a date is a market day if >=30% of tickers traded
EXTREME_DAILY_RETURN = 0.50
ADJ_MISMATCH_TOL = 0.005   # 0.5% median disagreement with vendor adj_close


def _load_bronze(bronze_dir: Path) -> pd.DataFrame:
    pattern = (Path(bronze_dir) / "*.parquet").as_posix()
    con = duckdb.connect()
    df = con.execute(f"SELECT * FROM read_parquet('{pattern}')").df()
    con.close()
    if df.empty:
        raise ValueError(f"no bronze data found under {bronze_dir}")
    return df


def _market_calendar(df: pd.DataFrame) -> pd.DatetimeIndex:
    """Dates where enough of the universe traded. We cannot know the
    official SET holiday calendar from price files alone, so we infer
    market days cross-sectionally."""
    n_tickers = df["ticker"].nunique()
    quorum = max(1, int(np.ceil(MARKET_DAY_QUORUM * n_tickers)))
    counts = df.groupby("date")["ticker"].nunique()
    return pd.DatetimeIndex(counts[counts >= quorum].index).sort_values()


def _adjust_one(g: pd.DataFrame) -> pd.DataFrame:
    """Compute our own adjusted close for a single ticker."""
    g = g.sort_values("date").drop_duplicates(subset="date").reset_index(drop=True)

    div = g["dividends"].fillna(0.0) if "dividends" in g.columns else 0.0
    split = g["stock_splits"] if "stock_splits" in g.columns else None
    split = split.replace(0.0, 1.0).fillna(1.0) if split is not None else 1.0

    prev_close = g["close"].shift(1)
    event_factor = ((prev_close - div) / prev_close) / split
    event_factor = event_factor.fillna(1.0).clip(lower=1e-9)

    # factor applying at row i = product of event factors of all rows AFTER i
    cum = event_factor.iloc[::-1].cumprod().iloc[::-1]
    adj_factor = cum.shift(-1).fillna(1.0)

    g["adj_close_own"] = g["close"] * adj_factor
    g["ret"] = g["adj_close_own"].pct_change()
    return g


def _qc_flags(g: pd.DataFrame, calendar: pd.DatetimeIndex) -> pd.DataFrame:
    g = g.copy()
    g["flag_bad_ohlc"] = (g["high"] < g["low"]) | (g["low"] <= 0) | (g["close"] <= 0)
    g["flag_extreme_return"] = g["ret"].abs() > EXTREME_DAILY_RETURN

    if "adj_close" in g.columns:
        rel = (g["adj_close_own"] - g["adj_close"]).abs() / g["adj_close"].abs()
        g["adj_rel_diff"] = rel
    else:
        g["adj_rel_diff"] = np.nan
    return g


def build_silver(bronze_dir: Path | None = None, silver_dir: Path | None = None) -> Path:
    """Bronze -> silver. Returns the path of silver/prices.parquet."""
    bronze = Path(bronze_dir) if bronze_dir is not None else config.BRONZE_DIR
    out_dir = Path(silver_dir) if silver_dir is not None else config.SILVER_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    raw = _load_bronze(bronze)
    calendar = _market_calendar(raw)

    frames, qc_rows = [], []
    for ticker, g in raw.groupby("ticker"):
        g = _adjust_one(g)
        g = _qc_flags(g, calendar)

        active = calendar[(calendar >= g["date"].min()) & (calendar <= g["date"].max())]
        n_missing = len(active.difference(pd.DatetimeIndex(g["date"])))

        qc_rows.append({
            "ticker": ticker,
            "rows": len(g),
            "first_day": g["date"].min(),
            "last_day": g["date"].max(),
            "missing_market_days": n_missing,
            "bad_ohlc": int(g["flag_bad_ohlc"].sum()),
            "extreme_returns": int(g["flag_extreme_return"].sum()),
            "adj_median_rel_diff": (
                float(g["adj_rel_diff"].median())
                if g["adj_rel_diff"].notna().any() else float("nan")
            ),
        })
        frames.append(g)

    prices = pd.concat(frames, ignore_index=True)
    qc = pd.DataFrame(qc_rows)

    con = duckdb.connect()
    con.register("prices_df", prices)
    con.register("qc_df", qc)
    prices_path = out_dir / "prices.parquet"
    con.execute(f"COPY prices_df TO '{prices_path.as_posix()}' (FORMAT parquet)")
    con.execute(f"COPY qc_df TO '{(out_dir / 'qc_summary.parquet').as_posix()}' (FORMAT parquet)")
    con.close()
    return prices_path
