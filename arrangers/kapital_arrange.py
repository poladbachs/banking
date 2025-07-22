import os
import re
import shutil

RAW_ROOT = "raw_data/kapital_bank"
PROCESSED_ROOT = "processed_data/kapital_bank"

def parse_info_from_filename(fname):
    # Matches: report_2025_Q2.pdf, report_2020_12m.pdf, etc
    m = re.match(r"([a-z_]+)_(20\d{2}_(?:Q[1-4]|12m))\.(pdf|xlsx|xls)", fname)
    if m:
        report_type, period, ext = m.groups()
        # Legacy: treat 12m as Q4
        if period.endswith("12m"):
            norm_period = period.replace("12m", "Q4")
        else:
            norm_period = period
        return report_type, norm_period, ext
    return None, None, None

def arrange_files(raw_root, processed_root):
    moved = 0
    skipped = 0
    for dirpath, _, files in os.walk(raw_root):
        for fname in files:
            if not (fname.endswith(".pdf") or fname.endswith(".xlsx") or fname.endswith(".xls")):
                continue
            report_type, period, ext = parse_info_from_filename(fname)
            if not period:
                print(f"[SKIP] Unrecognized format: {fname}")
                skipped += 1
                continue
            src = os.path.join(dirpath, fname)
            # PDFs: move to raw_data/kapital_bank/<period>/
            if ext == "pdf":
                target_dir = os.path.join(raw_root, period)
            # Excels: move to processed_data/kapital_bank/<period>/
            else:
                target_dir = os.path.join(processed_root, period)
            os.makedirs(target_dir, exist_ok=True)
            dst = os.path.join(target_dir, fname)
            # Avoid moving if already there
            if os.path.abspath(src) == os.path.abspath(dst):
                continue
            if os.path.exists(dst):
                print(f"[DUPLICATE] {dst} exists, skipping.")
                skipped += 1
                continue
            shutil.move(src, dst)
            print(f"[MOVED] {src} → {dst}")
            moved += 1
    print(f"\nDONE! {moved} moved, {skipped} skipped.\nAll PDFs in raw_data/kapital_bank/<year>_<quarter>/, Excels in processed_data/kapital_bank/<year>_<quarter>/.")

if __name__ == "__main__":
    arrange_files(RAW_ROOT, PROCESSED_ROOT)