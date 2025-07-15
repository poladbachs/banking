import os
import re
import shutil

RAW_BANK = os.path.join("raw_data", "abb_bank")
PROCESSED_ROOT = os.path.join("processed_data", "abb_bank")

def parse_info_from_filename(fname):
    """
    Accepts: 2020_12m_cash_flow_2020_12m.pdf/xlsx, 2025_Q1_risk_reports_credit_risk_2025_Q1.pdf/xlsx, etc.
    Returns: period (e.g. 2020_Q1, 2020_12m), out_name (e.g. cash_flow_2020_Q1.pdf/xlsx)
    """
    m = re.match(r"(20\d{2}_(?:Q[1-4]|12m))_(.+)_(20\d{2}_(?:Q[1-4]|12m))\.(pdf|xlsx)", fname)
    if m:
        period = m.group(1)
        type_part = m.group(2)
        ext = m.group(4)
        out_name = f"{type_part}_{period}.{ext}"
        return period, out_name, ext
    # Fallback: try to parse by splitting
    m2 = re.match(r"(.+?)_(20\d{2}_(?:Q[1-4]|12m))\.(pdf|xlsx)", fname)
    if m2:
        type_part = m2.group(1)
        period = m2.group(2)
        ext = m2.group(3)
        out_name = f"{type_part}_{period}.{ext}"
        return period, out_name, ext
    return None, None, None

def arrange_files(root_folder, processed_root):
    for fname in os.listdir(root_folder):
        if not (fname.endswith(".pdf") or fname.endswith(".xlsx")):
            continue
        src = os.path.join(root_folder, fname)
        period, out_name, ext = parse_info_from_filename(fname)
        if not period or not out_name:
            print(f"[SKIP] Unrecognized file name format: {fname}")
            continue
        # PDF files stay in raw_data/abb_bank/period/
        if ext == "pdf":
            target_dir = os.path.join(root_folder, period)
        # Excel files go to processed_data/abb_bank/period/
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
