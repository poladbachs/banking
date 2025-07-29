import os
import time
import re
import requests
import unidecode
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By

BASE_URL = "https://www.accessbank.az/az/our-bank/in-figures/"
RAW_DATA_DIR = os.path.join("raw_data", "access_bank")
PROCESSED_DATA_DIR = os.path.join("processed_data", "access_bank")
os.makedirs(RAW_DATA_DIR, exist_ok=True)
os.makedirs(PROCESSED_DATA_DIR, exist_ok=True)

CORE_REPORTS = [
    "balance",
    "profit_and_loss",
    "cash_flow",
    "capital_adequacy",
    "capital_change",
    "credit_risk",
    "liquidity_risk",
    "interest_rate_risk",
    "currency_risk",
    "material_risks"
]

SECTION_MAP = {
    "Kapital adekvatlığı": "capital_adequacy",
    "Maliyyə vəziyyəti haqqında hesabat": "balance",
    "Mənfəət və zərər hesabatı": "profit_and_loss",
    "Kapital strukturunda dəyişikliklər haqqında hesabat": "capital_change",
    "Pul hərəkəti haqqında hesabat": "cash_flow",
}
RISK_REPORTS_AZ_TO_EN = {
    "Faiz riski": "interest_rate_risk",
    "Likvidlik riski": "liquidity_risk",
    "Kredit riski": "credit_risk",
    "Valyuta riski": "currency_risk",
    "Əhəmiyyətli risklərin idarə edilməsi": "material_risks"
}
VALID_EXTENSIONS = [".pdf", ".xlsx", ".xls"]

def get_year_quarter(text):
    m = re.search(r"(\d{2})\.(\d{2})\.(20\d{2})", text)
    if not m:
        return None, None
    mm = m.group(2)
    yyyy = m.group(3)
    q_map = {"03": "Q1", "06": "Q2", "09": "Q3", "12": "Q4"}
    return yyyy, q_map.get(mm)

def file_exists(folder, report_type, yyyy, quarter, ext_list):
    subfolder = f"{yyyy}_{quarter}"
    dirpath = os.path.join(folder, subfolder)
    if not os.path.isdir(dirpath):
        return False
    for ext in ext_list:
        fname = f"{report_type}_{yyyy}_{quarter}{ext}"
        if fname in os.listdir(dirpath):
            return True
    return False

def safe_click(driver, elem, header_offset=120):
    driver.execute_script(
        "window.scrollTo(0, arguments[0].getBoundingClientRect().top + window.scrollY - arguments[1]);",
        elem, header_offset
    )
    time.sleep(0.3)
    driver.execute_script("arguments[0].click();", elem)
    time.sleep(1.2)

def scroll_inner_panel_until_loaded(panel):
    last_html = ""
    for _ in range(30):
        driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", panel)
        time.sleep(1.1)
        new_html = panel.get_attribute('innerHTML')
        if new_html == last_html:
            break
        last_html = new_html

def main():
    report = []
    total_downloaded = 0
    available_year_quarters = set()

    options = uc.ChromeOptions()
    driver = uc.Chrome(options=options)
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    driver.get(BASE_URL)
    time.sleep(4)

    session = requests.Session()
    for cookie in driver.get_cookies():
        session.cookies.set(cookie['name'], cookie['value'])
    headers = {"User-Agent": "Mozilla/5.0", "Referer": BASE_URL}

    # 1. Download all core (non-risk) files
    for az_title, section_en in SECTION_MAP.items():
        try:
            qlink = driver.find_element(By.XPATH, f"//div[contains(@class, 'faq__question') and contains(., '{az_title}')]")
            safe_click(driver, qlink)
            time.sleep(1.0)
            doc_blocks = driver.find_elements(By.CSS_SELECTOR, "div.faq__document-group-wr")
            for block in doc_blocks:
                try:
                    year_el = block.find_element(By.CSS_SELECTOR, "b.faq__answer__subtitle")
                    block_year = year_el.text.strip()
                    if not (block_year.isdigit() and int(block_year) >= 2020):
                        continue
                except Exception:
                    continue
                doc_links = block.find_elements(By.CSS_SELECTOR, "a.link_document")
                for link in doc_links:
                    href = link.get_attribute("href")
                    label = link.text.strip()
                    ext = os.path.splitext(href.split('?')[0])[1].lower()
                    if not href or ext not in VALID_EXTENSIONS:
                        continue
                    yyyy, quarter = get_year_quarter(label)
                    if not yyyy or not quarter:
                        continue
                    available_year_quarters.add((yyyy, quarter))
                    report_type = section_en
                    save_name = f"{report_type}_{yyyy}_{quarter}{ext}"
                    subfolder = f"{yyyy}_{quarter}"
                    period_dir = os.path.join(RAW_DATA_DIR if ext == ".pdf" else PROCESSED_DATA_DIR, subfolder)
                    os.makedirs(period_dir, exist_ok=True)
                    fpath = os.path.join(period_dir, save_name)
                    # No cross-folder check! Just check in the relevant folder
                    if ext == ".pdf" and file_exists(RAW_DATA_DIR, report_type, yyyy, quarter, [".pdf"]):
                        report.append(f"[SKIP] Already exists: {subfolder}/{save_name}")
                        continue
                    if ext in [".xlsx", ".xls"] and file_exists(PROCESSED_DATA_DIR, report_type, yyyy, quarter, [".xlsx", ".xls"]):
                        report.append(f"[SKIP] Already exists: {subfolder}/{save_name}")
                        continue
                    url = href if href.startswith("http") else "https://www.accessbank.az" + href
                    print(f"    Downloading: {subfolder}/{save_name}")
                    try:
                        r = session.get(url, headers=headers, timeout=25)
                        if ext == ".pdf" and not r.content.startswith(b'%PDF-'):
                            report.append(f"[SKIP_CORRUPT] {subfolder}/{save_name}")
                            continue
                        if ext in [".xlsx", ".xls"] and r.content[:2] != b'PK':
                            report.append(f"[SKIP_CORRUPT] {subfolder}/{save_name}")
                            continue
                        with open(fpath, "wb") as out:
                            out.write(r.content)
                        report.append(f"[OK] {subfolder}/{save_name}")
                        total_downloaded += 1
                    except Exception as e:
                        report.append(f"[ERROR] {subfolder}/{save_name}: {e}")
        except Exception as e:
            report.append(f"[MISSING_ON_SITE] {section_en}: {e}")

    # 2. Download ALL risk reports by scrolling the right panel!
    try:
        risk_qlink = driver.find_element(By.XPATH, "//div[contains(@class, 'faq__question') and contains(., 'Risklərin İdarə Edilməsi')]")
        safe_click(driver, risk_qlink)
        time.sleep(1.5)
        panel = driver.find_element(By.XPATH, "//div[contains(@class, 'faq__answer') and .//b[contains(., 'Risklərin İdarə Edilməsi')]]/following-sibling::div")
        scroll_inner_panel_until_loaded(panel)
        time.sleep(2)
        links = panel.find_elements(By.CSS_SELECTOR, "a.link_document")
        for link in links:
            href = link.get_attribute("href")
            label = link.text.strip()
            ext = os.path.splitext(href.split('?')[0])[1].lower()
            if not href or ext not in VALID_EXTENSIONS:
                continue
            yyyy, quarter = get_year_quarter(label)
            if not yyyy or not quarter:
                continue
            available_year_quarters.add((yyyy, quarter))
            report_type = None
            for az_risk, en_risk in RISK_REPORTS_AZ_TO_EN.items():
                if az_risk in label:
                    report_type = en_risk
                    break
            if not report_type:
                continue
            save_name = f"{report_type}_{yyyy}_{quarter}{ext}"
            subfolder = f"{yyyy}_{quarter}"
            period_dir = os.path.join(RAW_DATA_DIR if ext == ".pdf" else PROCESSED_DATA_DIR, subfolder)
            os.makedirs(period_dir, exist_ok=True)
            fpath = os.path.join(period_dir, save_name)
            if ext == ".pdf" and file_exists(RAW_DATA_DIR, report_type, yyyy, quarter, [".pdf"]):
                report.append(f"[SKIP] Already exists: {subfolder}/{save_name}")
                continue
            if ext in [".xlsx", ".xls"] and file_exists(PROCESSED_DATA_DIR, report_type, yyyy, quarter, [".xlsx", ".xls"]):
                report.append(f"[SKIP] Already exists: {subfolder}/{save_name}")
                continue
            url = href if href.startswith("http") else "https://www.accessbank.az" + href
            print(f"    Downloading: {subfolder}/{save_name}")
            try:
                r = session.get(url, headers=headers, timeout=25)
                if ext == ".pdf" and not r.content.startswith(b'%PDF-'):
                    report.append(f"[SKIP_CORRUPT] {subfolder}/{save_name}")
                    continue
                if ext in [".xlsx", ".xls"] and r.content[:2] != b'PK':
                    report.append(f"[SKIP_CORRUPT] {subfolder}/{save_name}")
                    continue
                with open(fpath, "wb") as out:
                    out.write(r.content)
                report.append(f"[OK] {subfolder}/{save_name}")
                total_downloaded += 1
            except Exception as e:
                report.append(f"[ERROR] {subfolder}/{save_name}: {e}")
    except Exception as e:
        report.append(f"[MISSING_ON_SITE] risk_reports: {e}")

    print("\n=== FULL ACCESSBANK REPORT ===")
    for line in report:
        print(line)

    # Report missing for PDFs in raw_data and Excels in processed_data *SEPARATELY*
    print("\n=== MISSING PDF CORE REPORTS IN RAW_DATA PER QUARTER ===")
    for yyyy, quarter in sorted(available_year_quarters, reverse=True):
        missing = [core for core in CORE_REPORTS if not file_exists(RAW_DATA_DIR, core, yyyy, quarter, [".pdf"])]
        if missing:
            print(f"{yyyy}_{quarter}: missing PDFs: {missing}")

    print("\n=== MISSING EXCEL CORE REPORTS IN PROCESSED_DATA PER QUARTER ===")
    for yyyy, quarter in sorted(available_year_quarters, reverse=True):
        missing = [core for core in CORE_REPORTS if not file_exists(PROCESSED_DATA_DIR, core, yyyy, quarter, [".xlsx", ".xls"])]
        if missing:
            print(f"{yyyy}_{quarter}: missing Excels: {missing}")

    print(f"\nDone.\nAll PDFs in raw_data/access_bank/<year>_<quarter>/, Excels in processed_data/access_bank/<year>_<quarter>/")
    print(f"Total files downloaded: {total_downloaded}")
    driver.quit()

if __name__ == "__main__":
    main()