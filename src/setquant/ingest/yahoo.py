"""Download daily OHLCV from Yahoo Finance into the bronze layer.

Bronze-layer rule: store what the vendor returns, unmodified except
for column names and types. All cleaning/adjustment happens in silver
(Phase 1). One Parquet file per ticker.
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from setquant import config

# Columns every bronze file must have. Extra vendor columns
# (Adj Close, Dividends, Stock Splits, ...) are kept as-is after these.
CORE_COLUMNS = ["date", "ticker", "open", "high", "low", "close", "volume"]


def _normalize(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Turn a `yf.Ticker(...).history()` frame into the bronze schema."""
    df = raw.copy()
    df.index = pd.to_datetime(df.index)
    if df.index.tz is not None:
        # SET quotes come tagged Asia/Bangkok; we store naive dates.
        df.index = df.index.tz_localize(None)
    df = df.reset_index()
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    df = df.rename(columns={"index": "date", "datetime": "date"})
    df["ticker"] = ticker

    missing = [c for c in CORE_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{ticker}: missing columns {missing}")

    extras = [c for c in df.columns if c not in CORE_COLUMNS]
    return df[CORE_COLUMNS + extras].sort_values("date").reset_index(drop=True)


def fetch_ohlcv(ticker: str, start: str = config.START_DATE) -> pd.DataFrame:
    """Download one ticker's daily history, unadjusted prices."""
    import yfinance as yf  # lazy import: tests must run without network

    raw = yf.Ticker(ticker).history(start=start, auto_adjust=False)
    if raw.empty:
        raise ValueError(f"{ticker}: Yahoo returned no data")
    return _normalize(raw, ticker)


def save_bronze(df: pd.DataFrame, ticker: str, bronze_dir: Path | None = None) -> Path:
    """Write one ticker's frame to data/bronze/<ticker>.parquet."""
    out_dir = Path(bronze_dir) if bronze_dir is not None else config.BRONZE_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{ticker}.parquet"
    # DuckDB is the project's only Parquet engine (reads AND writes) --
    # one engine everywhere means no pandas/pyarrow version skew.
    con = duckdb.connect()
    con.register("bronze_df", df)
    con.execute(f"COPY bronze_df TO '{path.as_posix()}' (FORMAT parquet)")
    con.close()
    return path


def ingest_many(
    tickers: list[str],
    bronze_dir: Path | None = None,
    force: bool = False,
    retries: int = 2,
    pause_seconds: float = 1.0,
) -> dict:
    """Download many tickers, resiliently.

    - Skips tickers whose bronze file already exists (unless force=True),
      so re-running never re-spends requests on data we already have.
    - Retries transient failures, then moves on; one bad ticker must
      not kill a 100-ticker run. Failures are reported, not hidden.
    """
    import time

    out_dir = Path(bronze_dir) if bronze_dir is not None else config.BRONZE_DIR
    done, skipped, failed = [], [], {}

    for ticker in tickers:
        target = out_dir / f"{ticker}.parquet"
        if target.exists() and not force:
            skipped.append(ticker)
            continue

        last_error = None
        for attempt in range(retries + 1):
            try:
                df = fetch_ohlcv(ticker)
                save_bronze(df, ticker, bronze_dir=out_dir)
                done.append(ticker)
                last_error = None
                break
            except Exception as exc:  # noqa: BLE001 - we report, not hide
                last_error = exc
                time.sleep(pause_seconds * (attempt + 1))
        if last_error is not None:
            failed[ticker] = str(last_error)

    return {"done": done, "skipped": skipped, "failed": failed}
