import os
import re
import time
import requests
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from collections import defaultdict
from urllib.parse import unquote, urlparse

BASE_URL = "https://www.kapitalbank.az/reports"
RAW_DATA_DIR = os.path.join("raw_data", "kapital_bank")
PROCESSED_DIR = os.path.join("processed_data", "kapital_bank")
os.makedirs(RAW_DATA_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)

CORE_6 = {
    "balance_sheet":     [["balans", "hesabat"]],
    "capital_adequacy":  [["kapital", "adekvat"]],
    "profit_loss":       [["mənfəət", "zərər"]],
    "other_general_info":[["digər", "ümumi", "məlumat"]],
}

def clean_for_header(val):
    if isinstance(val, str):
        return val.encode("latin-1", "ignore").decode("latin-1")
    return val

def matches_keywords(text, keyword_sets):
    t = text.lower()
    for keywords in keyword_sets:
        if all(kw in t for kw in keywords):
            return True
    return False

def get_en_report_type(text):
    for k, keywords in CORE_6.items():
        if matches_keywords(text, keywords):
            return k
    return None

def extract_quarter(label):
    match = re.search(r'([IV]+)\s*rüb[^\d]*(\d{4})', label, re.I)
    if not match:
        return None, None
    roman, year = match.group(1).upper(), match.group(2)
    q_map = {"I": "Q1", "II": "Q2", "III": "Q3", "IV": "Q4"}
    return q_map.get(roman), year

def is_real_excel(content):
    return content[:2] == b'PK'

def is_real_pdf(content):
    return content[:5] == b'%PDF-'

def file_exists_in_period(period_dir, fname):
    return os.path.exists(os.path.join(period_dir, fname))

def main():
    options = uc.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--no-sandbox")
    driver = uc.Chrome(options=options)
    driver.get(BASE_URL)
    time.sleep(3)

    # Accept cookies if present
    try:
        accept_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Accept')]")
        accept_btn.click()
    except Exception:
        pass
    time.sleep(2)

    # Prepare requests session with sanitized cookies
    session = requests.Session()
    for cookie in driver.get_cookies():
        session.cookies.set(cookie['name'], clean_for_header(cookie['value']))

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": BASE_URL
    }

    accordion_titles = driver.find_elements(By.CSS_SELECTOR, ".accordion--pls--title")
    per_quarter_files = defaultdict(set)

    for title_elem in accordion_titles:
        quarter_title = title_elem.text.strip()
        quarter, year = extract_quarter(quarter_title)
        if not quarter or not year or int(year) < 2020:
            continue
        period = f"{year}_{quarter}"
        period_dir_raw = os.path.join(RAW_DATA_DIR, period)
        period_dir_proc = os.path.join(PROCESSED_DIR, period)
        os.makedirs(period_dir_raw, exist_ok=True)
        os.makedirs(period_dir_proc, exist_ok=True)

        # Expand accordion
        try:
            driver.execute_script("arguments[0].scrollIntoView();", title_elem)
            ActionChains(driver).move_to_element(title_elem).perform()
            if not title_elem.get_attribute("aria-expanded") or title_elem.get_attribute("aria-expanded") == "false":
                title_elem.click()
            time.sleep(1.0)
        except Exception:
            continue

        # Find links
        panel_wrap = title_elem.find_element(By.XPATH, "./ancestor::div[contains(@class,'border-bottom-2')]")
        links = panel_wrap.find_elements(By.XPATH, ".//a[@href]")
        for a in links:
            href = a.get_attribute("href")
            text = a.text.strip()
            ext = os.path.splitext(href.split("?")[0])[-1].lower().replace(".", "")
            if not href or ext not in ["pdf", "xlsx", "xls"]:
                continue

            # Try to match report type by link text first, then by filename
            en_name = get_en_report_type(text)
            if not en_name:
                url_fname = unquote(os.path.basename(urlparse(href).path)).replace("_", " ").lower()
                en_name = get_en_report_type(url_fname)
            if not en_name:
                continue

            fname = f"{en_name}_{period}.{ext}"
            if ext in ["xlsx", "xls"]:
                fpath = os.path.join(period_dir_proc, fname)
                if file_exists_in_period(period_dir_proc, fname):
                    print(f"[SKIP] Already exists: {period}/{fname}")
                    per_quarter_files[period].add(en_name)
                    continue
                print(f"Downloading: {period}/{fname}")
                r = session.get(href, headers=headers, timeout=20)
                if not is_real_excel(r.content):
                    print(f"  [!] Not a real Excel (skipped): {href}")
                    continue
                with open(fpath, "wb") as out:
                    out.write(r.content)
                per_quarter_files[period].add(en_name)
            elif ext == "pdf":
                fpath = os.path.join(period_dir_raw, fname)
                if file_exists_in_period(period_dir_raw, fname):
                    print(f"[SKIP] Already exists: {period}/{fname}")
                    per_quarter_files[period].add(en_name)
                    continue
                print(f"[PDF] {period}/{fname}")
                r = session.get(href, headers=headers, timeout=20)
                if not is_real_pdf(r.content):
                    print(f"  [!] Not a real PDF (skipped): {href}")
                    continue
                with open(fpath, "wb") as out:
                    out.write(r.content)
                per_quarter_files[period].add(en_name)
        time.sleep(0.5)
    driver.quit()

    # -- Rebuild per_quarter_files from all files present on disk (future-proof, accurate) --
    per_quarter_files_disk = defaultdict(set)
    for dirpath, _, files in os.walk(PROCESSED_DIR):
        for fname in files:
            m = re.match(r"([a-z_]+)_(20\d{2}_Q[1-4]|20\d{2}_12m)\.(xlsx|xls)", fname)
            if m:
                report_type, period, ext = m.groups()
                per_quarter_files_disk[period].add(report_type)
    for dirpath, _, files in os.walk(RAW_DATA_DIR):
        for fname in files:
            m = re.match(r"([a-z_]+)_(20\d{2}_Q[1-4]|20\d{2}_12m)\.pdf", fname)
            if m:
                report_type, period = m.groups()
                per_quarter_files_disk[period].add(report_type)

    print("\n=== SUMMARY OF MISSING REPORTS PER QUARTER ===")
    core_keys = list(CORE_6.keys())
    for period in sorted(per_quarter_files_disk.keys()):
        got = per_quarter_files_disk[period]
        miss = [k for k in core_keys if k not in got]
        if miss:
            print(f"{period}: missing {miss}")
    print("Done.\nAll Excels in processed_data/kapital_bank/<year>_<quarter>/, all PDFs in raw_data/kapital_bank/<year>_<quarter>/")

if __name__ == "__main__":
    main()