import os
import re
import shutil

RAW_ROOT = os.path.join("raw_data", "access_bank")
PROCESSED_ROOT = os.path.join("processed_data", "access_bank")

def parse_info_from_filename(fname):
    # Accepts: balance_2023_Q2.xlsx, risk_reports_credit_risk_2025_Q2.xlsx, credit_risk_2023_Q4.xlsx, etc
    m = re.match(r"(?:risk_reports_)?([a-z_]+)_(20\d{2}_(?:Q[1-4]|12m))\.(xlsx|xls)", fname)
    if m:
        report_type, period, ext = m.groups()
        # Normalize 12m to Q4
        if period.endswith("12m"):
            norm_period = period.replace("12m", "Q4")
        else:
            norm_period = period
        out_name = f"{report_type}_{norm_period}.{ext}"
        return norm_period, out_name, ext
    return None, None, None

def arrange_excels_only(raw_root, processed_root):
    moved = 0
    skipped = 0
    for dirpath, _, files in os.walk(raw_root):
        for fname in files:
            if not fname.endswith((".xlsx", ".xls")):
                continue
            src = os.path.join(dirpath, fname)
            period, out_name, ext = parse_info_from_filename(fname)
            if not period or not out_name:
                print(f"[SKIP] Unrecognized Excel file name: {fname}")
                skipped += 1
                continue
            target_dir = os.path.join(processed_root, period)
            os.makedirs(target_dir, exist_ok=True)
            dst = os.path.join(target_dir, out_name)
            if os.path.abspath(src) == os.path.abspath(dst):
                continue
            if os.path.exists(dst):
                print(f"[DUPLICATE] Excel already exists: {dst}, skipping.")
                skipped += 1
                continue
            shutil.move(src, dst)
            print(f"[MOVED] {src} -> {dst}")
            moved += 1
    print(f"\nDONE! {moved} Excels moved, {skipped} skipped.")
    print("All Excels in processed_data/access_bank/<year>_<quarter>/.")

if __name__ == "__main__":
    arrange_excels_only(RAW_ROOT, PROCESSED_ROOT)