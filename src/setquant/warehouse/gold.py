"""Gold layer: research-ready monthly features.

mom_12_1 at month t = adj_close[t-1] / adj_close[t-12] - 1
(12-month return, skipping the most recent month — the classic
cross-sectional momentum signal; the skip avoids short-term reversal).
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from setquant import config


def build_gold(silver_dir: Path | None = None, gold_dir: Path | None = None) -> Path:
    silver = Path(silver_dir) if silver_dir is not None else config.SILVER_DIR
    out_dir = Path(gold_dir) if gold_dir is not None else config.GOLD_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    prices = con.execute(
        f"SELECT date, ticker, adj_close_used FROM read_parquet('{(silver / 'prices.parquet').as_posix()}')"
    ).df()

    frames = []
    for ticker, g in prices.groupby("ticker"):
        m = (
            g.set_index("date")["adj_close_used"]
            .sort_index()
            .resample("ME")
            .last()
            .to_frame("adj_close")
        )
        m["monthly_ret"] = m["adj_close"].pct_change()
        m["mom_12_1"] = m["adj_close"].shift(1) / m["adj_close"].shift(12) - 1
        m["mom_6_1"] = m["adj_close"].shift(1) / m["adj_close"].shift(6) - 1
        m["ticker"] = ticker
        frames.append(m.reset_index().rename(columns={"index": "date"}))

    monthly = pd.concat(frames, ignore_index=True)
    con.register("monthly_df", monthly)
    path = out_dir / "monthly.parquet"
    con.execute(f"COPY monthly_df TO '{path.as_posix()}' (FORMAT parquet)")
    con.close()
    return path
