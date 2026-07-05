from setquant.ingest.yahoo import _normalize, save_bronze
from setquant.warehouse.db import connect, coverage


def test_coverage_over_two_tickers(fake_history, tmp_path):
    for ticker in ["PTT.BK", "AOT.BK"]:
        save_bronze(_normalize(fake_history, ticker), ticker, bronze_dir=tmp_path)

    con = connect(bronze_dir=tmp_path)
    cov = coverage(con)

    assert list(cov["ticker"]) == ["AOT.BK", "PTT.BK"]  # sorted
    assert (cov["rows"] == len(fake_history)).all()
