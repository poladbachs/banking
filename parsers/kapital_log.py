import os
import pandas as pd

RAW_ROOT = "raw_data/kapital_bank"
PROCESSED_ROOT = "processed_data/kapital_bank_excel"
LOG_FILE = "boss_status_kapital.txt"

missing_outputs = []
capital_adequacy_warns = []

for root, dirs, files in os.walk(RAW_ROOT):
    rel_path = os.path.relpath(root, RAW_ROOT)
    processed_folder = os.path.join(PROCESSED_ROOT, rel_path)
    if not os.path.exists(processed_folder):
        missing_outputs.append(f"[ERROR] No processed folder for {rel_path}")
        continue
    for fname in files:
        base, ext = os.path.splitext(fname)
        if ext.lower() not in [".xlsx", ".xls", ".pdf"]:
            continue
        expected_excel = os.path.join(processed_folder, base + ".xlsx")
        if not os.path.exists(expected_excel):
            missing_outputs.append(f"[ERROR] Missing Excel output for {rel_path}/{base} (raw: {ext})")
        else:
            # Only care about capital_adequacy.pdf → capital_adequacy.xlsx
            if "adequacy" in base.lower() and ext.lower() == ".pdf":
                try:
                    xl = pd.ExcelFile(expected_excel)
                    n_sheets = len(xl.sheet_names)
                    if n_sheets < 2:
                        capital_adequacy_warns.append(
                            f"[WARNING] Capital Adequacy {expected_excel} has only {n_sheets} table(s) (sheet)."
                        )
                except Exception as e:
                    capital_adequacy_warns.append(f"[ERROR] Could not read {expected_excel}: {e}")

with open(LOG_FILE, "w") as f:
    f.write("========== RAW-vs-PROCESSED: MISSING OUTPUTS ==========\n")
    if not missing_outputs:
        f.write("[OK] All RAW reports have matching Excel outputs in processed folder.\n")
    else:
        for line in missing_outputs:
            f.write(line + "\n")

    f.write("\n========== CAPITAL ADEQUACY: MISSING SECOND TABLE (WARNINGS) ==========\n")
    if not capital_adequacy_warns:
        f.write("[OK] All Capital Adequacy Excels have 2+ tables (sheets).\n")
    else:
        for line in capital_adequacy_warns:
            f.write(line + "\n")

print("\nDONE! FULL RAW-PROCESSED + WARNINGS LOG WRITTEN TO boss_status_kapital.txt\n")