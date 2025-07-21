import os
import re
import time
import requests
from collections import defaultdict
from selenium.webdriver.common.by import By
import undetected_chromedriver as uc

BASE_URL = "https://www.yelo.az/en/about-bank/reports/quarter/"
RAW_DATA_DIR = os.path.join("raw_data", "yelobank")
os.makedirs(RAW_DATA_DIR, exist_ok=True)

STRICT_NAMES = {
    "Statement of financial position": "balance_sheet",
    "Balance sheet": "balance_sheet",
    "Profit and loss statement": "profit_loss",
    "Cash flow statement": "cash_flow",
    "Credit risk": "credit_risk",
    "Currency risk": "currency_risk",
    "Interest rate risk": "interest_rate_risk",
    "Liquidity risk": "liquidity_risk",
    "Adequacy of capital": "capital_adequacy",
    "Report on changes in capital structure": "capital_change",
    "Changes in equity": "capital_change",
}

EXPECTED_ORDER = [
    "balance_sheet", "profit_loss", "cash_flow", "credit_risk", "currency_risk",
    "interest_rate_risk", "liquidity_risk", "capital_adequacy", "capital_change"
]

def normalize(text):
    text = re.sub(r"\s+", " ", text or "").strip().lower()
    return text

def match_report_type(b_text):
    b_text = normalize(b_text)
    for label, fname in STRICT_NAMES.items():
        if normalize(label) in b_text:
            return fname
    return None

def parse_quarter_and_year(quarter_text):
    m = re.match(r"(I{1,3}|IV)\s+quarter,\s*(20\d{2})", quarter_text, re.I)
    if not m: return None, None
    roman, year = m.group(1).upper(), m.group(2)
    roman_map = {"I":"Q1","II":"Q2","III":"Q3","IV":"Q4"}
    return year, roman_map.get(roman, None)

def main():
    options = uc.ChromeOptions()
    driver = uc.Chrome(options=options)
    driver.get(BASE_URL)
    time.sleep(2.7)
    session = requests.Session()
    for cookie in driver.get_cookies():
        session.cookies.set(cookie['name'], cookie['value'])
    headers = {"User-Agent": "Mozilla/5.0", "Referer": BASE_URL}

    report = []
    per_quarter_status = defaultdict(dict)
    total_downloaded = 0

    # 1. Find all quarter <h2> elements
    h2s = driver.find_elements(By.CSS_SELECTOR, ".main_wrap > h2")
    year_items = driver.find_elements(By.CSS_SELECTOR, ".main_wrap > .year_item")

    if not h2s or not year_items or len(h2s) != len(year_items):
        print("[ERROR] Could not match quarter titles with report blocks")
        driver.quit()
        return

    for idx, h2 in enumerate(h2s):
        quarter_text = h2.text.strip()
        yyyy, qq = parse_quarter_and_year(quarter_text)
        if not yyyy or not qq:
            continue
        if int(yyyy) < 2020:
            continue
        quarter_id = f"{yyyy}_{qq}"
        print(f"\n[INFO] Processing {quarter_text} ({quarter_id})")
        docs_block = year_items[idx].find_element(By.CSS_SELECTOR, ".list_of_documents")
        lis = docs_block.find_elements(By.TAG_NAME, "li")
        per_quarter_status[quarter_id] = {k: "[MISSING]" for k in EXPECTED_ORDER}
        for li in lis:
            try:
                a = li.find_element(By.TAG_NAME, "a")
                href = a.get_attribute("href")
                desc_el = a.find_element(By.CSS_SELECTOR, ".file_desc b")
                b_text = desc_el.text.strip()
                report_type = match_report_type(b_text)
                if not report_type:
                    continue
                ext = os.path.splitext(href.split('?')[0])[1].lower()
                fname = f"{report_type}_{quarter_id}{ext}"
                fpath = os.path.join(RAW_DATA_DIR, fname)
                if os.path.exists(fpath):
                    per_quarter_status[quarter_id][report_type] = "[OK] already exists"
                    continue
                url = href if href.startswith("http") else "https://www.yelo.az" + href
                print(f"    Downloading: {fname}")
                r = session.get(url, headers=headers, timeout=30)
                if ext == ".pdf" and not r.content.startswith(b"%PDF-"):
                    per_quarter_status[quarter_id][report_type] = "[SKIP_CORRUPT]"
                    continue
                with open(fpath, "wb") as out:
                    out.write(r.content)
                per_quarter_status[quarter_id][report_type] = "[OK]"
                total_downloaded += 1
            except Exception as e:
                report.append(f"[ERROR] Download failed: {e}")

    print("\n=== YELOBANK REPORT ===")
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
    print(f"Total files downloaded: {total_downloaded}")
    print(f"Total quarters checked: {len(per_quarter_status)}")
    driver.quit()

if __name__ == "__main__":
    main()
