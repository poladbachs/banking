import os
import pandas as pd

BANK = "kapital_bank"
PROCESSED_ROOT = "processed_data/kapital_bank"
OUT_MASTER = "master_data/kapital_bank_master.xlsx"

all_rows = []

for quarter_folder in sorted(os.listdir(PROCESSED_ROOT)):
    qpath = os.path.join(PROCESSED_ROOT, quarter_folder)
    if not os.path.isdir(qpath):
        continue
    year, quarter = quarter_folder.split("_")
    for csvfile in os.listdir(qpath):
        if not csvfile.endswith(".csv"):
            continue
        report_type = csvfile.replace(".csv", "")
        try:
            df = pd.read_csv(os.path.join(qpath, csvfile))
        except Exception as e:
            print(f"Error reading {csvfile}: {e}")
            continue
        df["bank"] = BANK
        df["year"] = year
        df["quarter"] = quarter
        df["report_type"] = report_type
        all_rows.append(df)

if not all_rows:
    raise RuntimeError("No data found. Check processed_data folders.")

master_df = pd.concat(all_rows, ignore_index=True)
# Move context columns to front if not already
context_cols = ['bank', 'year', 'quarter', 'report_type']
other_cols = [c for c in master_df.columns if c not in context_cols]
master_df = master_df[context_cols + other_cols]
master_df.to_excel(OUT_MASTER, index=False)
print(f"✅ Aggregated master file saved: {OUT_MASTER}")
print(f"Rows: {len(master_df)}, Columns: {list(master_df.columns)}")
