"""Parse official SET constituent PDFs into reference/universe_set100.csv.

Input:  reference/raw/*.pdf — the per-half-year "SET50 & SET100 Index
        Constituents" files downloaded from set.or.th (member login).
        Raw PDFs are gitignored (they are SET's documents); only this
        transcription, with file names as `source`, is committed.

Rules:
- If a period has a revised file (revise / v2 / merger / psh / update
  in the name), the revised list is used for the WHOLE period.
  Simplification, documented in the paper's limitations.
- Every parsed SET100 section must contain row numbers 1..100 exactly;
  anything else aborts loudly rather than committing bad data.

Usage:
    python scripts/parse_universe_pdfs.py
    python scripts/parse_universe_pdfs.py --raw-dir path --out path
"""
import argparse
import csv
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

SUFFIX_MARKERS = ("revise", "v2", "merger", "psh", "update")
ROW_RE = re.compile(r"(?:^|\s)(\d{1,3})\*?\s+\*?([A-Z][A-Z0-9]{0,7})(?=\s|$)")  # \*? = footnote markers: "61* PSH", "15 *BEC"
SET100_HEADER = re.compile(r"^\s*SET100\b", re.MULTILINE)


def pdf_text(path: Path, layout: bool = True) -> str:
    cmd = ["pdftotext"] + (["-layout"] if layout else []) + [str(path), "-"]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return out.stdout


def _set100_section(text: str, fname: str) -> str:
    m = SET100_HEADER.search(text)
    if m is None:
        raise ValueError(f"{fname}: SET100 section header not found")
    section = text[m.start():]
    stop = re.search(r"^\s*Reserve list", section, re.MULTILINE | re.IGNORECASE)
    return section[: stop.start()] if stop else section


def parse_period(name: str):
    m = re.search(r"[Hh]([12])[-_]?((?:19|20)\d{2})", name)
    if not m:
        return None
    half, year = int(m.group(1)), int(m.group(2))
    if half == 1:
        return year, half, f"{year}-01-01", f"{year}-06-30"
    return year, half, f"{year}-07-01", f"{year}-12-31"


def extract_set100(path: Path, fname: str) -> list[str]:
    section = _set100_section(pdf_text(path, layout=True), fname)

    rows: dict[int, str] = {}
    for line in section.splitlines():
        for num_s, sym in ROW_RE.findall(line):
            num = int(num_s)
            if 1 <= num <= 100:
                rows.setdefault(num, sym)
        if len(rows) == 100:
            break  # SET100 complete; later numbered lists (reserve
                   # lists, change notes) must not bleed in

    missing = [n for n in range(1, 101) if n not in rows]
    if missing:
        # -layout occasionally garbles a few lines. Recover from the raw
        # (reading-order) text: for each missing row number, collect every
        # "standalone number -> symbol" candidate in the whole file, then
        # keep the one that fits the list's own alphabetical ordering
        # between the nearest known neighbours. (Every SET constituent
        # PDF is explicitly "Rank by alphabet".)
        raw = pdf_text(path, layout=False)
        used = set(rows.values())
        for n in sorted(missing):
            lower = max((v for k, v in rows.items() if k < n), default="")
            upper = min((v for k, v in rows.items() if k > n), default="ZZZZZZZZZ")
            candidates = []
            for m in re.finditer(
                rf"^\s*{n}\*?(?:\s*\n+\s*|\s+)\*?([A-Z][A-Z0-9]{{0,7}})(?=\s|$)",
                raw, re.MULTILINE,
            ):
                sym = m.group(1)
                if sym not in used and lower < sym < upper:
                    candidates.append(sym)
            if len(set(candidates)) == 1:
                rows[n] = candidates[0]
                used.add(candidates[0])
                missing.remove(n)

    if missing:
        raise ValueError(f"{fname}: missing SET100 row numbers {missing}")

    # Final validator: every SET constituent list is "Rank by alphabet",
    # so the 100 symbols must be strictly increasing. This catches any
    # wrong pick regardless of how messy the PDF text order was.
    # (Duplicate sightings with different symbols are fine — revised
    # files repeat the list; first complete alphabetical pass wins.)
    symbols = [rows[n] for n in range(1, 101)]
    breaks = [
        (i + 1, symbols[i], symbols[i + 1])
        for i in range(99) if symbols[i] >= symbols[i + 1]
    ]
    if breaks:
        raise ValueError(f"{fname}: alphabetical order broken at {breaks[:5]}")
    return symbols


def choose_file(candidates: list[Path]) -> Path:
    """Prefer the revised/updated version of a period's list."""
    def rank(p: Path):
        n = p.name.lower()
        return (any(k in n for k in SUFFIX_MARKERS), n)
    return sorted(candidates, key=rank)[-1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", default=REPO_ROOT / "reference" / "raw", type=Path)
    ap.add_argument("--out", default=REPO_ROOT / "reference" / "universe_set100.csv", type=Path)
    args = ap.parse_args()

    by_period = defaultdict(list)
    for pdf in sorted(args.raw_dir.glob("*.pdf")):
        period = parse_period(pdf.name)
        if period is None:
            print(f"SKIP (no H1/H2-year in name): {pdf.name}")
            continue
        by_period[period].append(pdf)

    records = []
    for (year, half, start, end), files in sorted(by_period.items()):
        chosen = choose_file(files)
        symbols = extract_set100(chosen, chosen.name)
        for sym in sorted(symbols):
            records.append(("SET100", start, end, sym, chosen.name))
        skipped = [f.name for f in files if f != chosen]
        note = f"  (skipped: {', '.join(skipped)})" if skipped else ""
        print(f"{year}H{half}: 100 symbols from {chosen.name}{note}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["index", "period_start", "period_end", "symbol", "source"])
        w.writerows(records)

    n_periods = len(by_period)
    n_symbols = len({r[3] for r in records})
    print(f"\nwrote {args.out}: {len(records)} rows, "
          f"{n_periods} periods, {n_symbols} unique symbols ever in SET100")


if __name__ == "__main__":
    main()
