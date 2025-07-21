import os
import re
import shutil

RAW_BANK = os.path.join("raw_data", "yelobank")
PROCESSED_ROOT = os.path.join("processed_data", "yelobank")

def parse_info_from_filename(fname):
    """
    Accepts: balance_sheet_2020_Q1.pdf, cash_flow_2023_Q4.xlsx, etc.
    Returns: period (e.g. 2020_Q1), out_name (e.g. cash_flow_2020_Q1.pdf), ext
    """
    m = re.match(r"([a-z_]+)_(20\d{2}_Q[1-4])\.(pdf|xlsx|xls)", fname)
    if m:
        type_part = m.group(1)
        period = m.group(2)
        ext = m.group(3)
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
        # PDF files go to raw_data/yelobank/<period>/
        if ext == "pdf":
            target_dir = os.path.join(root_folder, period)
        # Excel files go to processed_data/yelobank/<period>/
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