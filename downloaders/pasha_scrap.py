import os
import re
import time
import unidecode
import requests
import shutil
from selenium.webdriver.common.by import By
import undetected_chromedriver as uc
from collections import defaultdict
from urllib.parse import urljoin

BASE_URL = "https://www.pashabank.az/static,95/lang,az/"
RAW_DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'raw_data', 'pasha_bank')
PROCESSED_ROOT = os.path.join(os.path.dirname(__file__), '..', 'processed_data', 'pasha_bank')
os.makedirs(RAW_DATA_DIR, exist_ok=True)
os.makedirs(PROCESSED_ROOT, exist_ok=True)

SECTION_MAP = {
    "maliyyə hesabatları": "balance_sheet",
    "kapital dəyişmələri": "capital_change",
    "kredit riski": "credit_risk",
    "valyuta riski": "currency_risk",
    "digər maliyyə məlumatları": "other_data",
    "digər maliyyə məlumatı": "other_data",
    "risk dərəcəsi üzrə ölçülmüş aktivlərdən asılı olan kapitalın adekvatlıq standartlarının (əmsallarının) hesablanması": "capital_adequacy",
}
VALID_EXTENSIONS = [".pdf", ".xlsx", ".xls"]

def normalize(txt):
    txt = unidecode.unidecode(txt or "")
    txt = txt.lower()
    txt = re.sub(r"[\s\W_]+", " ", txt)
    txt = txt.replace("\u200c", "")   # Remove ZWNJ if present
    txt = txt.strip()
    return txt

SECTION_MAP_NORM = {normalize(k): v for k, v in SECTION_MAP.items()}

def get_year_period(text):
    norm = normalize(text)
    year_match = re.search(r"(\d{4})", norm)
    year = year_match.group(1) if year_match else ""
    q_match = re.search(r"(i{1,3}|iv)\s*r[uü]b", norm)
    if q_match:
        q_roman = q_match.group(1).upper()
        q_map = {"I": "Q1", "II": "Q2", "III": "Q3", "IV": "Q4"}
        period = q_map.get(q_roman, q_roman)
    elif "12 ay" in norm or "illik" in norm:
        period = "12m"
    else:
        period = "unknown"
    return year, period

def get_extension(href):
    ext = os.path.splitext(href.split('?')[0])[1]
    return ext.lower()

def should_skip(link_text, href):
    norm = normalize(link_text)
    if "valyuta movqeyi" in norm:
        return True
    return False

def is_2022_or_after(year, period):
    try:
        y = int(year)
    except:
        return False
    if y > 2022:
        return True
    if y == 2022:
        return period in ["Q1", "Q2", "Q3", "Q4"]
    return False

def file_exists_anywhere(root, fname):
    for dirpath, _, files in os.walk(root):
        if fname in files:
            return True
    return False

def main():
    BASE_EXPECTED = [
        "balance_sheet", "cash_flow", "credit_risk", "currency_risk", "other_data"
    ]
    report = []
    per_quarter_files = defaultdict(set)
    present_periods = set()

    options = uc.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    driver = uc.Chrome(options=options)
    driver.get(BASE_URL)
    time.sleep(3)
    try:
        accept_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Qəbul et')]")
        accept_btn.click()
        time.sleep(1)
    except Exception:
        pass

    session = requests.Session()
    for cookie in driver.get_cookies():
        session.cookies.set(cookie['name'], cookie['value'])
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": BASE_URL
    }

    links = driver.find_elements(By.TAG_NAME, "a")
    files_on_site = defaultdict(dict)
    unmatched_links = []

    for link in links:
        href = link.get_attribute("href")
        text = link.text.strip()
        if not href:
            continue
        if not any(href.lower().endswith(ext) for ext in VALID_EXTENSIONS):
            continue
        if not text:
            try:
                text = link.find_element(By.XPATH, ".//strong").text.strip()
            except:
                try:
                    text = link.find_element(By.XPATH, "..").text.strip()
                except:
                    text = href

        if should_skip(text, href):
            continue

        text_norm = normalize(text)
        section_type = None
        for az, en in SECTION_MAP_NORM.items():
            if az in text_norm:
                section_type = en
                break
        if not section_type:
            unmatched_links.append((text, text_norm, href))
            continue

        year, period = get_year_period(text)
        if not year or period == "unknown" or int(year) < 2020:
            continue
        ext = get_extension(href)
        if ext not in VALID_EXTENSIONS:
            continue
        if not href.startswith("http"):
            href = urljoin(BASE_URL, href)

        save_name = f"{section_type}_{year}_{period}{ext}"
        period_dir = os.path.join(RAW_DATA_DIR, f"{year}_{period}")
        os.makedirs(period_dir, exist_ok=True)
        fpath_actual = os.path.join(period_dir, save_name)

        # Check exists in period subfolder or anywhere
        already_exists = (
            file_exists_anywhere(period_dir, save_name) or 
            file_exists_anywhere(RAW_DATA_DIR, save_name) or 
            file_exists_anywhere(PROCESSED_ROOT, save_name)
        )
        if already_exists:
            report.append(f"[SKIP] Already exists: {save_name}")
            per_quarter_files[f"{year}_{period}"].add(section_type)
            present_periods.add((year, period))
            continue

        # Download and save
        try:
            print(f"    Downloading: {save_name}")
            r = session.get(href, headers=headers, timeout=20)
            if (save_name.endswith(".pdf") and not r.content.startswith(b'%PDF-')) or (
                save_name.endswith(".xlsx") and r.content[:2] != b'PK'
            ):
                report.append(f"[SKIP_CORRUPT] {save_name}")
                continue
            with open(fpath_actual, "wb") as out:
                out.write(r.content)
            report.append(f"[OK] {save_name}")
            per_quarter_files[f"{year}_{period}"].add(section_type)
            present_periods.add((year, period))
        except Exception as e:
            report.append(f"[ERROR] {save_name}: {e}")
            continue

    driver.quit()

    print("\n=== FULL REPORT ===")
    for line in report:
        print(line)

    # FINAL MISSING SUMMARY PER QUARTER (true future-proof)
    print("\n=== SUMMARY OF MISSING REPORTS PER QUARTER ===")
    for (year, period) in sorted(present_periods):
        is_after = is_2022_or_after(year, period)
        if is_after:
            expected_types = BASE_EXPECTED + ["capital_change", "capital_adequacy"]
        else:
            expected_types = BASE_EXPECTED + ["capital_change"]
        missing = []
        for k in expected_types:
            fname_pdf = f"{k}_{year}_{period}.pdf"
            fname_xlsx = f"{k}_{year}_{period}.xlsx"
            fname_xls = f"{k}_{year}_{period}.xls"
            if not (
                file_exists_anywhere(os.path.join(RAW_DATA_DIR, f"{year}_{period}"), fname_pdf)
                or file_exists_anywhere(os.path.join(RAW_DATA_DIR, f"{year}_{period}"), fname_xlsx)
                or file_exists_anywhere(os.path.join(RAW_DATA_DIR, f"{year}_{period}"), fname_xls)
                or file_exists_anywhere(RAW_DATA_DIR, fname_pdf)
                or file_exists_anywhere(RAW_DATA_DIR, fname_xlsx)
                or file_exists_anywhere(RAW_DATA_DIR, fname_xls)
                or file_exists_anywhere(PROCESSED_ROOT, fname_xlsx)
                or file_exists_anywhere(PROCESSED_ROOT, fname_xls)
            ):
                missing.append(k)
        if missing:
            print(f"{year}_{period}: missing {missing}")

    print("Done.")
    print(f"Total files downloaded: {len([l for l in report if l.startswith('[OK]')])}")

if __name__ == "__main__":
    main()
