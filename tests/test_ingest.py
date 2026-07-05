import duckdb
import pytest

from setquant.ingest.yahoo import CORE_COLUMNS, _normalize, save_bronze


def test_normalize_schema(fake_history):
    df = _normalize(fake_history, "PTT.BK")
    assert list(df.columns[: len(CORE_COLUMNS)]) == CORE_COLUMNS
    assert (df["ticker"] == "PTT.BK").all()
    assert df["date"].dt.tz is None  # timezone stripped
    assert df["date"].is_monotonic_increasing
    assert "adj_close" in df.columns  # vendor extras are kept


def test_normalize_rejects_missing_columns(fake_history):
    broken = fake_history.drop(columns=["Close"])
    with pytest.raises(ValueError, match="missing columns"):
        _normalize(broken, "PTT.BK")


def test_bronze_roundtrip(fake_history, tmp_path):
    df = _normalize(fake_history, "AOT.BK")
    path = save_bronze(df, "AOT.BK", bronze_dir=tmp_path)
    back = duckdb.connect().execute(
        f"SELECT * FROM read_parquet('{path.as_posix()}')"
    ).df()
    assert len(back) == len(df)
    assert list(back.columns) == list(df.columns)
