import os
import shutil

RAW_ROOT = "raw_data/abb_bank"
POOL_DIR = "temp_pool"

os.makedirs(POOL_DIR, exist_ok=True)

for root, dirs, files in os.walk(RAW_ROOT):
    for file in files:
        if file.lower().endswith('.pdf'):
            src_path = os.path.join(root, file)
            # Add the relative path as prefix to filename to prevent collisions
            rel_path = os.path.relpath(src_path, RAW_ROOT).replace(os.sep, '_')
            dst_path = os.path.join(POOL_DIR, rel_path)
            shutil.copy2(src_path, dst_path)
            print(f"[COPIED] {src_path} → {dst_path}")

print("\n[INFO] All PDFs copied to temp_pool/. Ready for Acrobat batch export.")