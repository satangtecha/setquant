"""Rebuild the whole warehouse with one command (Phase 1 definition of done).

Usage:
    python scripts/build_warehouse.py             # ingest missing -> silver -> gold
    python scripts/build_warehouse.py --offline   # skip downloads, rebuild silver/gold
    python scripts/build_warehouse.py --force     # re-download everything
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from setquant import config
from setquant.ingest.yahoo import ingest_many
from setquant.universe import all_symbols, load_periods, to_yahoo
from setquant.warehouse.gold import build_gold
from setquant.warehouse.silver import build_silver


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="skip downloads")
    ap.add_argument("--force", action="store_true", help="re-download everything")
    args = ap.parse_args()

    periods = load_periods()
    placeholder = periods["source"].str.contains("placeholder").any()
    tickers = [to_yahoo(s) for s in all_symbols(periods)]
    print(f"universe: {len(tickers)} symbols"
          + ("  [WARNING: placeholder universe — see README]" if placeholder else ""))

    if not args.offline:
        result = ingest_many(tickers, force=args.force)
        print(f"ingest: {len(result['done'])} downloaded, "
              f"{len(result['skipped'])} skipped (already present), "
              f"{len(result['failed'])} failed")
        for ticker, err in result["failed"].items():
            print(f"  FAILED {ticker}: {err}")

    build_silver()
    build_gold()

    from setquant.warehouse.db import connect, coverage
    con = connect()
    print("\nbronze coverage:")
    print(coverage(con).to_string(index=False))
    print("\nsilver QC summary:")
    qc = con.execute("SELECT * FROM read_parquet('"
                     + (config.SILVER_DIR / "qc_summary.parquet").as_posix()
                     + "')").df()
    print(qc.to_string(index=False))
    print("\ngold_monthly sample:")
    print(con.execute(
        "SELECT * FROM gold_monthly WHERE mom_12_1 IS NOT NULL ORDER BY date DESC LIMIT 5"
    ).df().to_string(index=False))


if __name__ == "__main__":
    main()
