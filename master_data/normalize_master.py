import pandas as pd
import os

INPUT_PATH = "./master_data/kapital_bank_master.xlsx"
OUTPUT_PATH = "./master_data/kapital_bank_master_normalized.xlsx"

# 1. Load master Excel
df = pd.read_excel(INPUT_PATH)

# 2. Remove unnamed/empty columns
df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
df = df.dropna(how="all")

# 3. Ensure context columns exist and are first
context_cols = ['bank', 'year', 'quarter', 'report_type']
for col in context_cols:
    if col not in df.columns:
        df[col] = "kapital_bank" if col == "bank" else None
df[context_cols] = df[context_cols].ffill()

# 4. Identify real data columns (anything not in context)
data_cols = [col for col in df.columns if col not in context_cols]

# 5. Melt to long format
df_long = df.melt(
    id_vars=context_cols,
    value_vars=data_cols,
    var_name="item",
    value_name="value"
)

# 6. Drop empty/junk rows
df_long = df_long.dropna(subset=["value"])
df_long = df_long[df_long["value"].astype(str).str.strip() != ""]
df_long = df_long[~df_long["item"].str.contains("Unnamed", na=False)]

# 7. Optional: sort
df_long = df_long.sort_values(context_cols + ["item"]).reset_index(drop=True)

# 8. Save
df_long.to_excel(OUTPUT_PATH, index=False)
print(f"✅ Normalized file saved: {OUTPUT_PATH}")
print(f"Rows: {len(df_long)} | Columns: {list(df_long.columns)}")
