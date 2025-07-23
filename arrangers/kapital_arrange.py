import os
import re
import shutil

RAW_ROOT = "raw_data/kapital_bank"
PROCESSED_ROOT = "processed_data/kapital_bank"

def parse_info_from_filename(fname):
    m = re.match(r"([a-z_]+)_(20\d{2}_(?:Q[1-4]|12m))\.(xlsx|xls)", fname)
    if m:
        report_type, period, ext = m.groups()
        # Legacy: treat 12m as Q4 for normalization
        if period.endswith("12m"):
            norm_period = period.replace("12m", "Q4")
        else:
            norm_period = period
        return report_type, norm_period, ext
    return None, None, None

def arrange_excels(raw_root, processed_root):
    moved = 0
    skipped = 0
    for dirpath, _, files in os.walk(raw_root):
        for fname in files:
            if not (fname.endswith(".xlsx") or fname.endswith(".xls")):
                continue
            report_type, period, ext = parse_info_from_filename(fname)
            if not period:
                print(f"[SKIP] Unrecognized format: {fname}")
                skipped += 1
                continue
            src = os.path.join(dirpath, fname)
            target_dir = os.path.join(processed_root, period)
            os.makedirs(target_dir, exist_ok=True)
            dst = os.path.join(target_dir, fname)
            if os.path.abspath(src) == os.path.abspath(dst):
                continue
            if os.path.exists(dst):
                print(f"[DUPLICATE] {dst} exists, skipping.")
                skipped += 1
                continue
            shutil.move(src, dst)
            print(f"[MOVED] {src} → {dst}")
            moved += 1
    print(f"\nDONE! {moved} Excels moved, {skipped} skipped.")
    print("All Excels in processed_data/kapital_bank/<year>_<quarter>/.")

if __name__ == "__main__":
    arrange_excels(RAW_ROOT, PROCESSED_ROOT)
