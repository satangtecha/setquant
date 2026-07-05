"""Run the pre-registered momentum study and log it to the registry.

Hypothesis (registered BEFORE seeing results, 2026-07-05):
    Cross-sectional 12-1 momentum, long the top decile of SET100
    members, rebalanced monthly, beats an equal-weight benchmark of the
    same point-in-time universe after real transaction costs.

Cost assumption: 0.25% per side (SET retail online commission ~0.157%
incl. VAT + spread/slippage allowance). Sensitivity at 0.15% and 0.40%.

Usage:
    python scripts/run_momentum.py
    python scripts/run_momentum.py --top-frac 0.2 --note "quintile variant"
"""
import argparse
import csv
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import duckdb

from setquant import config
from setquant.backtest.engine import run_monthly_backtest
from setquant.backtest.metrics import summarize
from setquant.universe import load_aliases, load_periods

REGISTRY = config.REPO_ROOT / "research" / "experiments.csv"
RUNS_DIR = config.REPO_ROOT / "research" / "runs"
REGISTRY_FIELDS = [
    "run_id", "timestamp_utc", "signal", "top_frac", "cost_per_side", "min_names",
    "n_months", "gross_cagr", "net_cagr", "net_sharpe", "net_max_dd",
    "bench_cagr", "bench_sharpe", "avg_turnover", "spread_t_stat", "note",
]


def fmt(x, pct=True):
    return f"{x*100:6.2f}%" if pct else f"{x:6.2f}"


def print_block(title, m):
    print(f"  {title:22s} CAGR {fmt(m['cagr'])}  vol {fmt(m['ann_vol'])}  "
          f"Sharpe {fmt(m['sharpe'], pct=False)}  MaxDD {fmt(m['max_dd'])}  "
          f"t {fmt(m['t_stat'], pct=False)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--signal", default="mom_12_1")
    ap.add_argument("--top-frac", type=float, default=0.10)
    ap.add_argument("--cost", type=float, default=0.0025)
    ap.add_argument("--min-names", type=int, default=20)
    ap.add_argument("--note", default="")
    args = ap.parse_args()

    con = duckdb.connect()
    monthly = con.execute(
        f"SELECT * FROM read_parquet('{(config.GOLD_DIR / 'monthly.parquet').as_posix()}')"
    ).df()
    con.close()
    periods, aliases = load_periods(), load_aliases()

    res = run_monthly_backtest(
        monthly, periods, aliases, signal=args.signal,
        top_frac=args.top_frac, cost_per_side=args.cost, min_names=args.min_names,
    )
    m = res.monthly
    if m.empty:
        print("no backtest months produced — is the warehouse built?")
        return

    print(f"params: {res.params}")
    print(f"sample: {m['date'].min():%Y-%m} -> {m['date'].max():%Y-%m} "
          f"({len(m)} months, avg {m['n_eligible'].mean():.0f} eligible, "
          f"{m['n_held'].iloc[0]} held, avg turnover {m['turnover'].mean()*100:.0f}%/mo)\n")

    g, n, b = summarize(m["gross_ret"]), summarize(m["net_ret"]), summarize(m["bench_ret"])
    sp = summarize(m["spread_gross"])
    active = summarize(m["net_ret"] - m["bench_ret"])
    print("full period:")
    print_block("momentum gross", g)
    print_block("momentum net", n)
    print_block("EW benchmark", b)
    print_block("top-bottom spread", sp)
    print(f"  {'net vs bench':22s} mean {fmt(active['cagr'])} /yr  t {fmt(active['t_stat'], pct=False)}\n")

    print("sub-periods (net | bench CAGR):")
    for lo, hi in [(2016, 2019), (2020, 2022), (2023, 2026)]:
        s = m[(m["date"].dt.year >= lo) & (m["date"].dt.year <= hi)]
        if len(s) < 6:
            continue
        print(f"  {lo}-{hi}: {fmt(summarize(s['net_ret'])['cagr'])} | "
              f"{fmt(summarize(s['bench_ret'])['cagr'])}  ({len(s)} mo)")

    print("\ncost sensitivity (net CAGR | net Sharpe):")
    for c in (0.0015, 0.0025, 0.0040):
        r = run_monthly_backtest(monthly, periods, aliases, signal=args.signal,
                                 top_frac=args.top_frac, cost_per_side=c,
                                 min_names=args.min_names)
        s = summarize(r.monthly["net_ret"])
        print(f"  {c*100:.2f}%/side: {fmt(s['cagr'])} | {s['sharpe']:.2f}")

    # ---- experiment registry: every run is recorded, success or not
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    m.to_csv(RUNS_DIR / f"{run_id}.csv", index=False)

    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    new_file = not REGISTRY.exists()
    with open(REGISTRY, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=REGISTRY_FIELDS)
        if new_file:
            w.writeheader()
        w.writerow({
            "run_id": run_id,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "signal": args.signal, "top_frac": args.top_frac,
            "cost_per_side": args.cost, "min_names": args.min_names,
            "n_months": len(m),
            "gross_cagr": round(g["cagr"], 6), "net_cagr": round(n["cagr"], 6),
            "net_sharpe": round(n["sharpe"], 4), "net_max_dd": round(n["max_dd"], 6),
            "bench_cagr": round(b["cagr"], 6), "bench_sharpe": round(b["sharpe"], 4),
            "avg_turnover": round(float(m["turnover"].mean()), 4),
            "spread_t_stat": round(sp["t_stat"], 4),
            "note": args.note,
        })
    print(f"\nlogged to research/experiments.csv as {run_id}")


if __name__ == "__main__":
    main()
