import os
import re
import shutil

PROCESSED_ROOT = os.path.join("processed_data", "bank_of_baku")

def parse_info_from_filename(fname):
    """
    Example: bank_of_baku_balance_sheet_2020_Q1.xlsx
             → period = 2020_Q1, output name = fname
    """
    m = re.match(r"bank_of_baku_[a-z_]+_(20\d{2})_(Q[1-4])\.xlsx", fname)
    if m:
        year = m.group(1)
        quarter = m.group(2)
        period = f"{year}_{quarter}"
        return period, fname
    return None, None

def arrange_files(processed_root):
    files = [f for f in os.listdir(processed_root) if f.endswith(".xlsx")]
    for fname in files:
        src = os.path.join(processed_root, fname)
        period, out_name = parse_info_from_filename(fname)
        if not period or not out_name:
            print(f"[SKIP] Unrecognized file name format: {fname}")
            continue
        target_dir = os.path.join(processed_root, period)
        os.makedirs(target_dir, exist_ok=True)
        dst = os.path.join(target_dir, out_name)
        if os.path.abspath(src) == os.path.abspath(dst):
            continue
        if os.path.exists(dst):
            print(f"[DUPLICATE] Already exists: {dst}, skipping.")
            continue
        shutil.move(src, dst)
        print(f"[MOVED] {src} -> {dst}")
    print("\nDONE! All Bank of Baku Excel files arranged into 2020_Q1-style folders.")

if __name__ == "__main__":
    arrange_files(PROCESSED_ROOT)