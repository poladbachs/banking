import os
import re
import pandas as pd
from pdfminer.high_level import extract_text

RAW_ROOT = "raw_data/kapital_bank"
PROCESSED_ROOT = "processed_data/kapital_bank_excel"
BOSS_REPORT = "boss_report.txt"

def get_warninged_quarters(boss_report_path):
    quarters = []
    with open(boss_report_path, encoding="utf-8") as f:
        for line in f:
            m = re.search(r"processed_data/kapital_bank_excel/([0-9]{4}_Q[1-4])/capital_adequacy_.*\.xlsx", line)
            if m:
                quarters.append(m.group(1))
    return sorted(set(quarters))

def extract_emsallar_block(pdf_path):
    text = extract_text(pdf_path)
    lines = text.split('\n')
    start_idx = None
    for i, line in enumerate(lines):
        # Try to spot where Table 2 starts (edit these keys as needed for your tables)
        if "Əmsallar" in line or "faizlə" in line or "% " in line:
            start_idx = i
            break
    if start_idx is not None:
        block = lines[max(0, start_idx-2):start_idx+7]  # try to get a meaningful chunk
        return [l.strip() for l in block if l.strip()]
    else:
        return []

def block_to_dataframe(block_lines):
    # Try to split rows into columns for Excel
    rows = []
    for line in block_lines:
        # Split by 2+ spaces or tabs, otherwise keep as is
        parts = re.split(r" {2,}|\t", line)
        rows.append([p for p in parts if p])
    return pd.DataFrame(rows)

def patch_excels(quarters):
    for quarter in quarters:
        pdf = os.path.join(RAW_ROOT, quarter, "capital_adequacy.pdf")
        excel = os.path.join(PROCESSED_ROOT, quarter, f"capital_adequacy_{quarter}.xlsx")
        if not os.path.exists(pdf):
            print(f"[SKIP] No PDF at {pdf}")
            continue
        if not os.path.exists(excel):
            print(f"[SKIP] No Excel at {excel}")
            continue
        # Extract block
        block = extract_emsallar_block(pdf)
        if not block:
            print(f"[WARNING] No Əmsallar block found in {pdf}")
            continue
        df = block_to_dataframe(block)
        # Patch Excel with new sheet
        with pd.ExcelWriter(excel, mode="a", if_sheet_exists="replace") as writer:
            df.to_excel(writer, sheet_name="Table_2", index=False)
        print(f"[PATCHED] Added Table_2 to {excel}")

if __name__ == "__main__":
    print("Scanning boss report for problematic quarters...")
    quarters = get_warninged_quarters(BOSS_REPORT)
    if not quarters:
        print("No warnings found in boss report. All done!")
    else:
        patch_excels(quarters)
        print("\nDONE! All patched. Check your Excels for Table_2.")