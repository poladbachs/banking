import os
import re
import argparse
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
from rapidfuzz import process as rf_process, fuzz as rf_fuzz

# ----------------- Config -----------------
MASTER_COLS = [
    "Bank","Period","Indicator table","Element","Sub-element","AZN","FS Line","Item","Currency",
    "Amount vs Share","Total","31-60 days","61-90 days","91+ days",
    "31-60 days_share%inLP","61-90 days_share%inLP","91+ days_share%inLP"
]

FILENAME_BALANCE_RE = re.compile(r"(balance[_\s]?sheet|balance|financial[_\s]?position)", re.IGNORECASE)
SHEET_NAME_HINTS = ("maliyyə vəziyyəti", "financial position", "balance")

PREFER_HDR = ("hesabat", "cari", "current")
AVOID_HDR  = ("ötən", "oten", "keçən", "kecen", "previous", "sonu", "last", "cəmi", "cemi", "yekun", "total")

# Top-level buckets to avoid for long descriptive labels
TOP_LEVEL_CODES = {"1","2","3","4"}

# ----------------- IO helpers -----------------
def md5sum(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)

# ----------------- Normalization helpers -----------------
_AZ_MAP = str.maketrans({
    "ə":"e","Ə":"e","ı":"i","İ":"i","ş":"s","Ş":"s","ö":"o","Ö":"o",
    "ü":"u","Ü":"u","ğ":"g","Ğ":"g","ç":"c","Ç":"c","İ":"i"
})

def norm_text(s: str) -> str:
    s = str(s or "")
    s = s.translate(_AZ_MAP)
    s = s.lower()
    s = re.sub(r"[\(\)\[\]\{\}:;,/\\\-–—]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

# ----------------- Master shaping -----------------
def force_master_columns(df: pd.DataFrame) -> pd.DataFrame:
    for c in MASTER_COLS:
        if c not in df.columns:
            df[c] = np.nan
    df = df[MASTER_COLS].copy()
    for c in ["AZN","Total","31-60 days","61-90 days","91+ days",
              "31-60 days_share%inLP","61-90 days_share%inLP","91+ days_share%inLP"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in ["Bank","Period","Indicator table","Element","Sub-element","FS Line","Item","Currency","Amount vs Share"]:
        df[c] = df[c].astype(str).str.strip()
        df.loc[df[c].isin(["", "nan", "None"]), c] = np.nan
    return df

def dedup_master_keep_last_per_element(master: pd.DataFrame) -> pd.DataFrame:
    # one row per Bank+Period+Element, keep the last (usually the detailed/true line)
    master = master.sort_values(["Bank","Period","Element","AZN"])
    return master.drop_duplicates(["Bank","Period","Element"], keep="last")

# ----------------- Element sorting (natural) -----------------
def _pad(code: str, w: int = 6) -> str:
    parts = str(code).split(".")
    return ".".join(f"{int(p):0{w}d}" if p.isdigit() else p for p in parts)

def natural_sort(df: pd.DataFrame) -> pd.DataFrame:
    k = "__k__"
    df[k] = df["Element"].astype(str).map(_pad)
    df = df.sort_values(k).drop(columns=[k])
    return df

# ----------------- Numeric parsing (PDF-proof) -----------------
_num_re_plain = re.compile(r"^[+-]?\d+$")
_num_re_mixed = re.compile(r"^[+-]?[\d.,\s\u00a0\u202f\u2009\u2007\u2060\(\)−–—]+$")  # include unicode spaces & dashes

def normalize_amount(x):
    """
    Robust:
      - remove all odd spaces: NBSP(\u00a0), narrow NBSP(\u202f), thin(\u2009), figure(\u2007), etc.
      - unicode minus (−), en-dash (–), em-dash (—)
      - parentheses negatives: (42 653) -> -42653
      - decide decimal sep by the RIGHT-MOST of {'.', ','}; other is thousands
    """
    if x is None:
        return np.nan
    if isinstance(x, (int, float, np.integer, np.floating)):
        return float(x) if pd.notna(x) else np.nan

    s = str(x).strip()
    if s == "" or s == "-":
        return np.nan

    # unify minus
    s = s.replace("−", "-").replace("–", "-").replace("—", "-")
    # parentheses negatives
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]

    # remove all weird spaces
    s = re.sub(r"[\s\u00a0\u202f\u2009\u2007\u2060]", "", s)

    if _num_re_plain.fullmatch(s):
        try:
            return float(s)
        except Exception:
            return np.nan
    if not _num_re_mixed.fullmatch(s):
        return pd.to_numeric(s, errors="coerce")

    last_dot   = s.rfind(".")
    last_comma = s.rfind(",")
    if last_dot > last_comma:
        dec, thou = ".", ","
    else:
        dec, thou = ",", "."

    s = s.replace(thou, "")
    s = s.replace(dec, ".")
    try:
        return float(s)
    except Exception:
        return pd.to_numeric(s, errors="coerce")

# ----------------- File / sheet detection -----------------
def is_balance_candidate(filename: str) -> bool:
    return bool(FILENAME_BALANCE_RE.search(Path(filename).stem))

def read_balance_sheet(file_path: str) -> pd.DataFrame | None:
    try:
        xls = pd.ExcelFile(file_path, engine="openpyxl")
    except Exception as e:
        print(f"[WARN] Cannot open {file_path}: {e}")
        return None

    for s in xls.sheet_names:
        if any(h in s.lower() for h in SHEET_NAME_HINTS):
            try:
                return xls.parse(s, header=0)
            except Exception:
                pass

    for s in xls.sheet_names:
        try:
            df0 = xls.parse(s, header=None, nrows=60)
            if df0.astype(str).apply(lambda col: col.str.contains("Maliyyə vəziyyəti", case=False, na=False)).any().any():
                return xls.parse(s, header=0)
        except Exception:
            continue

    try:
        return xls.parse(xls.sheet_names[0], header=0)
    except Exception:
        return None

def promote_headers_if_needed(df: pd.DataFrame) -> pd.DataFrame:
    if df.columns.astype(str).str.contains("Unnamed").any() and df.iloc[0].notna().sum() >= 3:
        new_cols = df.iloc[0].astype(str).tolist()
        df = df.iloc[1:].copy()
        df.columns = new_cols
    return df

# ----------------- Pick the "current/reporting" column -----------------
def find_reporting_col(df: pd.DataFrame) -> str | None:
    cols = [c for c in df.columns if isinstance(c, str)]
    peek = min(120, len(df))

    def weight(name: str) -> int:
        t = norm_text(name)
        w = 0
        if any(k in t for k in PREFER_HDR): w += 3000
        if any(k in t for k in AVOID_HDR):  w -= 2500
        return w

    best = None
    best_score = -10**9
    for j, c in enumerate(cols):
        if j == 0:
            continue
        series = df[c].head(peek)
        numeric_density = int(series.apply(lambda v: pd.notna(normalize_amount(v))).sum())
        sc = weight(c) + numeric_density
        if sc > best_score:
            best_score, best = sc, c

    if best is None:
        for j, c in enumerate(cols):
            if j == 0: continue
            series = df[c].head(peek)
            if int(series.apply(lambda v: pd.notna(normalize_amount(v))).sum()) >= max(3, peek//4):
                return c
    return best

# ----------------- Detect label vs code columns -----------------
_CODE_RE = re.compile(r"^\d+(?:\.\d+)*$")

def detect_label_and_code_cols(df: pd.DataFrame):
    n = min(4, df.shape[1])
    frac_code, textiness = [], []
    sample_n = min(150, len(df))
    for i in range(n):
        col = df.columns[i]
        ser = df[col].head(sample_n).astype(str)
        m_code = ser.apply(lambda s: bool(_CODE_RE.match(s.strip()))).mean()
        m_text = ser.apply(lambda s: bool(re.search(r"[A-Za-z\u0400-\u04FF]", s))).mean()
        frac_code.append((i, m_code))
        textiness.append((i, m_text))
    code_col_idx, code_score = max(frac_code, key=lambda t: t[1])
    label_col_idx, label_score = max([t for t in textiness if t[0] != code_col_idx] or [(0,0.0)], key=lambda t: t[1])
    code_col = df.columns[code_col_idx] if code_score >= 0.25 else None
    label_col = df.columns[label_col_idx] if label_score >= 0.25 else df.columns[0]
    return label_col, code_col

# ----------------- Special label rules (tight) -----------------
SPECIAL_RULES = [
    # loan loss provision (avoid 'umumi')
    (re.compile(r"\b(mumkun|moemkun|mumkun|mümkün).*(ehtiyat)\b|\b(meqsedli|məqsədli)\s+ehtiyat\b"), "1.5.5"),
    # net loans to customers
    (re.compile(r"\b(xalis)\b.*\b(kredit|kred|musteri)\b"), "1.5.6"),
]

# ----------------- Core extraction (LABEL-FIRST, smarter) -----------------
def extract_balance_sheet_from_file(file_path: str, items_map: pd.DataFrame) -> pd.DataFrame:
    if not is_balance_candidate(file_path):
        return pd.DataFrame()

    df = read_balance_sheet(file_path)
    if df is None or df.empty:
        return pd.DataFrame()

    df = promote_headers_if_needed(df)
    df.columns = [str(c).strip() for c in df.columns]
    if df.empty:
        return pd.DataFrame()

    amount_col = find_reporting_col(df)
    if amount_col is None:
        return pd.DataFrame()

    label_col, code_col = detect_label_and_code_cols(df)

    # normalized items map
    items_map = items_map.copy()
    items_map["norm_label"] = items_map["az_label"].map(norm_text)
    norm_to_row = {row["norm_label"]: row for _, row in items_map.iterrows()}
    norm_labels = list(norm_to_row.keys())
    codes_set = set(items_map["code"].astype(str).tolist())
    items_by_code = items_map.set_index("code")

    out_rows = []
    for _, row in df.iterrows():
        raw_label = str(row.get(label_col, "")).strip().rstrip(":")
        code_hint = str(row.get(code_col, "")).strip() if code_col else ""
        amt = normalize_amount(row.get(amount_col, np.nan))
        if pd.isna(amt):
            continue

        nz = norm_text(raw_label)

        # ---- 1) special rules
        matched_special = False
        for rx, code_val in SPECIAL_RULES:
            if rx.search(nz) and "umumi" not in nz:  # don't collide with equity reserves
                grp = items_by_code.loc[code_val, "master_group"]
                out_rows.append({"Element": code_val, "Sub-element": grp, "AZN": amt})
                matched_special = True
                break
        if matched_special:
            continue

        # ---- 2) fuzzy by label (avoid mapping long labels to top-level codes)
        chosen = None
        if nz:
            cands = rf_process.extract(nz, norm_labels, scorer=rf_fuzz.token_set_ratio, limit=5)
            for cand in cands:
                rec = norm_to_row[cand[0]]
                cand_code = str(rec["code"])
                if cand_code in TOP_LEVEL_CODES and len(nz) > 12:
                    continue  # skip too-broad match
                chosen = cand_code
                grp = rec["master_group"]
                out_rows.append({"Element": chosen, "Sub-element": grp, "AZN": amt})
                break
            if chosen:
                continue

        # ---- 3) fallback to code cell if valid
        if code_hint and _CODE_RE.match(code_hint) and code_hint in codes_set:
            grp = items_by_code.loc[code_hint, "master_group"]
            out_rows.append({"Element": code_hint, "Sub-element": grp, "AZN": amt})
            continue

        # ---- 4) last resort: skip
        continue

    if not out_rows:
        return pd.DataFrame()

    out = pd.DataFrame(out_rows)
    out = natural_sort(out).reset_index(drop=True)

    # fill master columns
    out["Indicator table"] = "Balance Sheet"
    out["FS Line"] = np.nan
    out["Item"] = np.nan
    out["Currency"] = np.nan
    out["Amount vs Share"] = np.nan
    out["Total"] = np.nan
    out["31-60 days"] = np.nan
    out["61-90 days"] = np.nan
    out["91+ days"] = np.nan
    out["31-60 days_share%inLP"] = np.nan
    out["61-90 days_share%inLP"] = np.nan
    out["91+ days_share%inLP"] = np.nan
    return out

# ----------------- CSV formatting (no scientific notation) -----------------
_NUM_COLS = ["AZN","Total","31-60 days","61-90 days","91+ days",
             "31-60 days_share%inLP","61-90 days_share%inLP","91+ days_share%inLP"]

def _fmt_num(x):
    if pd.isna(x): return ""
    try: x = float(x)
    except Exception: return ""
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    s = f"{x:.10f}".rstrip("0").rstrip(".")
    return s

def format_numeric_for_csv(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in _NUM_COLS:
        if c in out.columns:
            out[c] = out[c].apply(_fmt_num)
    return out

# ----------------- Runner -----------------
def run():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True, help="processed_data/<bank>/<period>")
    ap.add_argument("--out", required=True, help="output folder")
    ap.add_argument("--config", required=True, help="config folder with items_map_balance.csv")
    ap.add_argument("--master", required=True, help="output csv filename, e.g. master4.csv")
    args = ap.parse_args()

    raw_root = Path(args.raw)
    out_dir = Path(args.out)
    cfg_dir = Path(args.config)
    master_csv = out_dir / args.master

    items_map_path = cfg_dir / "items_map_balance.csv"
    if not items_map_path.exists():
        raise FileNotFoundError(f"Mapping not found: {items_map_path}")
    items_map = pd.read_csv(items_map_path, dtype=str).fillna("")

    ensure_dir(str(out_dir))

    processed_log = []
    master_parts = []

    for bank_dir in [p for p in raw_root.iterdir() if p.is_dir()]:
        for period_dir in [p for p in bank_dir.iterdir() if p.is_dir()]:
            for fp in period_dir.rglob("*.xls*"):
                if not is_balance_candidate(fp.name):
                    continue
                df = extract_balance_sheet_from_file(str(fp), items_map)
                if df is None or df.empty:
                    continue

                df.insert(0, "Period", period_dir.name)
                df.insert(0, "Bank", bank_dir.name)
                df = force_master_columns(df)
                df = natural_sort(df)

                master_parts.append(df)
                processed_log.append({"report_type": "balance_sheet", "file": str(fp), "md5": md5sum(str(fp))})

    if master_parts:
        master = pd.concat(master_parts, ignore_index=True)

        # natural sort + keep one value per Bank+Period+Element
        master["__k__"] = master["Element"].astype(str).map(_pad)
        master = master.sort_values(["Bank","Period","__k__"]).drop(columns="__k__")
        master = dedup_master_keep_last_per_element(master)

        master_out = format_numeric_for_csv(master)
        master_out.to_csv(master_csv, index=False, encoding="utf-8-sig")

    pd.DataFrame(processed_log).to_csv(out_dir / "processed_log.csv", index=False, encoding="utf-8-sig")

if __name__ == "__main__":
    run()