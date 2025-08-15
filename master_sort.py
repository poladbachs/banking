import pandas as pd
import re

# ---- Load Excel ----
df = pd.read_excel("master.xlsx")

# ---- Ensure columns exist ----
required_cols = ["Period", "Bank", "Indicator table", "Element"]
for col in required_cols:
    if col not in df.columns:
        raise ValueError(f"Missing required column: {col}")

# ---- Period parser: 'YYYY Qn' -> (year, quarter) ----
def parse_period(period_str):
    match = re.match(r"(\d{4})\s*[Qq](\d)", str(period_str))
    if match:
        year, quarter = match.groups()
        return int(year), int(quarter)
    return (9999, 9)  # unknown format at end

# ---- Element parser: '3.1.2' -> (3,1,2) ----
def parse_element(el):
    parts = str(el).strip().split(".")
    try:
        return tuple(int(p) for p in parts)
    except ValueError:
        return (9999,)

# ---- First sort ----
df["Period_Sort"]  = df["Period"].apply(parse_period)
df["Element_Sort"] = df["Element"].apply(parse_element)
df.sort_values(
    by=["Period_Sort", "Bank", "Indicator table", "Element_Sort"],
    ascending=[True, True, True, True],
    inplace=True
)

# ---- Fix duplicates (1.5.2 -> 1.5.5 for every 2nd, 4th, ... occurrence; same for 1.5.3 -> 1.5.6)
def fix_dupes(group):
    for target, newval in [("1.5.2", "1.5.5"), ("1.5.3", "1.5.6")]:
        mask = group["Element"].astype(str).str.strip().eq(target)
        # cumulative count over matches; even occurrences -> rename
        counts = mask.cumsum()
        even_mask = mask & (counts % 2 == 0)
        group.loc[even_mask, "Element"] = newval
    return group

df = df.groupby(["Period", "Bank", "Indicator table"], group_keys=False).apply(fix_dupes)

# ---- Recompute Element sort key and sort again ----
df["Element_Sort"] = df["Element"].apply(parse_element)
df.sort_values(
    by=["Period_Sort", "Bank", "Indicator table", "Element_Sort"],
    ascending=[True, True, True, True],
    inplace=True
)

# ---- Clean up helper cols ----
df.drop(columns=["Period_Sort", "Element_Sort"], inplace=True)

# ---- Save to new file (single sheet) ----
with pd.ExcelWriter("master_sorted.xlsx", engine="openpyxl", mode="w") as writer:
    df.to_excel(writer, index=False, sheet_name="Sheet1")

print("master_sorted.xlsx created successfully.")