# setquant

Point-in-time data pipeline and backtest research on Thai equities (SET100).

An independent research project. Research question: **does cross-sectional
momentum survive real transaction costs in the Thai stock market?**

## Architecture

```
Yahoo Finance (.BK tickers)
        |
     ingest                    src/setquant/ingest/
        v
   bronze (raw Parquet)        data/bronze/   <- Phase 0 (done)
        v
   silver (adjusted, QC'd)     data/silver/   <- Phase 1
        v
   gold (features)             data/gold/     <- Phase 1
        v
   backtest engine             src/setquant/backtest/  <- Phase 2
```

Query layer: **DuckDB over Parquet** — no database server needed.
The Parquet files on disk are the single source of truth.

## Quickstart (Phase 0)

```bash
# 1. install dependencies (Python 3.10+)
pip install duckdb yfinance pandas pytest

# 2. download the 5 pilot tickers into data/bronze/
python scripts/ingest_pilot.py

# 3. sanity-check the warehouse through DuckDB
python scripts/query_demo.py

# 4. run tests (offline — synthetic data, no network needed)
python -m pytest -q
```

No install of the package itself is needed — scripts and tests locate
`src/` on their own. (`pip install -e ".[dev]"` also works if you prefer.)

## Layout

- `src/setquant/ingest/` — vendor downloads, bronze layer
- `src/setquant/warehouse/` — DuckDB views over Parquet
- `src/setquant/backtest/` — Phase 2
- `src/setquant/research/` — notebooks and write-ups
- `tests/` — offline unit tests

## Roadmap

Phase 0 pilot (this) -> Phase 1 full SET100 warehouse with
survivorship-bias handling -> Phase 2 momentum backtest with
walk-forward validation and real costs -> Phase 3 write-up.

## Honest limitations so far

- Yahoo Finance data quality for SET is unverified; cross-checking
  against a second source is planned in Phase 1.
- Bronze stores unadjusted prices plus dividend/split events;
  adjustment logic arrives with the silver layer.
- Historical SET100 membership is not handled yet (survivorship bias) —
  this is the core Phase 1 problem.
