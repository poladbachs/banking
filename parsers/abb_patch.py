import os
import re
import pandas as pd
from pdfminer.high_level import extract_text

PROCESSED_ROOT = os.path.join(os.path.dirname(__file__), '..', 'processed_data', 'abb_bank_excel')
RAW_ROOT = os.path.join(os.path.dirname(__file__), '..', 'raw_data', 'abb_bank')
HEADERS = ["Əmsal", "Norma (Sistem əhəmiyyətli)", "Norma (Banklar istisna)", "Fakt"]

def fix_percent(val):
    try:
        f = float(val)
        if 0 < f < 1:
            return f"{round(f*100, 2)}%"
        else:
            return str(val)
    except:
        return str(val)

def get_warninged_quarters(boss_report_path):
    # Return: list of tuples (quarter_folder, excel_filename)
    warnings = []
    with open(boss_report_path, encoding="utf-8") as f:
        for line in f:
            m = re.search(r"processed_data/abb_bank_excel/([0-9]{4}_[^/]+)/capital_adequacy_([0-9]{4}_[^\.]+)\.xlsx", line)
            if m:
                warnings.append((m.group(1), f"capital_adequacy_{m.group(1)}.xlsx"))
    return sorted(set(warnings))

def extract_table2_from_pdf(pdf_path):
    # Extract bottom 3 lines with at least 4 columns (separated by whitespace)
    text = extract_text(pdf_path)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    # Heuristic: keep only lines with at least 4 whitespace-separated "words"
    rows = [re.split(r'\s{2,}|\t', line) for line in lines if len(re.split(r'\s{2,}|\t', line)) >= 4]
    if len(rows) < 3:
        # Fallback: just last 3 lines with enough data
        rows = [re.split(r'\s+', line) for line in lines if len(re.split(r'\s+', line)) >= 4]
        rows = rows[-3:]
    else:
        rows = rows[-3:]
    # Pad or trim to exactly 4 columns per row
    rows = [row[:4] + ['']*(4-len(row)) if len(row) < 4 else row[:4] for row in rows]
    df = pd.DataFrame(rows, columns=HEADERS)
    for col in df.columns:
        df[col] = df[col].apply(fix_percent)
    return df

def patch_table2_from_pdf(quarter, excel_name):
    folder = os.path.join(PROCESSED_ROOT, quarter)
    raw_folder = os.path.join(RAW_ROOT, quarter)
    excel = os.path.join(folder, excel_name)
    pdf = os.path.join(raw_folder, excel_name.replace('.xlsx', '.pdf'))
    if not os.path.exists(pdf):
        print(f"[SKIP] No PDF at {pdf}")
        return
    if not os.path.exists(excel):
        print(f"[SKIP] No Excel at {excel}")
        return
    df = extract_table2_from_pdf(pdf)
    with pd.ExcelWriter(excel, mode="a", if_sheet_exists="replace", engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Table_2", index=False)
    print(f"[PATCHED] Table_2 from PDFMiner in {excel}")

if __name__ == "__main__":
    BOSS_REPORT = os.path.join(os.path.dirname(__file__), '..', 'boss_report_abb.txt')
    warnings = get_warninged_quarters(BOSS_REPORT)
    if not warnings:
        print("No warnings found in boss report. All done!")
    else:
        for quarter, excel_name in warnings:
            patch_table2_from_pdf(quarter, excel_name)
        print("\nDONE! All Table_2 sheets patched from PDFMiner into relevant Excels.")