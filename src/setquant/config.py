"""Central configuration: paths, universe, date range."""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
BRONZE_DIR = DATA_DIR / "bronze"
SILVER_DIR = DATA_DIR / "silver"
GOLD_DIR = DATA_DIR / "gold"

# Phase 0: five liquid SET large caps with long history.
PILOT_TICKERS = ["PTT.BK", "AOT.BK", "CPALL.BK", "KBANK.BK", "ADVANC.BK"]

# Full sample: universe files start 2005H1 (pre-registered extension).
START_DATE = "2005-01-01"
