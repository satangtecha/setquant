"""DuckDB query layer over the Parquet warehouse.

DuckDB reads Parquet files in place — no database server, nothing to
keep in sync. Views are recreated on every connect, so the Parquet
files on disk are always the single source of truth.
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from setquant import config


def connect(bronze_dir: Path | None = None) -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB connection with a `bronze_prices` view."""
    bronze = Path(bronze_dir) if bronze_dir is not None else config.BRONZE_DIR
    con = duckdb.connect()
    pattern = (bronze / "*.parquet").as_posix()
    con.execute(
        f"CREATE OR REPLACE VIEW bronze_prices AS "
        f"SELECT * FROM read_parquet('{pattern}')"
    )
    return con


def coverage(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Row count and date range per ticker — the Phase 0 sanity check."""
    return con.execute(
        """
        SELECT ticker,
               count(*)  AS rows,
               min(date) AS first_day,
               max(date) AS last_day
        FROM bronze_prices
        GROUP BY ticker
        ORDER BY ticker
        """
    ).df()
