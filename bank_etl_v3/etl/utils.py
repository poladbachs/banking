import os, re, hashlib, pandas as pd, numpy as np

MASTER_COLS = ["Bank","Period","Indicator table","Element","Sub-element","AZN","FS Line","Item","Currency",
               "Amount vs Share","Total","31-60 days","61-90 days","91+ days",
               "31-60 days_share%inLP","61-90 days_share%inLP","91+ days_share%inLP"]

def ensure_dir(p): os.makedirs(p, exist_ok=True)

def file_md5(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""): h.update(chunk)
    return h.hexdigest()

def read_csv_utf8(path): return pd.read_csv(path, dtype=str, encoding="utf-8").fillna("")

def canonical_bank_from_filename(filename: str, banks_df: pd.DataFrame) -> str:
    fn = filename.lower()
    for _, r in banks_df.iterrows():
        alias = str(r["bank_alias"]).strip().lower()
        if alias and alias in fn:
            return r["bank"]
    return ""

def parse_period_from_filename(filename: str) -> str:
    name = os.path.basename(filename)
    s = name.replace("_"," ").replace("-"," ").lower()
    m = re.search(r'(20\d{2})\s*q\s*([1-4])', s, flags=re.I)
    if m: return f"{m.group(1)} Q{m.group(2)}"
    m = re.search(r'q\s*([1-4])\s*(20\d{2})', s, flags=re.I)
    if m: return f"{m.group(2)} Q{m.group(1)}"
    y = re.search(r'(20\d{2})', s)
    return f"{y.group(1)}" if y else ""

def force_master_columns(df: pd.DataFrame) -> pd.DataFrame:
    for c in MASTER_COLS:
        if c not in df.columns: df[c] = np.nan
    df = df[MASTER_COLS].copy()
    # numeric cleaning
    num_cols = ["AZN","Total","31-60 days","61-90 days","91+ days",
                "31-60 days_share%inLP","61-90 days_share%inLP","91+ days_share%inLP"]
    for c in num_cols:
        df[c] = pd.to_numeric(
            df[c].astype(str)
                .str.replace("\u00a0","", regex=False)  # NBSP
                .str.replace(" ","", regex=False)       # spaces as thousands
                .str.replace(".","", regex=False)       # dots as thousands
                .str.replace(",",".", regex=False),     # comma decimals
            errors="coerce"
        )
    # tidy text
    for c in ["Bank","Period","Indicator table","Element","Sub-element","FS Line","Item","Currency","Amount vs Share"]:
        df[c] = df[c].astype(str).str.strip()
    return df

def dedup_master(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    for c in ["AZN","Total","31-60 days","61-90 days","91+ days",
              "31-60 days_share%inLP","61-90 days_share%inLP","91+ days_share%inLP"]:
        d[c] = d[c].round(6)
    d = d.drop_duplicates(subset=MASTER_COLS)
    return d

def apply_bank_period_fallback(df: pd.DataFrame, filename: str, banks_df: pd.DataFrame) -> pd.DataFrame:
    fb_bank = canonical_bank_from_filename(filename, banks_df)
    fb_period = parse_period_from_filename(filename)
    if "Bank" not in df.columns: df["Bank"] = fb_bank
    df["Bank"] = df["Bank"].replace("", pd.NA).fillna(fb_bank)
    if "Period" not in df.columns: df["Period"] = fb_period
    df["Period"] = df["Period"].replace("", pd.NA).fillna(fb_period)
    # normalize formatting
    df["Period"] = df["Period"].astype(str).str.replace("_"," ").str.replace("-"," ")
    df["Period"] = df["Period"].str.replace("Q"," Q", case=False, regex=False).str.replace("  "," ")
    return df
