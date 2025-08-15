import os
import re
import requests
from collections import defaultdict
from bs4 import BeautifulSoup

BASE_URL = "https://www.bankrespublika.az/az/reportsnew"
PROCESSED_ROOT = os.path.join("processed_data", "bank_respublika")
os.makedirs(PROCESSED_ROOT, exist_ok=True)

REPORT_MAP = {
    "Balans hesabatı": "balance_sheet",
    "Kapitalın strukturu vә adekvatlığı barәdә mәlumat": "capital_adequacy",
    "Mənfəət və zərər haqqında hesabat": "profit_loss",
}

RISK_MAP = {
    "Kredit riski": "credit_risk",
    "Valyuta riski": "currency_risk",
}

EXPECTED_ORDER = [
    "balance_sheet", "profit_loss", "capital_adequacy",
    "credit_risk", "currency_risk",
]

QUARTER_MAP = {
    "I Rüb": "Q1", "II Rüb": "Q2", "III Rüb": "Q3", "IV Rüb": "Q4",
    "Rüb I": "Q1", "Rüb II": "Q2", "Rüb III": "Q3", "Rüb IV": "Q4"
}

def file_exists_anywhere(report_type, year, quarter):
    period = f"{year}_{quarter}"
    fname_prefix = f"{report_type}_{period}"
    for dirpath, _, files in os.walk(PROCESSED_ROOT):
        for fname in files:
            if fname.startswith(fname_prefix) and fname.endswith((".xlsx", ".xls")):
                return True
    return False

def get_soup():
    r = requests.get(BASE_URL, timeout=20)
    r.raise_for_status()
    return BeautifulSoup(r.content, "html.parser")

def extract_main_reports(soup, per_quarter_status):
    tds = soup.find_all("td")
    for td in tds:
        header = td.find("p", {"style": False})
        if not header or not header.text.strip():
            continue
        report_type = header.get_text(strip=True)
        en_name = REPORT_MAP.get(report_type)
        if not en_name:
            continue

        year = None
        for p in td.find_all("p"):
            txt = p.get_text(strip=True)
            m_year = re.match(r"(20\d{2})$", txt)
            if m_year:
                year = m_year.group(1)
                continue
            if not year or int(year) < 2020:
                continue
            links = p.find_all("a")
            for a in links:
                rub = a.get_text(strip=True)
                q = QUARTER_MAP.get(rub)
                if not q:
                    continue
                period = f"{year}_{q}"
                fname = f"{en_name}_{period}.xlsx"
                period_dir = os.path.join(PROCESSED_ROOT, period)
                os.makedirs(period_dir, exist_ok=True)
                dst = os.path.join(period_dir, fname)
                if file_exists_anywhere(en_name, year, q):
                    per_quarter_status[period][en_name] = f"[SKIP] Already exists: {period}/{fname}"
                    continue
                href = a.get("href")
                if not href or not href.endswith((".xlsx", ".xls")):
                    continue
                url = href if href.startswith("http") else f"https://www.bankrespublika.az{href}"
                print(f"    Downloading: {period}/{fname}")
                try:
                    r = requests.get(url, timeout=30)
                    if not r.ok or not r.content[:2] == b'PK':
                        per_quarter_status[period][en_name] = f"[SKIP_CORRUPT] {period}/{fname}"
                        continue
                    with open(dst, "wb") as out:
                        out.write(r.content)
                    per_quarter_status[period][en_name] = f"[OK] {period}/{fname}"
                except Exception as e:
                    per_quarter_status[period][en_name] = f"[ERROR] {period}/{fname}: {e}"

def extract_risk_reports(soup, per_quarter_status):
    risk_blocks = []
    for risk_az, risk_en in RISK_MAP.items():
        for p in soup.find_all("p"):
            if risk_az in p.get_text():
                risk_blocks.append((risk_az, risk_en, p))

    for risk_az, risk_en, p in risk_blocks:
        prev = p.find_previous_sibling("p")
        year = None
        while prev:
            prev_txt = prev.get_text(strip=True)
            if re.match(r"^20\d{2}$", prev_txt):
                year = prev_txt
                break
            prev = prev.find_previous_sibling("p")
        if not year or int(year) < 2020:
            continue

        links = p.find_all("a")
        for a in links:
            rub = a.get_text(strip=True)
            q = QUARTER_MAP.get(rub)
            if not q:
                continue
            period = f"{year}_{q}"
            fname = f"{risk_en}_{period}.xlsx"
            period_dir = os.path.join(PROCESSED_ROOT, period)
            os.makedirs(period_dir, exist_ok=True)
            dst = os.path.join(period_dir, fname)
            if file_exists_anywhere(risk_en, year, q):
                per_quarter_status[period][risk_en] = f"[SKIP] Already exists: {period}/{fname}"
                continue
            href = a.get("href")
            if not href or not href.endswith((".xlsx", ".xls")):
                continue
            url = href if href.startswith("http") else f"https://www.bankrespublika.az{href}"
            print(f"    Downloading: {period}/{fname}")
            try:
                r = requests.get(url, timeout=30)
                if not r.ok or not r.content[:2] == b'PK':
                    per_quarter_status[period][risk_en] = f"[SKIP_CORRUPT] {period}/{fname}"
                    continue
                with open(dst, "wb") as out:
                    out.write(r.content)
                per_quarter_status[period][risk_en] = f"[OK] {period}/{fname}"
            except Exception as e:
                per_quarter_status[period][risk_en] = f"[ERROR] {period}/{fname}: {e}"

def main():
    soup = get_soup()
    per_quarter_status = defaultdict(dict)

    extract_main_reports(soup, per_quarter_status)
    extract_risk_reports(soup, per_quarter_status)

    print("\n=== BANK RESPUBLIKA REPORT ===")
    for qid, stats in sorted(per_quarter_status.items()):
        print(f"\n== {qid} ==")
        missing = []
        for rtype in EXPECTED_ORDER:
            status = stats.get(rtype, "[MISSING]")
            print(f"{rtype}: {status}")
            if status.startswith("[MISSING]"):
                missing.append(rtype)
        if missing:
            print(f">>> MISSING in {qid}: {', '.join(missing)}")
        else:
            print(f"All expected 9 reports found for {qid}")

    print("\n=== SUMMARY OF MISSING REPORTS ===")
    any_missing = False
    for qid, stats in sorted(per_quarter_status.items()):
        missing = [rtype for rtype in EXPECTED_ORDER if stats.get(rtype, "[MISSING]").startswith("[MISSING]")]
        if missing:
            print(f"{qid}: {missing}")
            any_missing = True
    if not any_missing:
        print("ALL QUARTERS COMPLETE (no missing reports)")

    print("\nSUMMARY REPORT")
    print(f"Total quarters checked: {len(per_quarter_status)}")
    print("All Excel files arranged in processed_data/bank_respublika/<period>/")
    print("Done.")

if __name__ == "__main__":
    main()
