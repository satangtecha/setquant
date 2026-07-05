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

## Quickstart

```bash
# 1. install dependencies (Python 3.10+)
pip install duckdb yfinance pandas pytest

# 2. rebuild the whole warehouse: ingest -> silver -> gold + QC report
python scripts/build_warehouse.py

# 3. run tests (offline — synthetic data, no network needed)
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

## The universe file (survivorship-bias control)

`reference/universe_set100.csv` defines point-in-time index membership:
one row per (index, half-year period, symbol). A backtest at date t only
sees stocks that were members at t — including stocks that later
dropped out or were delisted.

The data is transcribed from SET's official constituent lists
(set.or.th -> Market Data -> List of Companies, Constituents and ISIN
-> **List of Index Constituents**; free member login), one PDF per
half-year, 2016H1-2026H2. `scripts/parse_universe_pdfs.py` parses the
PDFs (dropped into `reference/raw/`, which is gitignored) and enforces
two validators before writing anything: every period must contain row
numbers 1..100 exactly, and the 100 symbols must be strictly
alphabetical — the ordering the documents themselves guarantee. Revised
mid-period lists (mergers, restructurings) supersede the original for
the whole period; a simplification noted in the write-up.

## Symbol aliases and coverage gaps

`reference/symbol_aliases.csv` maps renamed/restructured symbols to
where their history lives today (TMB -> TTB, MTLS -> MTC, ...). Without
it, renamed stocks silently vanish from backtests. The build also
prints a **membership coverage gap** report: any stock whose data
starts later than its first index membership (SCB after the SCBX
restructuring, GULF after the INTUCH amalgamation) is flagged instead
of silently shortening the sample.

## Backtest (Phase 2)

```bash
python scripts/run_momentum.py
```

Pre-registered hypothesis: 12-1 momentum, long the top decile of
point-in-time SET100 members, monthly rebalance, 0.25%/side costs,
vs an equal-weight benchmark of the same universe. The engine enforces
point-in-time membership and no look-ahead (see tests/test_backtest.py
— the tests literally construct a stock with a huge future return and
assert the engine cannot see it). Every run appends to
`research/experiments.csv` — including the failures.

## Roadmap

Phase 0 pilot (done) -> Phase 1 warehouse + point-in-time universe
(done) -> Phase 2 momentum backtest with real costs (this) ->
Phase 3 write-up.

## Honest limitations so far

- Symbol renames (e.g. TMB -> TTB in 2021) are not yet linked into a
  single entity history.
- Yahoo Finance may lack price history for some delisted past members;
  coverage will be quantified against SET's delisting statistics before
  any backtest result is trusted.
- Returns are computed from the vendor's adjusted close: Yahoo's SET
  event feed misses some splits/par changes, so our own event-based
  adjustment (kept as `adj_close_own`) disagrees badly on ~12 names —
  the `adj_median_rel_diff` QC column documents exactly where.
- Series shorter than 60 rows are excluded from silver (`usable=False`
  in the QC report) and re-fetched on the next build.
