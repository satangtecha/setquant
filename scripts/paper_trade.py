"""Monthly live paper-trading run: settle last month, form this month, log it.

Run ONCE at the start of each calendar month (a reminder is fine; the
discipline is what makes the log credible):

    python scripts/paper_trade.py            # refresh data + settle + rebalance
    python scripts/paper_trade.py --status   # just show current holdings

What it writes (all committed to git — history is never edited):
    research/live/holdings/YYYY-MM.csv    the portfolio formed that month-end
    research/live/trades_YYYY-MM.csv      BUY/SELL/HOLD vs previous portfolio
    research/live/performance.csv         realized month returns vs benchmark
    research/live/live_log.csv            one audit row per rebalance
"""
import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import duckdb
import pandas as pd

from setquant import config
from setquant.backtest.live import (
    latest_formation_month,
    realized_month_return,
    target_portfolio,
)
from setquant.ingest.yahoo import ingest_many
from setquant.universe import (
    all_symbols,
    load_aliases,
    load_periods,
    to_data_symbol,
    to_yahoo,
)
from setquant.warehouse.gold import build_gold
from setquant.warehouse.silver import build_silver

LIVE = config.REPO_ROOT / "research" / "live"
HOLDINGS = LIVE / "holdings"


def load_gold() -> pd.DataFrame:
    con = duckdb.connect()
    df = con.execute(
        f"SELECT * FROM read_parquet('{(config.GOLD_DIR / 'monthly.parquet').as_posix()}')"
    ).df()
    con.close()
    df["date"] = pd.to_datetime(df["date"])
    return df


def previous_holdings() -> pd.DataFrame | None:
    files = sorted(HOLDINGS.glob("*.csv"))
    if not files:
        return None
    df = pd.read_csv(files[-1], parse_dates=["formation"])
    return df


def settle(prev: pd.DataFrame, monthly, periods, aliases, upto: pd.Timestamp) -> None:
    """Realize every complete month between the previous formation and now.
    Buy-and-hold across a skipped month, honestly noted."""
    prev_formation = pd.Timestamp(prev["formation"].iloc[0])
    months = sorted(m for m in monthly["date"].unique()
                    if prev_formation < pd.Timestamp(m) <= upto)
    if not months:
        return
    perf_path = LIVE / "performance.csv"
    new_file = not perf_path.exists()
    with open(perf_path, "a", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["month", "formation", "port_ret", "bench_ret",
                        "n_held", "n_missing", "note"])
        for i, m in enumerate(months):
            port, bench, missing = realized_month_return(
                prev, monthly, periods, aliases, pd.Timestamp(m))
            note = "buy-and-hold over skipped month" if i > 0 else ""
            w.writerow([f"{pd.Timestamp(m):%Y-%m-%d}",
                        f"{prev_formation:%Y-%m-%d}",
                        f"{port:.6f}", f"{bench:.6f}",
                        len(prev), missing, note])
            print(f"settled {pd.Timestamp(m):%Y-%m}: portfolio {port*100:+.2f}% "
                  f"| benchmark {bench*100:+.2f}%"
                  + (f" | {missing} name(s) missing data" if missing else ""))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true", help="show holdings, change nothing")
    ap.add_argument("--skip-refresh", action="store_true", help="use existing warehouse")
    ap.add_argument("--signal", default="mom_12_1")
    ap.add_argument("--top-frac", type=float, default=0.10)
    ap.add_argument("--min-names", type=int, default=20)
    ap.add_argument("--note", default="")
    args = ap.parse_args()

    if args.status:
        prev = previous_holdings()
        if prev is None:
            print("no live portfolio yet — run without --status to start")
            return
        print(prev.to_string(index=False))
        return

    periods, aliases = load_periods(), load_aliases()

    if not args.skip_refresh:
        tickers = sorted({to_yahoo(to_data_symbol(s, aliases))
                          for s in all_symbols(periods)})
        result = ingest_many(tickers, stale_days=3)
        print(f"refresh: {len(result['done'])} updated, "
              f"{len(result['skipped'])} fresh, {len(result['failed'])} failed")
        build_silver()
        build_gold()

    monthly = load_gold()
    formation = latest_formation_month(monthly)

    prev = previous_holdings()
    if prev is not None:
        if pd.Timestamp(prev["formation"].iloc[0]) >= formation:
            print(f"already rebalanced for {formation:%Y-%m} — "
                  "one rebalance per month is the rule; nothing to do")
            return
        settle(prev, monthly, periods, aliases, upto=formation)

    target = target_portfolio(
        monthly, periods, aliases, formation,
        signal=args.signal, top_frac=args.top_frac, min_names=args.min_names,
    )

    # trades vs previous portfolio
    old = set() if prev is None else set(prev["ticker"])
    new = set(target["ticker"])
    trades = (
        [("SELL", t) for t in sorted(old - new)]
        + [("BUY", t) for t in sorted(new - old)]
        + [("HOLD", t) for t in sorted(new & old)]
    )

    HOLDINGS.mkdir(parents=True, exist_ok=True)
    target.to_csv(HOLDINGS / f"{formation:%Y-%m}.csv", index=False)
    with open(LIVE / f"trades_{formation:%Y-%m}.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["action", "ticker", "target_weight"])
        wgt = float(target["weight"].iloc[0])
        for action, t in trades:
            w.writerow([action, t, f"{wgt:.6f}" if action != "SELL" else "0"])

    log_path = LIVE / "live_log.csv"
    new_file = not log_path.exists()
    with open(log_path, "a", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["run_utc", "formation", "signal", "top_frac",
                        "n_held", "tickers", "note"])
        w.writerow([datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    f"{formation:%Y-%m-%d}", args.signal, args.top_frac,
                    len(target), " ".join(target["ticker"]), args.note])

    print(f"\nformed {formation:%Y-%m} portfolio ({len(target)} names, "
          f"weight {float(target['weight'].iloc[0])*100:.1f}% each):")
    for action, t in trades:
        print(f"  {action:4s} {t}")
    print("\nnow commit the log:")
    print('  git add research/live ; git commit -m "Paper trade '
          f'{formation:%Y-%m}" ; git push')


if __name__ == "__main__":
    main()
