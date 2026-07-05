"""Generate the paper's figure and LaTeX tables from a backtest run.

Everything the paper reports is produced by this script from the run
CSV — re-run the backtest, re-run this, recompile: the paper updates.
No hand-typed numbers in tables.

Usage:
    python scripts/make_paper_assets.py                 # latest run in research/runs/
    python scripts/make_paper_assets.py --run research/runs/<file>.csv
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from setquant import config
from setquant.backtest.metrics import summarize

PAPER = config.REPO_ROOT / "research" / "paper"
FIGS, TABLES = PAPER / "figures", PAPER / "tables"

SUBPERIODS = [(2016, 2019), (2020, 2022), (2023, 2026)]
COST_GRID = [0.0015, 0.0025, 0.0040]


def latest_run() -> Path:
    runs = sorted((config.REPO_ROOT / "research" / "runs").glob("*.csv"))
    if not runs:
        raise SystemExit("no run CSVs found — run scripts/run_momentum.py first")
    return runs[-1]


def pct(x): return f"{x*100:.2f}\\%"
def num(x): return f"{x:.2f}"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    print(f"wrote {path.relative_to(config.REPO_ROOT)}")


def main_results_table(m: pd.DataFrame) -> str:
    rows = [
        ("Momentum (gross)", summarize(m["gross_ret"])),
        ("Momentum (net)", summarize(m["net_ret"])),
        ("EW benchmark", summarize(m["bench_ret"])),
        ("Top$-$bottom spread (gross)", summarize(m["spread_gross"])),
    ]
    body = "\n".join(
        f"{name} & {pct(s['cagr'])} & {pct(s['ann_vol'])} & {num(s['sharpe'])} "
        f"& {pct(s['max_dd'])} & {num(s['t_stat'])} \\\\"
        for name, s in rows
    )
    active = summarize(m["net_ret"] - m["bench_ret"])
    return (
        "\\begin{tabular}{lrrrrr}\n\\toprule\n"
        " & CAGR & Ann. vol & Sharpe & Max DD & $t$ \\\\\n\\midrule\n"
        + body +
        f"\n\\midrule\nNet active return (vs benchmark) & \\multicolumn{{4}}{{r}}{{{pct(active['cagr'])} per year}} & {num(active['t_stat'])} \\\\\n"
        "\\bottomrule\n\\end{tabular}\n"
    )


def subperiods_table(m: pd.DataFrame) -> str:
    lines = []
    for lo, hi in SUBPERIODS:
        s = m[(m["date"].dt.year >= lo) & (m["date"].dt.year <= hi)]
        if len(s) < 6:
            continue
        lines.append(
            f"{lo}--{hi} & {len(s)} & {pct(summarize(s['net_ret'])['cagr'])} "
            f"& {pct(summarize(s['bench_ret'])['cagr'])} "
            f"& {num(summarize(s['net_ret'] - s['bench_ret'])['t_stat'])} \\\\"
        )
    return (
        "\\begin{tabular}{lrrrr}\n\\toprule\n"
        "Period & Months & Net CAGR & Benchmark CAGR & Active $t$ \\\\\n\\midrule\n"
        + "\n".join(lines) +
        "\n\\bottomrule\n\\end{tabular}\n"
    )


def cost_table(m: pd.DataFrame) -> str:
    lines = []
    for c in COST_GRID:
        net = m["gross_ret"] - c * m["turnover"]
        s = summarize(net)
        lines.append(f"{c*100:.2f}\\% & {pct(s['cagr'])} & {num(s['sharpe'])} \\\\")
    return (
        "\\begin{tabular}{lrr}\n\\toprule\n"
        "Cost per side & Net CAGR & Net Sharpe \\\\\n\\midrule\n"
        + "\n".join(lines) +
        "\n\\bottomrule\n\\end{tabular}\n"
    )


def registry_table() -> str | None:
    reg = config.REPO_ROOT / "research" / "experiments.csv"
    if not reg.exists():
        return None
    df = pd.read_csv(reg)
    lines = [
        f"{r.run_id} & {r.signal} & {r.top_frac} & {r.cost_per_side*100:.2f}\\% "
        f"& {r.net_cagr*100:.2f}\\% & {r.net_sharpe:.2f} & {str(getattr(r, 'note', ''))[:28]} \\\\"
        for r in df.itertuples()
    ]
    return (
        "\\begin{tabular}{lllrrrl}\n\\toprule\n"
        "Run & Signal & Top frac & Cost/side & Net CAGR & Net Sharpe & Note \\\\\n\\midrule\n"
        + "\n".join(lines) +
        "\n\\bottomrule\n\\end{tabular}\n"
    )


def coverage_table() -> str | None:
    """Needs the local warehouse; skipped gracefully when absent."""
    try:
        from setquant.universe import load_aliases, load_periods
        from setquant.warehouse.coverage import membership_gaps
        gaps = membership_gaps(load_periods(), load_aliases())
    except Exception as exc:  # noqa: BLE001
        print(f"coverage table skipped ({exc})")
        return None
    bad = gaps[gaps["status"] != "ok"]
    if bad.empty:
        return None
    lines = [
        f"{r.symbol} & {r.data_symbol} & {r.member_from:%Y-%m} & "
        f"{'--' if pd.isna(r.data_from) else f'{r.data_from:%Y-%m}'} & {r.status} \\\\"
        for r in bad.itertuples()
    ]
    return (
        "\\begin{tabular}{lllll}\n\\toprule\n"
        "Symbol & Data symbol & Member from & Data from & Status \\\\\n\\midrule\n"
        + "\n".join(lines) +
        "\n\\bottomrule\n\\end{tabular}\n"
    )


def equity_figure(m: pd.DataFrame) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    wealth = (1 + m.set_index("date")[["net_ret", "gross_ret", "bench_ret"]]).cumprod()
    dd = wealth["net_ret"] / wealth["net_ret"].cummax() - 1

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(7.0, 5.0), sharex=True,
        gridspec_kw={"height_ratios": [2.4, 1.0]},
    )
    ax1.plot(wealth.index, wealth["net_ret"], lw=1.6, color="#1f4e8c", label="Momentum (net)")
    ax1.plot(wealth.index, wealth["gross_ret"], lw=1.0, ls="--", color="#1f4e8c",
             alpha=0.55, label="Momentum (gross)")
    ax1.plot(wealth.index, wealth["bench_ret"], lw=1.4, color="#8c8c8c", label="EW benchmark")
    ax1.set_yscale("log")
    ax1.set_ylabel("Growth of 1 THB (log scale)")
    ax1.legend(frameon=False, fontsize=9)
    ax1.grid(alpha=0.25, lw=0.5)

    ax2.fill_between(dd.index, dd, 0, color="#1f4e8c", alpha=0.35, lw=0)
    ax2.set_ylabel("Drawdown (net)")
    ax2.grid(alpha=0.25, lw=0.5)

    fig.tight_layout()
    FIGS.mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "png"):
        fig.savefig(FIGS / f"equity_curve.{ext}", dpi=200)
    print(f"wrote {FIGS.relative_to(config.REPO_ROOT)}/equity_curve.pdf/.png")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", type=Path, default=None)
    args = ap.parse_args()

    run = args.run if args.run else latest_run()
    m = pd.read_csv(run, parse_dates=["date", "formation_date"])
    print(f"run: {run.name} ({len(m)} months, "
          f"{m['date'].min():%Y-%m} -> {m['date'].max():%Y-%m})")

    write(TABLES / "main_results.tex", main_results_table(m))
    write(TABLES / "subperiods.tex", subperiods_table(m))
    write(TABLES / "cost_sensitivity.tex", cost_table(m))
    reg = registry_table()
    if reg:
        write(TABLES / "registry.tex", reg)
    cov = coverage_table()
    if cov:
        write(TABLES / "coverage_gaps.tex", cov)
    equity_figure(m)


if __name__ == "__main__":
    main()
