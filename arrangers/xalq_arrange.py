import os
import re
import shutil

RAW_BANK = os.path.join("raw_data", "xalq_bank")
PROCESSED_ROOT = os.path.join("processed_data", "xalq_bank")

def parse_info_from_filename(fname):
    """
    Accepts: cash_flow_2020_Q1.xlsx, capital_change_2021_12m.xls, etc.
    Returns: period (e.g. 2020_Q1), out_name (full correct filename), ext
    """
    m = re.match(r"([a-z_]+)_(20\d{2}_(?:Q[1-4]|12m))\.(xlsx|xls)", fname)
    if m:
        type_part = m.group(1)
        period = m.group(2)
        ext = m.group(3)
        out_name = f"{type_part}_{period}.{ext}"
        return period, out_name, ext
    # Handle files like 2020_Q1_cash_flow_2020_Q1.xlsx (legacy, rare)
    m2 = re.match(r"(20\d{2}_(?:Q[1-4]|12m))_([a-z_]+)_(20\d{2}_(?:Q[1-4]|12m))\.(xlsx|xls)", fname)
    if m2:
        period = m2.group(1)
        type_part = m2.group(2)
        ext = m2.group(4)
        out_name = f"{type_part}_{period}.{ext}"
        return period, out_name, ext
    return None, None, None

def arrange_excels_only(raw_folder, processed_root):
    for fname in os.listdir(raw_folder):
        if not fname.endswith((".xlsx", ".xls")):
            continue
        src = os.path.join(raw_folder, fname)
        period, out_name, ext = parse_info_from_filename(fname)
        if not period or not out_name:
            print(f"[SKIP] Unrecognized Excel file name: {fname}")
            continue
        target_dir = os.path.join(processed_root, period)
        os.makedirs(target_dir, exist_ok=True)
        dst = os.path.join(target_dir, out_name)
        if os.path.abspath(src) == os.path.abspath(dst):
            continue
        if os.path.exists(dst):
            print(f"[DUPLICATE] Excel already exists: {dst}, skipping.")
            continue
        shutil.move(src, dst)
        print(f"[MOVED] {src} -> {dst}")
    print("\nDONE! All Excel files moved. PDFs untouched.")

if __name__ == "__main__":
    arrange_excels_only(RAW_BANK, PROCESSED_ROOT)