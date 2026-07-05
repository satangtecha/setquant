import duckdb
import numpy as np
import pandas as pd

from setquant.warehouse.gold import build_gold


def test_momentum_12_1(tmp_path):
    # 14 months of daily prices doubling once: engineered so that
    # mom_12_1 is checkable by hand.
    dates = pd.bdate_range("2023-01-01", "2024-03-31")
    prices = pd.DataFrame({
        "date": dates,
        "ticker": "TST",
        # +1% per business day -> known monthly structure
        "adj_close_used": 100.0 * (1.01 ** np.arange(len(dates))),
    })
    silver = tmp_path / "silver"
    silver.mkdir()
    con = duckdb.connect()
    con.register("df", prices)
    con.execute(f"COPY df TO '{(silver / 'prices.parquet').as_posix()}' (FORMAT parquet)")
    con.close()

    path = build_gold(silver_dir=silver, gold_dir=tmp_path / "gold")
    m = duckdb.connect().execute(
        f"SELECT * FROM read_parquet('{path.as_posix()}') ORDER BY date").df()

    row = m.iloc[-1]  # 2024-03 month end
    m_indexed = m.set_index("date")["adj_close"]
    expected = m_indexed.iloc[-2] / m_indexed.iloc[-13] - 1
    assert abs(row["mom_12_1"] - expected) < 1e-12
    assert m["mom_12_1"].notna().sum() >= 1
