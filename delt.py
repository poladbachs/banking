import os
import re

ROOT_DIR = "processed_data"

for root, dirs, files in os.walk(ROOT_DIR):
    for fname in files:
        # Match patterns like balance_sheet_sheet_2024_Q2.xlsx
        if re.match(r"(?i)^balance_sheet_sheet_", fname):
            old_path = os.path.join(root, fname)
            new_name = re.sub(r"(?i)^balance_sheet_sheet_", "balance_sheet_", fname)
            new_path = os.path.join(root, new_name)

            if not os.path.exists(new_path):
                os.rename(old_path, new_path)
                print(f"Fixed: {old_path} -> {new_path}")
            else:
                print(f"[SKIP] Target exists: {new_path}")
