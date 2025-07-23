import os
import time
import re
import requests
import unidecode
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from collections import defaultdict

BASE_URL = "https://abb-bank.az/az/hesabatlar"
RAW_DATA_DIR = os.path.join("raw_data", "abb_bank")
os.makedirs(RAW_DATA_DIR, exist_ok=True)

CORE_REPORTS = [
    "balance_sheet",
    "profit_and_loss",
    "cash_flow",
    "capital_adequacy",
    "liquidity_risk",
    "portfolio_share",
    "credit_risk",
    "interest_rate_risk",
    "currency_risk"
]
SECTION_MAP = {
    "maliyyə vəziyyəti": "balance_sheet",
    "mənfəət və zərər": "profit_and_loss",
    "pul vəsaitlərinin hərəkəti": "cash_flow",
    "kapital adekvatlığı": "capital_adequacy",
    "risk hesabatları": "risk_reports",
    "likvidlik riski": "liquidity_risk",
}
RISK_REPORTS_AZ_TO_EN = {
    "Kreditlərin, həmçinin vaxtı keçmiş kreditlərin portfeldə payı və onun iqtisadi sektorlar üzrə göstəriciləri": "portfolio_share",
    "Kredit riski - kreditlərin təminat üzrə bölgüsü": "credit_risk",
    "Faiz riski": "interest_rate_risk",
    "Valyuta riski": "currency_risk",
}
CAP_ADEQ_AZ = "Bank kapitalının strukturu və adekvatlığı barədə məlumatlar"

def normalize(txt):
    txt = unidecode.unidecode(txt or "")
    txt = txt.lower()
    txt = re.sub(r"\s+", " ", txt)
    return txt.strip()

SECTION_MAP_NORM = {normalize(k): v for k, v in SECTION_MAP.items()}

def get_year_period(text):
    norm = normalize(text)
    year_match = re.search(r"(\d{4})", norm)
    year = year_match.group(1) if year_match else ""
    q_match = re.search(r"\b([iv]+)\s*rub", norm)
    if q_match:
        q_roman = q_match.group(1).upper()
        q_map = {"I": "Q1", "II": "Q2", "III": "Q3", "IV": "Q4"}
        period = q_map.get(q_roman, q_roman)
    elif "12 ay" in norm or "illik" in norm:
        period = "12m"
    else:
        period = "unknown"
    return year, period

def file_exists_anywhere(period, fname):
    # Checks for file in period's subfolder (future-proof, avoids dups)
    period_dir = os.path.join(RAW_DATA_DIR, period)
    return os.path.exists(os.path.join(period_dir, fname))

def main():
    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    driver = uc.Chrome(options=options)
    driver.get(BASE_URL)
    time.sleep(3)

    try:
        onesignal_close = driver.find_element(By.CSS_SELECTOR, "#onesignal-slidedown-dialog button.onesignal-slidedown-cancel-button")
        onesignal_close.click()
        time.sleep(1)
    except Exception:
        pass

    try:
        accept_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Qəbul et')]")
        accept_btn.click()
    except Exception:
        pass
    time.sleep(1)

    try:
        other_reports_btn = driver.find_element(By.XPATH, "//span[contains(text(),'Digər hesabatlar')]")
        other_reports_btn.click()
        time.sleep(2)
    except Exception as e:
        print(f"[ERROR] Could not click Other reports tab: {e}")
        driver.quit()
        return

    session = requests.Session()
    for cookie in driver.get_cookies():
        session.cookies.set(cookie['name'], cookie['value'])
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": BASE_URL
    }

    section_headers = driver.find_elements(By.CSS_SELECTOR, "h4.ac-q")
    print(f"Found {len(section_headers)} report sections.")

    quarter_files = defaultdict(set)  # {period: set([report_types])}
    downloaded_keys = set()
    for section in section_headers:
        section_name_az = section.text.strip()
        section_name_az_norm = normalize(section_name_az)
        if section_name_az_norm not in SECTION_MAP_NORM:
            continue
        section_name_en = SECTION_MAP_NORM[section_name_az_norm]
        print(f"\nSection: {section_name_en}")

        try:
            if not section.get_attribute("aria-expanded") or section.get_attribute("aria-expanded") == "false":
                driver.execute_script("arguments[0].scrollIntoView();", section)
                ActionChains(driver).move_to_element(section).perform()
                section.click()
                time.sleep(1.0)
        except Exception:
            continue

        cards = section.find_elements(By.XPATH, "./following-sibling::div[1]//a[contains(@href,'.pdf')]")
        print(f"  Found {len(cards)} cards.")

        for card in cards:
            href = card.get_attribute("href")
            try:
                period_elem = card.find_element(By.XPATH, "../../p[1]")
                period_text = period_elem.text.strip()
            except Exception:
                period_text = card.text.strip()
            year, period = get_year_period(period_text)
            if not year or not period or period == "unknown" or int(year) < 2020:
                continue
            ext = href.split('.')[-1].split('?')[0].lower()
            if ext != 'pdf':
                continue

            report_type = None
            do_download = False

            if section_name_en == "capital_adequacy":
                if CAP_ADEQ_AZ in period_text:
                    report_type = section_name_en
                    do_download = True
            elif section_name_en == "risk_reports":
                for az_title, en_title in RISK_REPORTS_AZ_TO_EN.items():
                    if period_text.strip().startswith(az_title):
                        key = (en_title, year, period)
                        if key in downloaded_keys:
                            do_download = False
                            break
                        downloaded_keys.add(key)
                        report_type = en_title
                        do_download = True
                        break
            else:
                report_type = section_name_en
                do_download = True

            if not do_download or not report_type:
                continue

            quarter_folder = f"{year}_{period}"
            period_dir = os.path.join(RAW_DATA_DIR, quarter_folder)
            os.makedirs(period_dir, exist_ok=True)
            save_name = f"{report_type}_{year}_{period}.pdf"
            fpath = os.path.join(period_dir, save_name)
            if file_exists_anywhere(quarter_folder, save_name):
                print(f"[SKIP] Already exists in {quarter_folder}: {save_name}")
                quarter_files[quarter_folder].add(report_type)
                continue

            print(f"    Downloading: {quarter_folder}/{save_name}")
            try:
                r = session.get(href, headers=headers, timeout=20)
                if not r.content.startswith(b'%PDF-'):
                    print(f"    [!] Not a real PDF: {href}")
                    continue
                with open(fpath, "wb") as out:
                    out.write(r.content)
                quarter_files[quarter_folder].add(report_type)
            except Exception as e:
                print(f"    [!] Download error: {e}")

    driver.quit()

    # Scan already existing files in subfolders
    for subdir in os.listdir(RAW_DATA_DIR):
        period_path = os.path.join(RAW_DATA_DIR, subdir)
        if not os.path.isdir(period_path):
            continue
        for fname in os.listdir(period_path):
            m = re.match(r"([a-z_]+)_(\d{4})_(Q[1-4]|12m)\.pdf", fname)
            if m:
                report_type, year, quarter = m.group(1), m.group(2), m.group(3)
                key = f"{year}_{quarter}"
                quarter_files[key].add(report_type)

    print("\n=== SUMMARY OF MISSING REPORTS PER QUARTER ===")
    for quarter in sorted(quarter_files.keys()):
        got = quarter_files[quarter]
        miss = [k for k in CORE_REPORTS if k not in got]
        if miss:
            print(f"{quarter}: missing {miss}")
    print("Done.\nAll PDFs in raw_data/abb_bank/<year>_<quarter>/")

if __name__ == "__main__":
    main()