import os
import re
import time
import unidecode
import requests
from selenium.webdriver.common.by import By
import undetected_chromedriver as uc

BASE_URL = "https://xalqbank.az/az/ferdi/bank/bank-haqqinda-melumatlarin-aciqlanmasi/maliyye-gostericileri-tab?include=menu"
RAW_DATA_DIR = os.path.join("raw_data", "xalq_bank")
PROCESSED_DATA_DIR = os.path.join("processed_data", "xalq_bank")
os.makedirs(RAW_DATA_DIR, exist_ok=True)
os.makedirs(PROCESSED_DATA_DIR, exist_ok=True)

CORE_REPORTS = [
    "balance_sheet",
    "profit_and_loss",
    "capital_adequacy",
    "currency_risk",
    "credit_risk"
]

REPORT_TYPES = [
    ("Balans hesabatı", "balance_sheet"),
    ("Mənfəət və zərər haqqında hesabat", "profit_and_loss"),
    ("Bankın birinci və ikinci dərəcəli kapitalının məbləği və onun elementləri", "capital_adequacy"),
    ("Valyuta riski", "currency_risk"),
    ("Kreditlərin, o cümlədən, vaxtı keçmiş kreditlərin iqtisadi sektorlar üzrə bölgüsü", "portfolio_sector"),
    ("Kredit riski", "credit_risk"),
]

VALID_EXTENSIONS = [".pdf", ".xlsx", ".xls"]

def normalize(txt):
    txt = unidecode.unidecode(txt or "")
    txt = txt.lower()
    txt = re.sub(r"[\s\W_]+", " ", txt)
    txt = txt.strip()
    return txt

def get_year_period(text):
    norm = normalize(text)
    year_match = re.search(r"(\d{4})", norm)
    year = year_match.group(1) if year_match else ""
    q_match = re.search(r"(i{1,3}|iv)\s*r[uü]b", norm)
    if q_match:
        q_roman = q_match.group(1).upper()
        q_map = {"I": "Q1", "II": "Q2", "III": "Q3", "IV": "Q4"}
        period = q_map.get(q_roman, q_roman)
    else:
        period = "unknown"
    return year, period

def file_exists_pdf(report_type, yyyy, quarter):
    # Checks for PDF in RAW only
    subfolder = f"{yyyy}_{quarter}"
    fname = f"{report_type}_{yyyy}_{quarter}.pdf"
    folder = os.path.join(RAW_DATA_DIR, subfolder)
    return os.path.exists(os.path.join(folder, fname))

def file_exists_excel(report_type, yyyy, quarter):
    # Checks for xlsx/xls in PROCESSED only
    subfolder = f"{yyyy}_{quarter}"
    for ext in [".xlsx", ".xls"]:
        fname = f"{report_type}_{yyyy}_{quarter}{ext}"
        folder = os.path.join(PROCESSED_DATA_DIR, subfolder)
        if os.path.exists(os.path.join(folder, fname)):
            return True
    return False

def safe_click(driver, elem, header_offset=120):
    driver.execute_script(
        "window.scrollTo(0, arguments[0].getBoundingClientRect().top + window.scrollY - arguments[1]);",
        elem, header_offset
    )
    time.sleep(0.4)
    driver.execute_script("arguments[0].click();", elem)
    time.sleep(2.3)

def main():
    report = []
    total_downloaded = 0
    all_year_quarters = set()

    options = uc.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    driver = uc.Chrome(options=options)
    driver.get(BASE_URL)
    time.sleep(4)

    session = requests.Session()
    for cookie in driver.get_cookies():
        session.cookies.set(cookie['name'], cookie['value'])
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": BASE_URL
    }

    for az_title, en_name in REPORT_TYPES:
        print(f"\n[INFO] Scraping section: {az_title}")
        try:
            link_elem = driver.find_element(By.LINK_TEXT, az_title)
            safe_click(driver, link_elem, header_offset=120)
        except Exception as e:
            report.append(f"[MISSING_ON_SITE] {en_name}: cannot find/click section link ({e})")
            continue

        # Scrape all report links
        report_links = driver.find_elements(By.CSS_SELECTOR, "a.reports__item")
        print(f"  [DEBUG] Found {len(report_links)} report link(s)")
        for link in report_links:
            href = link.get_attribute("href")
            info_text = link.text.strip()
            if not href or not any(href.lower().endswith(ext) for ext in VALID_EXTENSIONS):
                continue
            year, quarter = get_year_period(info_text)
            if not year or quarter == "unknown" or not year.isdigit() or int(year) < 2020:
                continue
            ext = os.path.splitext(href.split('?')[0])[1].lower()
            subfolder = f"{year}_{quarter}"
            save_name = f"{en_name}_{year}_{quarter}{ext}"
            all_year_quarters.add((year, quarter))
            if ext == ".pdf":
                period_dir = os.path.join(RAW_DATA_DIR, subfolder)
                fpath = os.path.join(period_dir, save_name)
                if file_exists_pdf(en_name, year, quarter):
                    report.append(f"[SKIP] Already exists: {subfolder}/{save_name}")
                    continue
            elif ext in [".xlsx", ".xls"]:
                period_dir = os.path.join(PROCESSED_DATA_DIR, subfolder)
                fpath = os.path.join(period_dir, save_name)
                if file_exists_excel(en_name, year, quarter):
                    report.append(f"[SKIP] Already exists: {subfolder}/{save_name}")
                    continue
            else:
                continue
            os.makedirs(period_dir, exist_ok=True)
            try:
                print(f"    Downloading: {subfolder}/{save_name}")
                r = session.get(href, headers=headers, timeout=20)
                if (ext == ".pdf" and not r.content.startswith(b'%PDF-')) or (ext in [".xlsx", ".xls"] and r.content[:2] != b'PK'):
                    report.append(f"[SKIP_CORRUPT] {subfolder}/{save_name}")
                    continue
                with open(fpath, "wb") as out:
                    out.write(r.content)
                report.append(f"[OK] {subfolder}/{save_name}")
                total_downloaded += 1
            except Exception as e:
                report.append(f"[ERROR] {subfolder}/{save_name}: {e}")

        # Go BACK to menu page for next section
        driver.get(BASE_URL)
        time.sleep(2.3)

    print("\n=== FULL XALQ BANK REPORT ===")
    for line in report:
        print(line)

    # Summary of missing core reports, separate for PDF and Excel
    print("\n=== SUMMARY OF MISSING CORE REPORTS PER QUARTER ===")
    for year, quarter in sorted(all_year_quarters, reverse=True):
        missing_pdfs = [core for core in CORE_REPORTS if not file_exists_pdf(core, year, quarter)]
        missing_excels = [core for core in CORE_REPORTS if not file_exists_excel(core, year, quarter)]
        if missing_pdfs:
            print(f"{year}_{quarter}: missing PDFs: {missing_pdfs}")
        if missing_excels:
            print(f"{year}_{quarter}: missing Excels: {missing_excels}")

    print(f"\nDone.\nAll PDFs in raw_data/xalq_bank/<year>_<quarter>/, Excels in processed_data/xalq_bank/<year>_<quarter>/")
    print(f"Total files downloaded: {total_downloaded}")

    driver.quit()

if __name__ == "__main__":
    main()
