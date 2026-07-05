"""Phase 0 definition of done: query the bronze layer through DuckDB."""
import sys
from pathlib import Path

# Allow running directly (python scripts/xxx.py) with no install step.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from setquant.warehouse.db import connect, coverage


def main() -> None:
    con = connect()
    print(coverage(con).to_string(index=False))


if __name__ == "__main__":
    main()
