"""Point-in-time index membership — the survivorship-bias control.

The canonical input is reference/universe_set100.csv with one row per
(index, half-year period, symbol), mirroring how SET officially
publishes constituent lists (set.or.th -> Securities List -> List of
Index Constituents; free member login required to download).

A backtest at date t must only see members_on(t). Using today's
membership for the past inflates results, because today's list only
contains survivors.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from setquant import config

UNIVERSE_CSV = config.REPO_ROOT / "reference" / "universe_set100.csv"
REQUIRED_COLUMNS = ["index", "period_start", "period_end", "symbol", "source"]


def load_periods(path: Path | None = None) -> pd.DataFrame:
    """Load and validate the membership table."""
    csv = Path(path) if path is not None else UNIVERSE_CSV
    df = pd.read_csv(csv)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{csv.name}: missing columns {missing}")

    df["period_start"] = pd.to_datetime(df["period_start"])
    df["period_end"] = pd.to_datetime(df["period_end"])
    df["symbol"] = df["symbol"].str.strip().str.upper()

    bad = df[df["period_end"] < df["period_start"]]
    if not bad.empty:
        raise ValueError(f"{csv.name}: period_end before period_start:\n{bad}")

    dup = df.duplicated(subset=["index", "period_start", "symbol"])
    if dup.any():
        raise ValueError(f"{csv.name}: duplicate rows:\n{df[dup]}")

    return df


def members_on(periods: pd.DataFrame, date, index_name: str = "SET100") -> list[str]:
    """Symbols that were index members on the given date."""
    d = pd.Timestamp(date)
    mask = (
        (periods["index"] == index_name)
        & (periods["period_start"] <= d)
        & (periods["period_end"] >= d)
    )
    return sorted(periods.loc[mask, "symbol"].unique())


def all_symbols(periods: pd.DataFrame, index_name: str | None = None) -> list[str]:
    """Every symbol that was EVER a member — this is the download list.

    Includes past members that later dropped out; excluding them is
    exactly the survivorship bias this module exists to prevent.
    """
    df = periods if index_name is None else periods[periods["index"] == index_name]
    return sorted(df["symbol"].unique())


def to_yahoo(symbol: str) -> str:
    """SET symbol -> Yahoo Finance ticker (PTT -> PTT.BK)."""
    return f"{symbol.upper()}.BK"


ALIASES_CSV = config.REPO_ROOT / "reference" / "symbol_aliases.csv"


def load_aliases(path: Path | None = None) -> dict[str, str]:
    """old SET symbol -> the symbol its price history lives under today.

    Renames and restructurings (TMB -> TTB, MTLS -> MTC, ...) leave the
    old symbol in past constituent lists while the vendor serves the
    history under the new one. Without this map those stocks silently
    drop out of backtests — a survivorship bias through the back door.
    """
    csv = Path(path) if path is not None else ALIASES_CSV
    if not csv.exists():
        return {}
    df = pd.read_csv(csv)
    missing = [c for c in ("old_symbol", "new_symbol") if c not in df.columns]
    if missing:
        raise ValueError(f"{csv.name}: missing columns {missing}")

    aliases = {
        str(o).strip().upper(): str(n).strip().upper()
        for o, n in zip(df["old_symbol"], df["new_symbol"])
    }
    chained = set(aliases) & set(aliases.values())
    if chained:
        raise ValueError(f"{csv.name}: chained aliases not allowed: {chained}")
    return aliases


def to_data_symbol(symbol: str, aliases: dict[str, str]) -> str:
    """Resolve a universe symbol to the symbol its data lives under."""
    return aliases.get(symbol.strip().upper(), symbol.strip().upper())
