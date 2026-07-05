"""Phase 0 pilot: download the 5 pilot tickers into data/bronze/."""
import sys
from pathlib import Path

# Allow running directly (python scripts/xxx.py) with no install step.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from setquant import config
from setquant.ingest.yahoo import fetch_ohlcv, save_bronze


def main() -> None:
    print(f"pilot tickers: {', '.join(config.PILOT_TICKERS)}")
    for ticker in config.PILOT_TICKERS:
        df = fetch_ohlcv(ticker)
        path = save_bronze(df, ticker)
        first, last = df["date"].min(), df["date"].max()
        print(f"  {ticker:<10} {len(df):>5} rows  {first:%Y-%m-%d} -> {last:%Y-%m-%d}  {path.name}")


if __name__ == "__main__":
    main()
