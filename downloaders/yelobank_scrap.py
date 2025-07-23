import os
import re
import time
import unidecode
import requests
from selenium.webdriver.common.by import By
import undetected_chromedriver as uc

BASE_URL = "https://www.yelo.az/en/about-bank/reports/quarter/"
RAW_DATA_DIR = os.path.join("raw_data", "yelobank")
PROCESSED_DATA_DIR = os.path.join("processed_data", "yelobank")
os.makedirs(RAW_DATA_DIR, exist_ok=True)
os.makedirs(PROCESSED_DATA_DIR, exist_ok=True)

CORE_REPORTS = [
    "balance_sheet",
    "profit_loss",
    "cash_flow",
    "credit_risk",
    "currency_risk",
    "interest_rate_risk",
    "liquidity_risk",
    "capital_adequacy",
    "capital_change"
]

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

VALID_EXTENSIONS = [".pdf", ".xlsx", ".xls"]

def normalize(txt):
    txt = unidecode.unidecode(txt or "")
    txt = txt.lower()
    txt = re.sub(r"[\s\W_]+", " ", txt)
    txt = txt.strip()
    return txt

def match_report_type(text):
    n = normalize(text)
    for k, v in STRICT_NAMES.items():
        if normalize(k) in n:
            return v
    return None

def get_year_period(text):
    # e.g. "IV quarter, 2024"
    m = re.match(r"(I{1,3}|IV)\s+quarter,\s*(20\d{2})", text, re.I)
    if not m: return None, None
    roman, year = m.group(1).upper(), m.group(2)
    q_map = {"I": "Q1", "II": "Q2", "III": "Q3", "IV": "Q4"}
    return year, q_map.get(roman, None)

def file_exists_pdf(report_type, yyyy, quarter):
    subfolder = f"{yyyy}_{quarter}"
    fname = f"{report_type}_{yyyy}_{quarter}.pdf"
    folder = os.path.join(RAW_DATA_DIR, subfolder)
    return os.path.exists(os.path.join(folder, fname))

def file_exists_excel(report_type, yyyy, quarter):
    subfolder = f"{yyyy}_{quarter}"
    for ext in [".xlsx", ".xls"]:
        fname = f"{report_type}_{yyyy}_{quarter}{ext}"
        folder = os.path.join(PROCESSED_DATA_DIR, subfolder)
        if os.path.exists(os.path.join(folder, fname)):
            return True
    return False

def main():
    report = []
    total_downloaded = 0
    all_year_quarters = set()

    options = uc.ChromeOptions()
    driver = uc.Chrome(options=options)
    driver.get(BASE_URL)
    time.sleep(2.7)

    session = requests.Session()
    for cookie in driver.get_cookies():
        session.cookies.set(cookie['name'], cookie['value'])
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": BASE_URL
    }

    h2s = driver.find_elements(By.CSS_SELECTOR, ".main_wrap > h2")
    year_items = driver.find_elements(By.CSS_SELECTOR, ".main_wrap > .year_item")
    if not h2s or not year_items or len(h2s) != len(year_items):
        print("[ERROR] Could not match quarter titles with report blocks")
        driver.quit()
        return

    for idx, h2 in enumerate(h2s):
        quarter_text = h2.text.strip()
        yyyy, quarter = get_year_period(quarter_text)
        if not yyyy or not quarter:
            continue
        if int(yyyy) < 2020:
            continue
        period = f"{yyyy}_{quarter}"
        all_year_quarters.add((yyyy, quarter))
        docs_block = year_items[idx].find_element(By.CSS_SELECTOR, ".list_of_documents")
        lis = docs_block.find_elements(By.TAG_NAME, "li")
        for li in lis:
            try:
                a = li.find_element(By.TAG_NAME, "a")
                href = a.get_attribute("href")
                desc_el = a.find_element(By.CSS_SELECTOR, ".file_desc b")
                b_text = desc_el.text.strip()
                report_type = match_report_type(b_text)
                if not report_type or report_type not in CORE_REPORTS:
                    continue
                ext = os.path.splitext(href.split('?')[0])[1].lower()
                if ext == ".pdf":
                    period_dir = os.path.join(RAW_DATA_DIR, period)
                    fname = f"{report_type}_{yyyy}_{quarter}.pdf"
                    fpath = os.path.join(period_dir, fname)
                    if file_exists_pdf(report_type, yyyy, quarter):
                        report.append(f"[SKIP] Already exists: {period}/{fname}")
                        continue
                elif ext in [".xlsx", ".xls"]:
                    period_dir = os.path.join(PROCESSED_DATA_DIR, period)
                    fname = f"{report_type}_{yyyy}_{quarter}{ext}"
                    fpath = os.path.join(period_dir, fname)
                    if file_exists_excel(report_type, yyyy, quarter):
                        report.append(f"[SKIP] Already exists: {period}/{fname}")
                        continue
                else:
                    continue
                os.makedirs(period_dir, exist_ok=True)
                print(f"    Downloading: {period}/{fname}")
                r = session.get(href, headers=headers, timeout=20)
                if (ext == ".pdf" and not r.content.startswith(b'%PDF-')) or (ext in [".xlsx", ".xls"] and r.content[:2] != b'PK'):
                    report.append(f"[SKIP_CORRUPT] {period}/{fname}")
                    continue
                with open(fpath, "wb") as out:
                    out.write(r.content)
                report.append(f"[OK] {period}/{fname}")
                total_downloaded += 1
            except Exception as e:
                report.append(f"[ERROR] {period}/{fname}: {e}")

    print("\n=== YELOBANK FULL REPORT ===")
    for line in report:
        print(line)

    print("\n=== SUMMARY OF MISSING CORE REPORTS PER QUARTER ===")
    for yyyy, quarter in sorted(all_year_quarters, reverse=True):
        miss_pdf = [core for core in CORE_REPORTS if not file_exists_pdf(core, yyyy, quarter)]
        miss_xls = [core for core in CORE_REPORTS if not file_exists_excel(core, yyyy, quarter)]
        if miss_pdf:
            print(f"{yyyy}_{quarter}: missing PDFs: {miss_pdf}")
        if miss_xls:
            print(f"{yyyy}_{quarter}: missing Excels: {miss_xls}")

    print(f"\nDone.\nAll PDFs in raw_data/yelobank/<year>_<quarter>/, Excels in processed_data/yelobank/<year>_<quarter>/")
    print(f"Total files downloaded: {total_downloaded}")

    driver.quit()

if __name__ == "__main__":
    main()
