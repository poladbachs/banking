import os

RAW_ROOT = "raw_data/abb_bank"
PROCESSED_ROOT = "processed_data/abb_bank"
LOG_FILE = "boss_status_abb.txt"

missing_outputs = []

for root, dirs, files in os.walk(RAW_ROOT):
    rel_path = os.path.relpath(root, RAW_ROOT)
    processed_folder = os.path.join(PROCESSED_ROOT, rel_path)
    if not os.path.exists(processed_folder):
        missing_outputs.append(f"[ERROR] No processed folder for {rel_path}")
        continue
    for fname in files:
        base, ext = os.path.splitext(fname)
        if ext.lower() not in [".pdf"]:
            continue
        expected_excel = os.path.join(processed_folder, base + ".xlsx")
        if not os.path.exists(expected_excel):
            missing_outputs.append(f"[ERROR] Missing Excel output for {rel_path}/{base} (raw: {ext})")

with open(LOG_FILE, "w") as f:
    f.write("========== RAW-vs-PROCESSED: MISSING OUTPUTS ==========\n")
    if not missing_outputs:
        f.write("[OK] All RAW reports have matching Excel outputs in processed folder.\n")
    else:
        for line in missing_outputs:
            f.write(line + "\n")

print("\nDONE! FULL RAW-PROCESSED LOG WRITTEN TO boss_status_abb.txt\n")
