import duckdb
import numpy as np
import pandas as pd
import pytest

from setquant.warehouse.silver import build_silver


def _bronze_frame(ticker, closes, dividends=None, splits=None, start="2024-01-01"):
    n = len(closes)
    dates = pd.bdate_range(start, periods=n)
    closes = pd.Series(closes, dtype=float)
    return pd.DataFrame({
        "date": dates,
        "ticker": ticker,
        "open": closes,
        "high": closes + 1,
        "low": closes - 1,
        "close": closes,
        "volume": 1000,
        "dividends": dividends if dividends is not None else [0.0] * n,
        "stock_splits": splits if splits is not None else [0.0] * n,
    })


def _write_bronze(df, bronze_dir, ticker):
    con = duckdb.connect()
    con.register("df", df)
    con.execute(f"COPY df TO '{(bronze_dir / f'{ticker}.parquet').as_posix()}' (FORMAT parquet)")
    con.close()


def test_dividend_adjustment_makes_total_return_flat(tmp_path):
    # price drops exactly by the dividend on ex-date -> holder wealth is
    # unchanged -> adjusted returns must all be ~0
    closes = [100, 100, 100, 95, 95, 95]
    dividends = [0, 0, 0, 5, 0, 0]
    _write_bronze(_bronze_frame("DIV", closes, dividends=dividends), tmp_path, "DIV")

    path = build_silver(bronze_dir=tmp_path, silver_dir=tmp_path / "silver")
    silver = pd.read_parquet(path) if False else duckdb.connect().execute(
        f"SELECT * FROM read_parquet('{path.as_posix()}')").df()

    rets = silver["ret"].dropna()
    assert np.abs(rets).max() < 1e-9


def test_split_adjustment_makes_return_flat(tmp_path):
    # 2:1 split on day 2: close halves but nothing happened economically
    closes = [100, 100, 50, 50]
    splits = [0, 0, 2.0, 0]
    _write_bronze(_bronze_frame("SPL", closes, splits=splits), tmp_path, "SPL")

    path = build_silver(bronze_dir=tmp_path, silver_dir=tmp_path / "silver")
    silver = duckdb.connect().execute(
        f"SELECT * FROM read_parquet('{path.as_posix()}')").df()

    rets = silver["ret"].dropna()
    assert np.abs(rets).max() < 1e-9


def test_bad_ohlc_is_flagged_not_fixed(tmp_path):
    df = _bronze_frame("BAD", [100, 100, 100, 100])
    df.loc[2, "high"] = 90  # high < low: impossible bar
    _write_bronze(df, tmp_path, "BAD")

    build_silver(bronze_dir=tmp_path, silver_dir=tmp_path / "silver")
    qc = duckdb.connect().execute(
        f"SELECT * FROM read_parquet('{(tmp_path / 'silver' / 'qc_summary.parquet').as_posix()}')").df()

    assert int(qc.loc[qc["ticker"] == "BAD", "bad_ohlc"].iloc[0]) == 1
