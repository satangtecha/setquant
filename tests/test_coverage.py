import duckdb
import pandas as pd

from setquant.warehouse.coverage import membership_gaps


def _write(df, path):
    con = duckdb.connect()
    con.register("df", df)
    con.execute(f"COPY df TO '{path.as_posix()}' (FORMAT parquet)")
    con.close()


def _bronze(ticker, start, periods_n, tmp_path):
    dates = pd.bdate_range(start, periods=periods_n)
    _write(pd.DataFrame({"date": dates, "ticker": ticker, "close": 1.0}),
           tmp_path / f"{ticker}.parquet")


def test_membership_gaps_flags_silent_late_start(tmp_path):
    periods = pd.DataFrame({
        "index": "SET100",
        "period_start": pd.to_datetime(["2016-01-01"] * 3),
        "period_end": pd.to_datetime(["2016-06-30"] * 3),
        "symbol": ["OK", "LATE", "TMB"],
        "source": "test",
    })
    _bronze("OK.BK", "2016-01-04", 100, tmp_path)
    _bronze("LATE.BK", "2022-04-20", 100, tmp_path)   # SCB-style silent gap
    _bronze("TTB.BK", "2016-01-04", 100, tmp_path)    # TMB history lives under TTB

    gaps = membership_gaps(periods, {"TMB": "TTB"}, bronze_dir=tmp_path)
    by = gaps.set_index("symbol")["status"]

    assert by["OK"] == "ok"
    assert by["LATE"].startswith("late start")
    assert by["TMB"] == "ok"                          # alias resolved the rename


def test_membership_gaps_reports_missing_data(tmp_path):
    periods = pd.DataFrame({
        "index": "SET100",
        "period_start": pd.to_datetime(["2016-01-01"]),
        "period_end": pd.to_datetime(["2016-06-30"]),
        "symbol": ["GONE"], "source": "test",
    })
    _bronze("SOMETHING.BK", "2016-01-04", 30, tmp_path)
    gaps = membership_gaps(periods, {}, bronze_dir=tmp_path)
    assert gaps.iloc[0]["status"] == "no data"
