import os
import pandas as pd

import tabula
import camelot
import pdfplumber

RAW_ROOT = "raw_data/kapital_bank"
PROCESSED_ROOT = "processed_data/kapital_bank"

for root, dirs, files in os.walk(RAW_ROOT):
    for fname in files:
        ext = os.path.splitext(fname)[1].lower()
        full_path = os.path.join(root, fname)
        rel_path = os.path.relpath(root, RAW_ROOT)
        out_folder = os.path.join(PROCESSED_ROOT, rel_path)
        os.makedirs(out_folder, exist_ok=True)
        base = os.path.splitext(fname)[0]

        if ext == ".pdf":
            print(f"[PDF] {full_path}")
            # Tabula-py (lattice)
            try:
                tables = tabula.read_pdf(full_path, pages="all", multiple_tables=True, lattice=True)
                for idx, df in enumerate(tables):
                    if not df.empty:
                        out_csv = os.path.join(out_folder, f"{base}_tabula_lattice_table{idx+1}.csv")
                        df.to_csv(out_csv, index=False)
            except Exception as e:
                print(f"   Tabula lattice ERROR: {e}")

            # Tabula-py (stream)
            try:
                tables = tabula.read_pdf(full_path, pages="all", multiple_tables=True, stream=True)
                for idx, df in enumerate(tables):
                    if not df.empty:
                        out_csv = os.path.join(out_folder, f"{base}_tabula_stream_table{idx+1}.csv")
                        df.to_csv(out_csv, index=False)
            except Exception as e:
                print(f"   Tabula stream ERROR: {e}")

            # Camelot (lattice)
            try:
                tables = camelot.read_pdf(full_path, pages="all", flavor="lattice")
                for idx, table in enumerate(tables):
                    df = table.df
                    out_csv = os.path.join(out_folder, f"{base}_camelot_lattice_table{idx+1}.csv")
                    df.to_csv(out_csv, index=False, header=False)
            except Exception as e:
                print(f"   Camelot lattice ERROR: {e}")

            # Camelot (stream)
            try:
                tables = camelot.read_pdf(full_path, pages="all", flavor="stream")
                for idx, table in enumerate(tables):
                    df = table.df
                    out_csv = os.path.join(out_folder, f"{base}_camelot_stream_table{idx+1}.csv")
                    df.to_csv(out_csv, index=False, header=False)
            except Exception as e:
                print(f"   Camelot stream ERROR: {e}")

            # pdfplumber (bonus: all tables on all pages, but structure may be poor)
            try:
                with pdfplumber.open(full_path) as pdf:
                    for page_num, page in enumerate(pdf.pages, 1):
                        tables = page.extract_tables()
                        for idx, table in enumerate(tables):
                            df = pd.DataFrame(table)
                            out_csv = os.path.join(out_folder, f"{base}_plumber_page{page_num}_table{idx+1}.csv")
                            df.to_csv(out_csv, index=False, header=False)
            except Exception as e:
                print(f"   pdfplumber ERROR: {e}")

        elif ext in [".xlsx", ".xls"]:
            print(f"[EXCEL] {full_path}")
            try:
                xl = pd.ExcelFile(full_path)
                for sheet in xl.sheet_names:
                    df = xl.parse(sheet)
                    safe_sheet = sheet.replace(" ", "_").replace("/", "_")
                    out_csv = os.path.join(out_folder, f"{base}_{safe_sheet}.csv")
                    df.to_csv(out_csv, index=False)
            except Exception as e:
                print(f"   Excel ERROR: {e}")

print("\nDONE! All PDFs and Excels processed into processed_data/kapital_bank/[...].\n")
print("For each PDF, check all *_table*.csv files and pick the most accurate for your needs.")