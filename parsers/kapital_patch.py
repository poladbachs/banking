import os
import pandas as pd

PROCESSED_ROOT = os.path.join(os.path.dirname(__file__), '..', 'processed_data', 'kapital_bank_excel')
HEADERS = ["Əmsal", "Norma (Sistem əhəmiyyətli)", "Norma (Banklar istisna)", "Fakt"]

def fix_percent(val):
    # Only fix if value is float and between 0 and 1, otherwise keep as is
    try:
        f = float(val)
        if 0 < f < 1:
            # 0.0491 -> 4.91%
            return f"{round(f*100, 2)}%"
        else:
            return str(val)
    except:
        # Already text, just return as is
        return str(val)

def patch_table2_from_exports(quarter):
    folder = os.path.join(PROCESSED_ROOT, quarter)
    export_file = os.path.join(folder, "table_2.xlsx")
    excel = os.path.join(folder, f"capital_adequacy_{quarter}.xlsx")
    if not os.path.exists(export_file):
        print(f"[SKIP] No Table2 Excel at {export_file}")
        return
    if not os.path.exists(excel):
        print(f"[SKIP] No master Excel at {excel}")
        return

    # Read as all text, but handle float->percent
    df = pd.read_excel(export_file, header=None, dtype=str, engine="openpyxl")
    df = df.iloc[-3:, :4]
    df.columns = HEADERS
    # Now: Fix percent-looking floats
    for col in df.columns:
        df[col] = df[col].apply(fix_percent)
    with pd.ExcelWriter(excel, mode="a", if_sheet_exists="replace", engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Table_2", index=False)
    print(f"[PATCHED] Table_2 from Acrobat export into {excel}")

def get_warninged_quarters(boss_report_path):
    import re
    quarters = []
    with open(boss_report_path, encoding="utf-8") as f:
        for line in f:
            m = re.search(r"processed_data/kapital_bank_excel/([0-9]{4}_Q[1-4])/capital_adequacy_.*\.xlsx", line)
            if m:
                quarters.append(m.group(1))
    return sorted(set(quarters))

if __name__ == "__main__":
    BOSS_REPORT = os.path.join(os.path.dirname(__file__), '..', 'boss_report.txt')
    quarters = get_warninged_quarters(BOSS_REPORT)
    if not quarters:
        print("No warnings found in boss report. All done!")
    else:
        for q in quarters:
            patch_table2_from_exports(q)
        print("\nDONE! All Table_2 sheets patched from Acrobat exports into relevant Excels.")
