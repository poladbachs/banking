import os
import re
import shutil

RAW_BANK = os.path.join("raw_data", "access_bank")
PROCESSED_ROOT = os.path.join("processed_data", "access_bank")

def parse_info_from_filename(fname):
    m = re.match(r"([a-z_]+)_(20\d{2})_(Q[1-4]|12m)\.(pdf|xlsx|xls)", fname)
    if m:
        type_part, year, quarter, ext = m.groups()
        period = f"{year}_{quarter}"
        out_name = f"{type_part}_{period}.{ext}"
        return period, out_name, ext
    m = re.match(r"(risk_reports_[a-z_]+)_(20\d{2})_(Q[1-4]|12m)\.(pdf|xlsx|xls)", fname)
    if m:
        type_part, year, quarter, ext = m.groups()
        period = f"{year}_{quarter}"
        out_name = f"{type_part}_{period}.{ext}"
        return period, out_name, ext
    m = re.match(r"(risk_reports_[a-z_]+)[\s_]+(20\d{2})[\s_]+(Q[1-4]|12m)\.(pdf|xlsx|xls)", fname)
    if m:
        type_part, year, quarter, ext = m.groups()
        period = f"{year}_{quarter}"
        out_name = f"{type_part}_{period}.{ext}"
        return period, out_name, ext
    return None, None, None

def deep_iter_files(root, exts=(".pdf", ".xlsx", ".xls")):
    for subdir, _, files in os.walk(root):
        for fname in files:
            if fname.lower().endswith(exts):
                yield os.path.join(subdir, fname)

def arrange_files(bank_raw, bank_processed):
    # PDFs: put in raw/<period>
    for src in deep_iter_files(bank_raw, exts=(".pdf",)):
        fname = os.path.basename(src)
        period, out_name, ext = parse_info_from_filename(fname)
        if not period or not out_name:
            print(f"[SKIP] Unrecognized file name format: {fname}")
            continue
        target_dir = os.path.join(bank_raw, period)
        os.makedirs(target_dir, exist_ok=True)
        dst = os.path.join(target_dir, out_name)
        if os.path.abspath(src) == os.path.abspath(dst):
            continue
        if os.path.exists(dst):
            print(f"[DUPLICATE] Already exists: {dst}, skipping.")
            continue
        shutil.move(src, dst)
        print(f"[MOVED] {src} -> {dst}")

    # Excels: put in processed/<period>
    for src in deep_iter_files(bank_raw, exts=(".xlsx", ".xls")):
        fname = os.path.basename(src)
        period, out_name, ext = parse_info_from_filename(fname)
        if not period or not out_name:
            print(f"[SKIP] Unrecognized file name format: {fname}")
            continue
        target_dir = os.path.join(bank_processed, period)
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