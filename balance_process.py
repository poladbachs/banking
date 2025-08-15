import os
import re
from pathlib import Path
import pandas as pd

# ---------------- CONFIG ----------------
ROOT = Path("processed_data")          # your root folder
INCLUDE_EXT = {".xlsx", ".xls"}       # Excel types
# Match report type in path/filename (exclude balance of payments)
REPORT_RX = re.compile(r"(financial[_\s-]*position|balance(?![_\s-]*of[_\s-]*payments))", re.IGNORECASE)

# Period patterns you said you have
PERIOD_Q_RX   = re.compile(r"\b(20\d{2})[ _\-\.]?Q([1-4])\b", re.IGNORECASE)   # 2024_Q1
PERIOD_12M_RX = re.compile(r"\b(20\d{2})[ _\-\.]?12M\b", re.IGNORECASE)        # 2020_12m → Q4

TOTAL_RX = re.compile(r"\b(total|subtotal|cəm|ümumi|итог|всего)\b", re.IGNORECASE)

# ---------------- HELPERS ----------------
def is_balance_file(path: Path) -> bool:
    return path.suffix.lower() in INCLUDE_EXT and bool(REPORT_RX.search(str(path)))

def parse_bank(path: Path) -> str:
    try:
        parts = path.relative_to(ROOT).parts[:-1]
    except ValueError:
        parts = path.parent.parts
    return parts[0] if parts else "UNKNOWN_BANK"

def parse_period(path: Path) -> str:
    s = str(path)
    m = PERIOD_Q_RX.search(s)
    if m:
        return f"{m.group(1)}_Q{m.group(2)}"
    m = PERIOD_12M_RX.search(s)
    if m:
        return f"{m.group(1)}_Q4"
    return "UNKNOWN_PERIOD"

def col_letter(idx: int) -> str:
    # 0 -> A, 1 -> B, ...
    s = ""
    idx += 1
    while idx:
        idx, rem = divmod(idx - 1, 26)
        s = chr(65 + rem) + s
    return s

def find_header_row(df: pd.DataFrame) -> int:
    # First row with >=2 non-nulls; tweak if needed
    for i, row in df.iterrows():
        if row.count() >= 2:
            return i
    return 0

def first_text_cell_index(series: pd.Series) -> int | None:
    for j, v in series.items():
        if pd.isna(v):
            continue
        s = str(v).strip()
        if not s:
            continue
        # treat cells with any letter as text label (metric)
        if re.search(r"[A-Za-zÀ-žƏəİıÖöÜüĞğŞş]", s):
            return j
    return None

def tidy_sheet_cellwise(raw: pd.DataFrame) -> pd.DataFrame:
    if raw is None or raw.empty:
        return pd.DataFrame()

    # Drop fully empty rows/cols
    df = raw.dropna(how="all").dropna(axis=1, how="all")
    if df.empty:
        return pd.DataFrame()

    # Detect header row
    h = find_header_row(df)

    # Build descriptors from the header row (fallback to column letters)
    header_vals = df.iloc[h].tolist()
    descriptors = []
    for c_idx, v in enumerate(header_vals):
        label = str(v).strip() if pd.notna(v) and str(v).strip() else col_letter(c_idx)
        descriptors.append(label)

    # Data starts after header
    data = df.iloc[h+1:].reset_index(drop=True)
    if data.empty:
        return pd.DataFrame()

    records = []
    for _, row in data.iterrows():
        # find metric cell index (first non-empty text cell anywhere in the row)
        metric_idx = first_text_cell_index(row)
        if metric_idx is None:
            continue
        metric_text = str(row.iloc[metric_idx]).strip()
        if not metric_text or TOTAL_RX.search(metric_text):
            continue

        # emit one record for every other non-empty cell in the row
        for c_idx, cell in enumerate(row):
            if c_idx == metric_idx:
                continue
            if pd.isna(cell):
                continue
            val = str(cell).strip()
            if not val:
                continue
            descriptor = descriptors[c_idx] if c_idx < len(descriptors) else col_letter(c_idx)
            # avoid meaningless numeric-only descriptors like "1" if header was bad
            if not descriptor or descriptor.isdigit():
                descriptor = col_letter(c_idx)
            records.append({
                "Metric": metric_text,
                "Descriptor": descriptor,
                "Value": val
            })

    if not records:
        return pd.DataFrame()
    return pd.DataFrame.from_records(records)

# ---------------- MAIN PROCESS ----------------
def process_file(xl_path: Path):
    bank   = parse_bank(xl_path)
    period = parse_period(xl_path)

    try:
        book = pd.read_excel(xl_path, sheet_name=None, header=None, engine="openpyxl")
    except Exception as e:
        print(f"[SKIP] {xl_path} -> read error: {e}")
        return

    frames = []
    for sheet_name, raw in book.items():
        try:
            tidy = tidy_sheet_cellwise(raw)
            if tidy.empty:
                continue
            tidy["Bank"]       = bank
            tidy["Period"]     = period
            tidy["ReportType"] = "BalanceSheet"
            tidy["SourceFile"] = xl_path.name
            tidy["Sheet"]      = str(sheet_name)
            frames.append(tidy)
        except Exception as e:
            print(f"[WARN] {xl_path}::{sheet_name} -> tidy error: {e}")

    if not frames:
        print(f"[INFO] {xl_path} -> no usable rows")
        return

    out_df = pd.concat(frames, ignore_index=True)

    # Write CSV next to the source file
    out_path = xl_path.with_name(xl_path.stem + "__balance_clean.csv")
    out_df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"✅ {xl_path} → {out_path} ({len(out_df):,} rows)")

def main():
    count = 0
    for p in ROOT.rglob("*"):
        if p.is_file() and is_balance_file(p):
            process_file(p)
            count += 1
    if count == 0:
        print("No Balance Sheet files found under", ROOT)

if __name__ == "__main__":
    main()
