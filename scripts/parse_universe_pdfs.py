"""Parse official SET constituent documents into reference/universe_set100.csv.

Input:  reference/raw/ — the per-half-year "SET50 & SET100 Index
        Constituents" files downloaded from set.or.th (member login).
        2015 onward these are PDFs; 2005-2014 they are .xls workbooks.
        Raw files are gitignored (they are SET's documents); only this
        transcription, with file names as `source`, is committed.

Validators (a list is rejected unless):
- it contains row numbers 1..100 exactly, each mapped to one symbol;
- PDF-era lists (alphabetical by construction, "Rank by alphabet")
  must be strictly alphabetical — unless the extraction was clean and
  conflict-free, which covers the sector-ordered 2015 layout;
- XLS-era lists are sector-ordered by design, so only completeness
  and conflict-freeness are enforced there.

Rules:
- If a period has a revised file (revise / v2 / merger / psh / update
  in the name), the revised list is used for the WHOLE period.
- PDF text extraction uses poppler's pdftotext when available and
  falls back to pdfplumber (pure Python) otherwise, so the script
  runs identically on Windows.

Usage:
    python scripts/parse_universe_pdfs.py
    python scripts/parse_universe_pdfs.py --raw-dir path --out path
"""
import argparse
import csv
import re
import subprocess
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

SUFFIX_MARKERS = ("revise", "v2", "v3", "merger", "psh", "update")
ROW_RE = re.compile(r"(?:^|\s)(\d{1,3})\*?\s+\*?([A-Z][A-Z0-9&.\-]{0,7})(?=\s|$)")
SET100_HEADER = re.compile(r"^\s*SET100\b", re.MULTILINE)
XLS_SYMBOL = re.compile(r"^[A-Z][A-Z0-9&.\-]{0,7}$")

# Defect in several 2005-2006 SET files: TRUE's symbol cell holds the
# number 1 instead of "TRUE". Rescue by company-name evidence on the
# same row — auditable and applies wherever the defect recurs.
NAME_RESCUES = {
    "TRUE CORPORATION": "TRUE",
}

# Documented repairs for rows whose number is unrecoverable from the
# PDF text layer. Evidence noted; the alphabetical validator still
# checks the placement afterwards.
PDF_REPAIRS = {
    # HEMRAJ removed (free float < 20%), SAMART is its replacement; the
    # row number 70 is missing from the text layer of the update file.
    ("SET50_100_H1_2015-Update-HEMRAJ-Out.pdf", 70): "SAMART",
}


def parse_period(name: str):
    m = (re.search(r"[Hh]([12])[-_]?((?:19|20)\d{2})", name)
         or re.search(r"([12])[Hh][-_]?((?:19|20)\d{2})", name))
    if not m:
        return None
    half, year = int(m.group(1)), int(m.group(2))
    if half == 1:
        return year, half, f"{year}-01-01", f"{year}-06-30"
    return year, half, f"{year}-07-01", f"{year}-12-31"


def choose_file(candidates: list[Path]) -> Path:
    """Prefer the revised/updated version of a period's list."""
    def rank(p: Path):
        n = p.name.lower()
        return (any(k in n for k in SUFFIX_MARKERS), n)
    return sorted(candidates, key=rank)[-1]


def pdf_text(path: Path, layout: bool = True) -> str:
    cmd = ["pdftotext"] + (["-layout"] if layout else []) + [str(path), "-"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return out.stdout
    except FileNotFoundError:
        # no poppler on this machine (typical on Windows) -> pure Python
        if layout:
            return _plumber_layout_text(path)
        import pdfplumber
        with pdfplumber.open(str(path)) as pdf:
            return "\n".join((p.extract_text() or "") for p in pdf.pages)


def _plumber_layout_text(path: Path) -> str:
    """Rebuild layout-style lines from word coordinates: bucket words
    into 3pt vertical bands (one visual line), sort by x. Handles the
    two-column SET layouts that pdfplumber's own layout mode garbles."""
    import pdfplumber
    lines = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            bands: dict[int, list] = {}
            for w in page.extract_words(x_tolerance=1):
                bands.setdefault(round(w["top"] / 3), []).append(w)
            for key in sorted(bands):
                ws = sorted(bands[key], key=lambda w: w["x0"])
                lines.append(" ".join(w["text"] for w in ws))
    return "\n".join(lines)


def _set100_section(text: str, fname: str) -> str:
    m = SET100_HEADER.search(text)
    if m is None:
        raise ValueError(f"{fname}: SET100 section header not found")
    # No truncation at "Reserve list": in the 2015 layout the reserve
    # column sits BESIDE the main list, so cutting there loses main rows.
    # Reserve numbers (1..5) collide with already-seen main rows and are
    # ignored by first-occurrence-wins; the break-at-100 plus the
    # alphabetical validator handle the below-the-list case.
    return text[m.start():]


def extract_pdf(path: Path, fname: str) -> list[str]:
    """Try every line-start SET100 header; return the first candidate
    section that parses into a valid list. Some files mention SET100 at
    line start inside the SET50 pages, so the first match is not always
    the real section."""
    layout_text = pdf_text(path, layout=True)
    matches = list(SET100_HEADER.finditer(layout_text))
    if not matches:
        raise ValueError(f"{fname}: SET100 section header not found")
    errors = []
    for m in matches:
        try:
            return _extract_pdf_section(layout_text[m.start():], path, fname)
        except ValueError as exc:
            errors.append(str(exc))
    raise ValueError(f"{fname}: no SET100 header candidate parsed cleanly; "
                     f"last error: {errors[-1]}")


def _extract_pdf_section(section: str, path: Path, fname: str) -> list[str]:

    rows: dict[int, str] = {}
    conflicts = []
    for line in section.splitlines():
        for num_s, sym in ROW_RE.findall(line):
            num = int(num_s)
            if not 1 <= num <= 100:
                continue
            if num in rows and rows[num] != sym:
                conflicts.append((num, rows[num], sym))
            rows.setdefault(num, sym)
        if len(rows) == 100:
            break  # SET100 complete; later numbered lists must not bleed in

    missing = [n for n in range(1, 101) if n not in rows]
    recovered = False
    if missing:
        # -layout occasionally garbles lines; recover from raw reading-order
        # text using the list's own alphabetical ordering between the
        # nearest known neighbours.
        raw = pdf_text(path, layout=False)
        used = set(rows.values())
        for n in sorted(missing):
            lower = max((v for k, v in rows.items() if k < n), default="")
            upper = min((v for k, v in rows.items() if k > n), default="ZZZZZZZZZ")
            candidates = []
            for m in re.finditer(
                rf"^\s*{n}\*?(?:\s*\n+\s*|\s+)\*?([A-Z][A-Z0-9&.\-]{{0,7}})(?=\s|$)",
                raw, re.MULTILINE,
            ):
                sym = m.group(1)
                if sym not in used and lower < sym < upper:
                    candidates.append(sym)
            if len(set(candidates)) == 1:
                rows[n] = candidates[0]
                used.add(candidates[0])
                missing.remove(n)
                recovered = True

    for (f, n), fixed in PDF_REPAIRS.items():
        if f == fname and n in missing:
            rows[n] = fixed
            missing.remove(n)
            print(f"  repaired {fname} row {n} -> {fixed} (see PDF_REPAIRS)")

    if missing:
        raise ValueError(f"{fname}: missing SET100 row numbers {missing}")

    symbols = [rows[n] for n in range(1, 101)]
    breaks = [
        (i + 1, symbols[i], symbols[i + 1])
        for i in range(99) if symbols[i] >= symbols[i + 1]
    ]
    if breaks and (conflicts or recovered):
        raise ValueError(
            f"{fname}: non-alphabetical with conflicts {conflicts[:3]} "
            f"/ raw recovery used — inspect manually"
        )
    if breaks:
        # clean, conflict-free extraction that simply isn't alphabetical:
        # the sector-ordered (pre-2016) layout. Completeness already holds.
        print(f"  note: {fname} is sector-ordered (pre-2016 layout)")
    return symbols


def extract_xls(path: Path, fname: str) -> list[str]:
    import xlrd

    wb = xlrd.open_workbook(str(path))

    def score(sheet_name: str) -> int:
        n = sheet_name.lower().replace(" ", "").replace("-", "_")
        if "set100" not in n or "sum" in n:
            return -1
        return 2 if "en" in n else 1  # prefer the English sheet

    sheets = sorted(wb.sheets(), key=lambda s: score(s.name))
    best = sheets[-1]
    if score(best.name) < 0:
        raise ValueError(f"{fname}: no SET100 sheet found; sheets={wb.sheet_names()}")

    def row_parts(r):
        """(row_number_or_None, symbol_or_None, has_company_name) for one row."""
        v0 = best.cell_value(r, 0)
        num = None
        if isinstance(v0, (int, float)) and float(v0).is_integer():
            num = int(v0)
        elif isinstance(v0, str) and v0.strip().rstrip(".").isdigit():
            num = int(v0.strip().rstrip("."))

        sym, has_name = None, False
        for c in range(1, best.ncols):
            val = best.cell_value(r, c)
            if not isinstance(val, str):
                continue
            v = re.sub(r"^\*+|[\s*]+$", "", val.strip())  # 'IVL   *' / 'BTS*' -> footnote marks off
            if sym is None and XLS_SYMBOL.match(v):
                sym = v  # first symbol-looking cell = the symbol column
            if len(v) > 15 and " " in v:
                has_name = True  # long multi-word string = a company name
        if sym is None and has_name:
            joined = " ".join(
                str(best.cell_value(r, c)) for c in range(best.ncols)
            ).upper()
            for key, fixed in NAME_RESCUES.items():
                if key in joined:
                    sym = fixed
                    print(f"  rescued {fname} -> {fixed} (company-name match)")
                    break
        return num, sym, has_name

    stop_re = re.compile(r"rep[a-z]*ment\s+list|reserve\s+list|สำรอง", re.IGNORECASE)  # tolerant: SET's own "Repalcement" typo; Thai-era sheets say รายชื่อหลักทรัพย์สำรอง

    def is_separator(r, sym) -> bool:
        """A reserve/replacement SECTION HEADER: stop text and no symbol.
        (Rows that merely annotate a constituent still carry a symbol.)"""
        return sym is None and any(
            isinstance(best.cell_value(r, c), str)
            and stop_re.search(best.cell_value(r, c))
            for c in range(best.ncols)
        )

    # pass 1: numbered layout (2005, 2011+) — validate rows 1..100 exactly
    rows: dict[int, str] = {}
    conflicts = []
    for r in range(best.nrows):
        num, sym, _ = row_parts(r)
        if is_separator(r, sym):
            break  # replacement lists restart numbering at 1 — must not bleed in
        if num is None or not 1 <= num <= 100 or sym is None:
            continue
        if num in rows and rows[num] != sym:
            conflicts.append((num, rows[num], sym))
        rows.setdefault(num, sym)

    if len(rows) == 100 and not conflicts:
        return [rows[n] for n in range(1, 101)]
    if conflicts:
        raise ValueError(f"{fname}: [{best.name}] conflicting rows {conflicts[:5]}")

    # pass 2: unnumbered layout (2006-2007) — one symbol per company row,
    # validated by the count: exactly 100 distinct symbols
    ordered: list[str] = []
    for r in range(best.nrows):
        _, sym, has_name = row_parts(r)
        if is_separator(r, sym):
            break
        if sym is not None and has_name:
            joined = " ".join(
                str(best.cell_value(r, c)) for c in range(best.ncols)
            )
            if re.search(r"delist", joined, re.IGNORECASE):
                # e.g. 2008H1 lists ATC/RRC with "(Delist 28/12/2007)"
                # alongside their merger successor PTTAR — names that had
                # already left are excluded, and loudly.
                print(f"  excluded {sym} ({fname}): note mentions delisting")
                continue
            if sym not in ordered:
                ordered.append(sym)
    if len(ordered) == 100:
        return ordered

    raise ValueError(
        f"{fname}: [{best.name}] numbered pass found {len(rows)} rows, "
        f"unnumbered pass found {len(ordered)} symbols — expected 100"
    )


def extract_any(path: Path) -> list[str]:
    if path.suffix.lower() == ".pdf":
        return extract_pdf(path, path.name)
    if path.suffix.lower() in (".xls", ".xlsx"):
        return extract_xls(path, path.name)
    raise ValueError(f"{path.name}: unsupported file type")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", default=REPO_ROOT / "reference" / "raw", type=Path)
    ap.add_argument("--out", default=REPO_ROOT / "reference" / "universe_set100.csv", type=Path)
    args = ap.parse_args()

    by_period = defaultdict(list)
    for f in sorted(list(args.raw_dir.glob("*.pdf"))
                    + list(args.raw_dir.glob("*.xls"))
                    + list(args.raw_dir.glob("*.xlsx"))):
        period = parse_period(f.name)
        if period is None:
            print(f"SKIP (no H1/H2-year in name): {f.name}")
            continue
        by_period[period].append(f)

    # carry-forward: one legacy file (SET50_100_H2_2018.pdf, page 2)
    # is unreadable without poppler. If parsing fails and the existing
    # CSV already holds that period, reuse the committed transcription
    # rather than aborting — loudly.
    existing: dict[tuple, list] = {}
    if args.out.exists():
        import csv as _csv
        with open(args.out, newline="") as f:
            for row in _csv.DictReader(f):
                existing.setdefault(
                    (row["period_start"], row["period_end"]), []
                ).append((row["symbol"], row["source"]))

    records = []
    for (year, half, start, end), files in sorted(by_period.items()):
        chosen = choose_file(files)
        try:
            symbols = extract_any(chosen)
            for sym in sorted(symbols):
                records.append(("SET100", start, end, sym, chosen.name))
        except ValueError as exc:
            prior = existing.get((start, end))
            if prior and len(prior) == 100:
                for sym, src in sorted(prior):
                    records.append(("SET100", start, end, sym, src))
                print(f"{year}H{half}: PARSER FAILED ({str(exc)[:60]}...) — "
                      f"reused committed transcription ({prior[0][1]})")
                continue
            raise
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
