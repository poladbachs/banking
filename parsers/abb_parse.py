import os
import shutil
import re
import pandas as pd
import camelot
import pdfplumber

RAW_ROOT = "raw_data/abb_bank"
PROCESSED_ROOT = "processed_data/abb_bank_excel"
FAILED_LOG = open("failed_extractions_abb.txt", "a")

def year_from_quarter_year(quarter_year):
    match = re.match(r"(\d{4})_Q\d", quarter_year)
    return int(match.group(1)) if match else None

def save_excels(dfs, excel_path):
    if not dfs:
        return 0
    with pd.ExcelWriter(excel_path) as writer:
        for i, df in enumerate(dfs):
            df.to_excel(writer, sheet_name=f"Table_{i+1}", index=False)
    return len(dfs)

for root, dirs, files in os.walk(RAW_ROOT):
    rel_path = os.path.relpath(root, RAW_ROOT)
    out_folder = os.path.join(PROCESSED_ROOT, rel_path)
    os.makedirs(out_folder, exist_ok=True)
    quarter_year = rel_path
    year = year_from_quarter_year(quarter_year)
    for fname in files:
        ext = os.path.splitext(fname)[1].lower()
        base = os.path.splitext(fname)[0]
        in_path = os.path.join(root, fname)
        out_xlsx = os.path.join(out_folder, base + ".xlsx")
        report_type = base.lower()
        # Excel: just copy
        if ext in [".xlsx", ".xls"]:
            print(f"[EXCEL] Copying {in_path} -> {out_xlsx}")
            shutil.copy2(in_path, out_xlsx)
            FAILED_LOG.write(f"[EXCEL] Copied {in_path} -> {out_xlsx}\n")
        # PDF: extract using best available method per report/year
        elif ext == ".pdf":
            if "adequacy" in report_type:
                tables_lattice = camelot.read_pdf(in_path, pages="all", flavor="lattice")
                dfs_lattice = [t.df for t in tables_lattice if not t.df.empty]
                n_tables = save_excels(dfs_lattice, out_xlsx)
                print(f"[PDF] {in_path} (Camelot Lattice, {n_tables} tables) -> {out_xlsx}")
                FAILED_LOG.write(f"[PDF] Camelot Lattice extracted {n_tables} tables for {in_path}\n")
                if n_tables < 2:
                    tables_stream = camelot.read_pdf(in_path, pages="all", flavor="stream")
                    dfs_stream = [t.df for t in tables_stream if not t.df.empty]
                    n_tables_stream = save_excels(dfs_stream, out_xlsx)
                    print(f"[PDF] {in_path} (Camelot Stream fallback, {n_tables_stream} tables) -> {out_xlsx}")
                    FAILED_LOG.write(f"[PDF] Camelot Stream fallback extracted {n_tables_stream} tables for {in_path}\n")
            else:
                tables = camelot.read_pdf(in_path, pages="all", flavor="lattice")
                dfs = [t.df for t in tables if not t.df.empty]
                n_tables = save_excels(dfs, out_xlsx)
                print(f"[PDF] {in_path} (Camelot Lattice, {n_tables} tables) -> {out_xlsx}")
                FAILED_LOG.write(f"[PDF] Camelot Lattice extracted {n_tables} tables for {in_path}\n")
                if n_tables == 0:
                    tables = camelot.read_pdf(in_path, pages="all", flavor="stream")
                    dfs = [t.df for t in tables if not t.df.empty]
                    n_tables_stream = save_excels(dfs, out_xlsx)
                    print(f"[PDF] {in_path} (Camelot Stream fallback, {n_tables_stream} tables) -> {out_xlsx}")
                    FAILED_LOG.write(f"[PDF] Camelot Stream fallback extracted {n_tables_stream} tables for {in_path}\n")

FAILED_LOG.close()
print("\nDONE! All Excels copied, all PDFs extracted, basic technical logs saved for debugging.\n")
