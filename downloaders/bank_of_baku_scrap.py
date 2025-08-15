import os
import time
import re
import requests
from datetime import datetime
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import undetected_chromedriver as uc

BASE_URL = "https://www.bankofbaku.com/en/about-the-bank/reports/quarterly-reports"
PROCESSED_DATA_DIR = os.path.join("processed_data", "bank_of_baku")
os.makedirs(PROCESSED_DATA_DIR, exist_ok=True)

REPORT_TYPES = {
    "Balance sheet": "balance_sheet",
    "Profit and loss statement": "profit_and_loss",
    "Quarterly report on the capital structure and the adequacy": "capital_adequacy",
    "Credit Risk": "credit_risk",
    "Currency Risk": "currency_risk"
}

CORE_REPORTS = [
    "balance_sheet",
    "profit_and_loss",
    "capital_adequacy",
    "credit_risk",
    "currency_risk"
]

YEAR_RANGE = list(range(2020, datetime.now().year + 1))

def normalize_quarter_label(label):
    label = label.lower()
    if "iv" in label: return "Q4"
    if "iii" in label: return "Q3"
    if "ii" in label: return "Q2"
    if "i" in label: return "Q1"
    return None

def extract_year(text):
    m = re.search(r"(20\d{2})", text)
    return int(m.group(1)) if m else None

def scroll_and_click(driver, el):
    driver.execute_script("""
        arguments[0].scrollIntoView({block: 'center'});
        window.scrollBy(0, -100);
    """, el)
    time.sleep(0.6)
    driver.execute_script("arguments[0].click();", el)
    time.sleep(1.2)

def file_exists_anywhere(report_type, year, quarter):
    period = f"{year}_{quarter}"
    fname = f"bank_of_baku_{report_type}_{year}_{quarter}.xlsx"
    folder = os.path.join(PROCESSED_DATA_DIR, period)
    return os.path.exists(os.path.join(folder, fname))

def main():
    options = uc.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    driver = uc.Chrome(options=options)
    wait = WebDriverWait(driver, 10)
    driver.get(BASE_URL)
    print("[DEBUG] Loaded Bank of Baku page")
    time.sleep(2.5)

    session = requests.Session()
    for cookie in driver.get_cookies():
        session.cookies.set(cookie['name'], cookie['value'])
    headers = {"User-Agent": "Mozilla/5.0", "Referer": BASE_URL}

    report = []
    total_downloaded = 0
    all_year_quarters = set()

    for display_name, internal_name in REPORT_TYPES.items():
        try:
            section_btn = wait.until(EC.element_to_be_clickable((
                By.XPATH, f"//h2[contains(@class, 'accordion__header') and contains(., '{display_name}')]")))
            scroll_and_click(driver, section_btn)
            print(f"[INFO] Opened section: {display_name}")
        except Exception as e:
            report.append(f"[MISSING] {display_name} section not found: {e}")
            continue

        year_headers = driver.find_elements(By.XPATH,
            f"//h2[contains(., '{display_name}')]/following-sibling::div//h2[contains(@class, 'accordion__header')]")
        print(f"[DEBUG] Found {len(year_headers)} years in {display_name}")

        for year_header in year_headers:
            try:
                year_text = year_header.text.strip()
                year = extract_year(year_text)
                if not year or year not in YEAR_RANGE:
                    continue

                scroll_and_click(driver, year_header)
                print(f"  [INFO] Opened year {year}")

                accordion = year_header.find_element(By.XPATH, "./following-sibling::div[contains(@class, 'accordion__main')]")
                links = accordion.find_elements(By.XPATH, ".//a[contains(@href, 'storage')]")

                for a in links:
                    href = a.get_attribute("href")
                    span = a.find_element(By.TAG_NAME, "span").text.strip()
                    quarter = normalize_quarter_label(span)
                    if not href or not quarter:
                        continue
                    period = f"{year}_{quarter}"
                    all_year_quarters.add((year, quarter))
                    folder = os.path.join(PROCESSED_DATA_DIR, period)
                    os.makedirs(folder, exist_ok=True)
                    fname = f"bank_of_baku_{internal_name}_{year}_{quarter}.xlsx"
                    fpath = os.path.join(folder, fname)
                    if os.path.exists(fpath):
                        report.append(f"[SKIP] Already exists: {period}/{fname}")
                        continue

                    try:
                        r = session.get(href, headers=headers, timeout=20)
                        if r.status_code == 200 and r.content[:2] == b'PK':
                            with open(fpath, "wb") as out:
                                out.write(r.content)
                            report.append(f"[OK] {fname}")
                            total_downloaded += 1
                        else:
                            report.append(f"[ERROR] {fname} failed (status {r.status_code})")
                    except Exception as e:
                        report.append(f"[ERROR] {fname}: {e}")
            except Exception as e:
                report.append(f"[ERROR] Year block in {display_name} failed: {e}")
                continue

    print("\n=== BANK OF BAKU FULL REPORT ===")
    for line in report:
        print(line)
    print("\nSUMMARY REPORT")
    print(f"Total files downloaded: {total_downloaded}")
    missing = len([l for l in report if l.startswith('[SKIP') or l.startswith('[ERROR') or l.startswith('[MISSING')])

    print("\n=== SUMMARY OF MISSING CORE REPORTS PER QUARTER ===")
    for year, quarter in sorted(all_year_quarters, reverse=True):
        missing_core = [core for core in CORE_REPORTS if not file_exists_anywhere(core, year, quarter)]
        if missing_core:
            print(f"{year}_{quarter}: missing {missing_core}")

    print(f"\nDone.\nAll Excels in processed_data/bank_of_baku/<year>_<quarter>/")
    driver.quit()

if __name__ == "__main__":
    main()
