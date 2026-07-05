"""Membership-vs-data coverage: catch SILENT history gaps.

A ticker that fails to download is loud. A ticker whose data starts
years after it entered the index (SCB after the SCBX restructuring,
GULF after the INTUCH amalgamation) is silent — and silently biases a
backtest, because the missing early years are exactly when the old
entity existed. This check makes every such gap visible.
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from setquant import config
from setquant.universe import to_data_symbol, to_yahoo

LATE_START_TOLERANCE_DAYS = 7


def _bronze_ranges(bronze_dir: Path) -> dict[str, tuple[pd.Timestamp, pd.Timestamp, int]]:
    pattern = (Path(bronze_dir) / "*.parquet").as_posix()
    con = duckdb.connect()
    try:
        df = con.execute(
            f"SELECT ticker, min(date) AS lo, max(date) AS hi, count(*) AS n "
            f"FROM read_parquet('{pattern}') GROUP BY ticker"
        ).df()
    except duckdb.IOException:
        return {}
    finally:
        con.close()
    return {r.ticker: (pd.Timestamp(r.lo), pd.Timestamp(r.hi), int(r.n)) for r in df.itertuples()}


def membership_gaps(
    periods: pd.DataFrame,
    aliases: dict[str, str],
    bronze_dir: Path | None = None,
) -> pd.DataFrame:
    """One row per universe symbol: where does its data fall short of
    its membership window?"""
    bronze = Path(bronze_dir) if bronze_dir is not None else config.BRONZE_DIR
    ranges = _bronze_ranges(bronze)

    rows = []
    for symbol, g in periods.groupby("symbol"):
        data_symbol = to_data_symbol(symbol, aliases)
        member_from, member_to = g["period_start"].min(), g["period_end"].max()
        found = ranges.get(to_yahoo(data_symbol))

        if found is None:
            status, data_from, data_to, n = "no data", pd.NaT, pd.NaT, 0
        else:
            data_from, data_to, n = found
            late = (data_from - member_from).days
            status = f"late start (+{late}d)" if late > LATE_START_TOLERANCE_DAYS else "ok"

        rows.append({
            "symbol": symbol, "data_symbol": data_symbol,
            "member_from": member_from, "member_to": member_to,
            "data_from": data_from, "data_to": data_to, "rows": n,
            "status": status,
        })
    return pd.DataFrame(rows).sort_values(["status", "symbol"]).reset_index(drop=True)
