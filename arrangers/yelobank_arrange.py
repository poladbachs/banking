import os
import shutil

RAW_BANK = os.path.join("raw_data", "yelobank")
PROCESSED_ROOT = os.path.join("processed_data", "yelobank")

def move_excels_to_processed(raw_root, processed_root):
    for subdir, _, files in os.walk(raw_root):
        for fname in files:
            if fname.endswith(".xlsx") or fname.endswith(".xls"):
                src = os.path.join(subdir, fname)
                # Extract period from path: .../raw_data/yelobank/2022_Q3/file.xlsx → 2022_Q3
                period = os.path.basename(subdir)
                # Only process if period looks like YYYY_Qx
                if not re.match(r"20\d{2}_Q[1-4]", period):
                    continue
                # Target processed folder
                target_dir = os.path.join(processed_root, period)
                os.makedirs(target_dir, exist_ok=True)
                dst = os.path.join(target_dir, fname)
                if os.path.abspath(src) == os.path.abspath(dst):
                    continue
                if os.path.exists(dst):
                    print(f"[DUPLICATE] Already exists: {dst}, skipping.")
                    continue
                shutil.move(src, dst)
                print(f"[MOVED] {src} -> {dst}")
    print("\nDONE! All Excel files moved to processed_data/yelobank/<period>/")

if __name__ == "__main__":
    move_excels_to_processed(RAW_BANK, PROCESSED_ROOT)
