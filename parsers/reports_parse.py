import os
import pandas as pd
import camelot
from glob import glob

RAW_DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'raw_data')
PROCESSED_DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'processed_data')
os.makedirs(PROCESSED_DATA_DIR, exist_ok=True)

def process_pdf(pdf_path, out_csv):
    try:
        tables = camelot.read_pdf(pdf_path, pages='all', flavor='stream')
        if tables and len(tables) > 0:
            tables[0].to_csv(out_csv, index=False)
            print(f"  ✔ PDF extracted: {os.path.basename(pdf_path)} → {os.path.basename(out_csv)}")
        else:
            print(f"  ✘ No tables found in PDF: {os.path.basename(pdf_path)}")
    except Exception as e:
        print(f"  ✘ PDF error [{pdf_path}]: {e}")

def process_excel(excel_path, out_csv):
    try:
        df = pd.read_excel(excel_path)
        df.to_csv(out_csv, index=False)
        print(f"  ✔ Excel extracted: {os.path.basename(excel_path)} → {os.path.basename(out_csv)}")
    except Exception as e:
        print(f"  ✘ Excel error [{excel_path}]: {e}")

def main():
    for bank_dir in glob(os.path.join(RAW_DATA_DIR, '*')):
        if not os.path.isdir(bank_dir):
            continue
        bank_name = os.path.basename(bank_dir)
        for quarter_dir in glob(os.path.join(bank_dir, '*_*')):
            quarter = os.path.basename(quarter_dir)
            output_dir = os.path.join(PROCESSED_DATA_DIR, bank_name, quarter)
            os.makedirs(output_dir, exist_ok=True)
            for fname in os.listdir(quarter_dir):
                in_path = os.path.join(quarter_dir, fname)
                report_base, ext = os.path.splitext(fname)
                out_csv = os.path.join(output_dir, report_base + '.csv')
                ext = ext.lower()
                if ext == '.pdf':
                    process_pdf(in_path, out_csv)
                elif ext in ('.xlsx', '.xls', '.csv'):
                    process_excel(in_path, out_csv)
                else:
                    print(f"  Skipping unknown file: {fname}")

if __name__ == "__main__":
    main()