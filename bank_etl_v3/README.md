# Bank ETL v3 (Azeri raw → Master for Power BI)

**Master schema (exact order):**
Bank, Period, Indicator table, Element, Sub-element, AZN, FS Line, Item, Currency,
Amount vs Share, Total, 31-60 days, 61-90 days, 91+ days,
31-60 days_share%inLP, 61-90 days_share%inLP, 91+ days_share%inLP

## Folder structure
raw/
  balance_sheet/
  profit_and_loss/
  capital_adequacy/
  credit_risk/
  currency_risk/
config/
out/

## Run
```bash
pip install -r requirements.txt
python -m etl.etl --raw ./raw --out ./out --config ./config --master ./out/master.xlsx
```
Outputs:
- `out/master.csv` (+ `out/master.xlsx` if --master is given)
- `out/<report_type>.csv` (one per type)
- `out/rejects.csv` (anything unmapped)
- `out/processed_log.csv` (file hashes to skip repeats)

### What’s special
- **Content-driven Balance Sheet**: matches Azeri line text anywhere in the row (doesn’t rely on column positions or Element codes). Picks **current-period** column (`Hesabat/Cari/Current`) and ignores year-end (`Ötən/Previous`).
- **Filename fallback**: if `Bank` or `Period` missing, they’re parsed from the filename (aliases + Q patterns).
