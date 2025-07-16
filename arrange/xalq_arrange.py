import os
import re
import shutil

RAW_BANK = os.path.join("raw_data", "xalq_bank")
PROCESSED_ROOT = os.path.join("processed_data", "xalq_bank")

def parse_info_from_filename(fname):
    """
    Accepts: balance_2020_Q1.pdf, cash_flow_2020_12m.xlsx, capital_adequacy_2022_Q4.pdf, capital_change_2021_Q3.xlsx, etc.
    Returns: period (e.g. 2020_Q1, 2020_12m), out_name (e.g. cash_flow_2020_Q1.pdf/xlsx), ext
    """
    m = re.match(r"([a-z_]+)_(20\d{2}_(?:Q[1-4]|12m))\.(pdf|xlsx|xls)", fname)
    if m:
        type_part = m.group(1)
        period = m.group(2)
        ext = m.group(3)
        out_name = f"{type_part}_{period}.{ext}"
        return period, out_name, ext
    # Try with possible duplicated period part
    m2 = re.match(r"(20\d{2}_(?:Q[1-4]|12m))_([a-z_]+)_(20\d{2}_(?:Q[1-4]|12m))\.(pdf|xlsx|xls)", fname)
    if m2:
        period = m2.group(1)
        type_part = m2.group(2)
        ext = m2.group(4)
        out_name = f"{type_part}_{period}.{ext}"
        return period, out_name, ext
    return None, None, None

def arrange_files(root_folder, processed_root):
    for fname in os.listdir(root_folder):
        if not (fname.endswith(".pdf") or fname.endswith(".xlsx") or fname.endswith(".xls")):
            continue
        src = os.path.join(root_folder, fname)
        period, out_name, ext = parse_info_from_filename(fname)
        if not period or not out_name:
            print(f"[SKIP] Unrecognized file name format: {fname}")
            continue
        # PDF files go to raw_data/xalq_bank/<period>/
        if ext == "pdf":
            target_dir = os.path.join(root_folder, period)
        # Excel files go to processed_data/xalq_bank/<period>/
        else:
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
    print("\nDONE! All PDF and Excel files arranged in correct structure.")

if __name__ == "__main__":
    arrange_files(RAW_BANK, PROCESSED_ROOT)