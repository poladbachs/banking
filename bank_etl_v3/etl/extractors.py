import os, yaml, pandas as pd, numpy as np
from rapidfuzz import process, fuzz
from .utils import force_master_columns, apply_bank_period_fallback

def read_sheet(xls, report_type: str, rules_path: str):
    with open(rules_path, "r", encoding="utf-8") as f:
        rules = yaml.safe_load(f) or {}
    kws = [k.lower() for k in (rules.get(report_type, {}).get("sheet_keywords", []) or [])]
    pick = xls.sheet_names[0]
    for s in xls.sheet_names:
        if any(k in s.lower() for k in kws): pick = s; break
    df = xls.parse(pick, header=0)
    return df

def promote_headers_if_needed(df: pd.DataFrame) -> pd.DataFrame:
    if df.columns.astype(str).str.contains("Unnamed").any() and df.iloc[0].notna().sum() >= 3:
        new_cols = df.iloc[0].astype(str).tolist()
        df = df.iloc[1:].copy()
        df.columns = new_cols
    return df

# ---------- Balance Sheet (content-driven) ----------
def extract_balance_sheet(xls, dict_df, items_map_df, banks_df, filename):
    df = read_sheet(xls, "balance_sheet", xls.rules_path)
    df = promote_headers_if_needed(df)
    df.columns = [str(c).strip() for c in df.columns]

    prefer_kw = ("hesabat","cari","current","reporting")
    avoid_kw  = ("ötən","keçən","previous","year end","ilin sonu","prior")
    best_col, best_score = None, -1e9
    for c in df.columns:
        h = c.lower()
        nonnull = pd.to_numeric(df[c], errors="coerce").notna().sum()
        if nonnull == 0: continue
        score = sum(k in h for k in prefer_kw)*100 - sum(k in h for k in avoid_kw)*100 + nonnull/1000
        if score > best_score: best_score, best_col = score, c
    if best_col is None:
        dens = {c: pd.to_numeric(df[c], errors="coerce").notna().sum() for c in df.columns}
        best_col = max(dens, key=dens.get)

    labels = items_map_df[["az_label","code","master_group"]].dropna()
    label_list = labels["az_label"].astype(str).tolist()

    def code_to_fs(code: str) -> str:
        s = str(code)
        if s.startswith("1"): return "Assets"
        if s.startswith("2"): return "Liabilities"
        if s.startswith("3"): return "Equity"
        if s.startswith("4"): return "Liabilities+Equity"
        return ""

    rows = []
    for i in range(len(df)):
        r = df.iloc[i]
        blob = " ".join([str(v) for v in r.tolist() if isinstance(v, str)]).lower()
        if not blob.strip():
            continue
        match = process.extractOne(blob, label_list, scorer=fuzz.token_set_ratio, score_cutoff=86)
        if not match:
            continue
        az_label = match[0]
        rec = labels.loc[labels["az_label"] == az_label].iloc[0]
        code = rec["code"]
        group = rec["master_group"]   # ASSETS, LIABILITIES, EQUITY...
        amt = pd.to_numeric(r[best_col], errors="coerce")
        rows.append({
            "Bank": r.get("Bank", np.nan),
            "Period": r.get("Period", np.nan),
            "Indicator table": "Balance Sheet",
            "Element": str(code),
            "Sub-element": group,     # << master_group only
            "AZN": amt,
            # all others NaN
            "FS Line": np.nan,
            "Item": np.nan,
            "Currency": np.nan,
            "Amount vs Share": np.nan,
            "Total": np.nan,
            "31-60 days": np.nan,
            "61-90 days": np.nan,
            "91+ days": np.nan,
            "31-60 days_share%inLP": np.nan,
            "61-90 days_share%inLP": np.nan,
            "91+ days_share%inLP": np.nan
        })

    out = pd.DataFrame(rows).sort_values("Element")
    out = apply_bank_period_fallback(out, filename, banks_df)
    return force_master_columns(out), pd.DataFrame()


# ---------- P&L ----------
def extract_pnl(xls, dict_df, items_map_df, banks_df, filename):
    df = read_sheet(xls, "profit_and_loss", xls.rules_path)
    df = promote_headers_if_needed(df)
    ren = {"Bank Name":"Bank","Bank":"Bank","Period":"Period",
           "Indicator tabl":"Indicator table","Indicator table":"Indicator table",
           "Element":"Element","Sub-element":"Sub-element","AZN":"AZN"}
    for k,v in ren.items():
        if k in df.columns: df = df.rename(columns={k:v})
    df["Indicator table"] = "Profit & Loss"
    if "Element" in df.columns:
        df["FS Line"] = df["Element"].astype(str).str.split(".").str[0].map({
            "1":"Interest income","2":"Interest expense","3":"Net interest income",
            "4":"Non-interest income","5":"Operating expenses","6":"Specific reserves",
            "7":"Profit before tax","8":"Profit tax","9":"Net profit (loss)"
        })
        df["Item"] = df["Element"].astype(str).map(items_map_df.set_index("code")["item_en"]).fillna(df.get("Sub-element",""))
    df["Currency"] = np.nan
    df["Amount vs Share"] = "Amount"
    out = df[["Bank","Period","Indicator table","Element","Sub-element","AZN","FS Line","Item","Currency","Amount vs Share"]].copy()
    for c in ["Total","31-60 days","61-90 days","91+ days","31-60 days_share%inLP","61-90 days_share%inLP","91+ days_share%inLP"]:
        out[c] = np.nan
    out = apply_bank_period_fallback(out, filename, banks_df)
    return force_master_columns(out), pd.DataFrame()

# ---------- Capital Adequacy ----------
def extract_capital(xls, dict_df, items_map_df, banks_df, filename):
    df = read_sheet(xls, "capital_adequacy", xls.rules_path)
    df = promote_headers_if_needed(df)
    ren = {"Bank Name":"Bank","Bank":"Bank","Period":"Period",
           "Indicator tabl":"Indicator table","Indicator table":"Indicator table",
           "Element":"Element","Sub-element":"Sub-element","AZN":"AZN"}
    for k,v in ren.items():
        if k in df.columns: df = df.rename(columns={k:v})
    df["Indicator table"] = "Capital Adequacy"
    subs = df.get("Sub-element","").astype(str)
    def map_fs(s):
        sL = s.lower()
        if "tier i" in sL and "cap" in sL: return "Tier I Capital"
        if "total cap" in sL: return "Total Capital"
        if "risk" in sL and "weight" in sL: return "Risk-weighted assets"
        if "ratio" in sL and "tier" in sL: return "Tier I Ratio"
        if "ratio" in sL and "total" in sL: return "Total Capital Ratio"
        return s
    df["FS Line"] = subs.map(map_fs)
    df["Item"] = subs
    df["Currency"] = np.nan
    df["Amount vs Share"] = subs.str.contains("ratio", case=False).map({True:"Ratio %", False:"Amount"})
    out = df[["Bank","Period","Indicator table","Element","Sub-element","AZN","FS Line","Item","Currency","Amount vs Share"]].copy()
    for c in ["Total","31-60 days","61-90 days","91+ days","31-60 days_share%inLP","61-90 days_share%inLP","91+ days_share%inLP"]:
        out[c] = np.nan
    out = apply_bank_period_fallback(out, filename, banks_df)
    return force_master_columns(out), pd.DataFrame()

# ---------- Credit Risk (wide) ----------
def extract_credit(xls, dict_df, banks_df, filename):
    df = read_sheet(xls, "credit_risk", xls.rules_path)
    df = promote_headers_if_needed(df)
    ren = {"Bank":"Bank","Element":"Element","Indicator t":"Indicator table","Indicator table":"Indicator table",
           "Period":"Period","Total":"Total","31-60 days":"31-60 days","61-90 days":"61-90 days","91+ days":"91+ days",
           "31-60 days_share%inLP":"31-60 days_share%inLP","61-90 days_share%inLP":"61-90 days_share%inLP",
           "91+ days_share%inLP":"91+ days_share%inLP"}
    for k,v in ren.items():
        if k in df.columns: df = df.rename(columns={k:v})
    df["Indicator table"] = "Credit Risk"
    df["FS Line"] = df.get("Element","")
    df["Item"] = "Loan portfolio"
    df["Currency"] = np.nan
    df["Amount vs Share"] = "Amount"
    df["AZN"] = np.nan
    keep = ["Bank","Period","Indicator table","Element","AZN","FS Line","Item","Currency","Amount vs Share",
            "Total","31-60 days","61-90 days","91+ days","31-60 days_share%inLP","61-90 days_share%inLP","91+ days_share%inLP"]
    if "Sub-element" in df.columns:
        out = df[["Bank","Period","Indicator table","Element","Sub-element","AZN","FS Line","Item","Currency","Amount vs Share",
                  "Total","31-60 days","61-90 days","91+ days","31-60 days_share%inLP","61-90 days_share%inLP","91+ days_share%inLP"]].copy()
    else:
        out = df[keep].copy()
        out.insert(4, "Sub-element", np.nan)
    out = apply_bank_period_fallback(out, filename, banks_df)
    return force_master_columns(out), pd.DataFrame()

# ---------- Currency Risk ----------
def extract_currency(xls, dict_df, banks_df, filename):
    df = read_sheet(xls, "currency_risk", xls.rules_path)
    df = promote_headers_if_needed(df)
    ren = {"Bank":"Bank","Bank Name":"Bank","Period":"Period","Indicator tabl":"Indicator table","Indicator table":"Indicator table",
           "AZN":"AZN","FS Line":"FS Line","Item":"Item","Currency":"Currency","Amount vs Share":"Amount vs Share"}
    for k,v in ren.items():
        if k in df.columns: df = df.rename(columns={k:v})
    df["Indicator table"] = "Currency Risk"
    out = df.assign(**{"Element":np.nan,"Sub-element":np.nan})[["Bank","Period","Indicator table","Element","Sub-element","AZN","FS Line","Item","Currency","Amount vs Share"]]
    for c in ["Total","31-60 days","61-90 days","91+ days","31-60 days_share%inLP","61-90 days_share%inLP","91+ days_share%inLP"]:
        out[c] = np.nan
    out = apply_bank_period_fallback(out, filename, banks_df)
    return force_master_columns(out), pd.DataFrame()
