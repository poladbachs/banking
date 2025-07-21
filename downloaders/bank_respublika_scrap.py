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
    "Kapital strukturunda dəyişikliklər haqqında hesabat": "capital_change",
    "Pul vəsaitlərinin hərəkəti barədə hesabat": "cash_flow",
}

RISK_MAP = {
    "Kredit riski": "credit_risk",
    "Likvidlik riski": "liquidity_risk",
    "Valyuta riski": "currency_risk",
    "Faiz riski": "interest_rate_risk",
}

EXPECTED_ORDER = [
    "balance_sheet", "profit_loss", "cash_flow", "capital_change", "capital_adequacy",
    "credit_risk", "liquidity_risk", "currency_risk", "interest_rate_risk"
]

QUARTER_MAP = {
    "I Rüb": "Q1", "II Rüb": "Q2", "III Rüb": "Q3", "IV Rüb": "Q4",
    "Rüb I": "Q1", "Rüb II": "Q2", "Rüb III": "Q3", "Rüb IV": "Q4"
}
QUARTER_PATTERN = r"(I{1,3}|IV)\s*Rüb"

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
                quarter_id = f"{year}_{q}"
                href = a.get("href")
                if not href or not href.endswith((".xlsx", ".xls")):
                    continue
                url = href if href.startswith("http") else f"https://www.bankrespublika.az{href}"
                fname = f"{en_name}_{quarter_id}.xlsx"
                period_dir = os.path.join(PROCESSED_ROOT, quarter_id)
                os.makedirs(period_dir, exist_ok=True)
                dst = os.path.join(period_dir, fname)
                if os.path.exists(dst):
                    per_quarter_status[quarter_id][en_name] = "[OK] already exists"
                    continue
                print(f"    Downloading: {fname}")
                try:
                    r = requests.get(url, timeout=30)
                    if not r.ok or not r.content[:2] == b'PK':
                        per_quarter_status[quarter_id][en_name] = "[SKIP_CORRUPT]"
                        continue
                    with open(dst, "wb") as out:
                        out.write(r.content)
                    per_quarter_status[quarter_id][en_name] = "[OK]"
                except Exception as e:
                    per_quarter_status[quarter_id][en_name] = f"[ERROR] {e}"

def extract_risk_reports(soup, per_quarter_status):
    # Find Əlavə hesabatlar section
    # For each risk, locate p with risk name, then find year, then links
    risk_blocks = []
    for risk_az, risk_en in RISK_MAP.items():
        for p in soup.find_all("p"):
            if risk_az in p.get_text():
                risk_blocks.append((risk_az, risk_en, p))

    for risk_az, risk_en, p in risk_blocks:
        # Go upwards to find the year
        prev = p.find_previous_sibling("p")
        year = None
        # Find year block
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
            quarter_id = f"{year}_{q}"
            href = a.get("href")
            if not href or not href.endswith((".xlsx", ".xls")):
                continue
            url = href if href.startswith("http") else f"https://www.bankrespublika.az{href}"
            fname = f"{risk_en}_{quarter_id}.xlsx"
            period_dir = os.path.join(PROCESSED_ROOT, quarter_id)
            os.makedirs(period_dir, exist_ok=True)
            dst = os.path.join(period_dir, fname)
            if os.path.exists(dst):
                per_quarter_status[quarter_id][risk_en] = "[OK] already exists"
                continue
            print(f"    Downloading: {fname}")
            try:
                r = requests.get(url, timeout=30)
                if not r.ok or not r.content[:2] == b'PK':
                    per_quarter_status[quarter_id][risk_en] = "[SKIP_CORRUPT]"
                    continue
                with open(dst, "wb") as out:
                    out.write(r.content)
                per_quarter_status[quarter_id][risk_en] = "[OK]"
            except Exception as e:
                per_quarter_status[quarter_id][risk_en] = f"[ERROR] {e}"

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

    # --- Compact missing summary ---
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
