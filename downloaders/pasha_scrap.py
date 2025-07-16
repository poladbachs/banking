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
os.makedirs(RAW_DATA_DIR, exist_ok=True)

SECTION_MAP = {
    "maliyyə hesabatları": "balance",
    "pul vəsaitlərinin hərəkəti": "cash_flow",
    "kapital dəyişmələri": "capital_change",
    "kredit riski": "credit_risk",
    "likvidlik riski": "liquidity_risk",
    "valyuta riski": "currency_risk",
    "faiz riski": "interest_rate_risk",
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

def main():
    BASE_EXPECTED = [
        "balance", "cash_flow", "credit_risk", "liquidity_risk", "interest_rate_risk", "currency_risk", "other_data"
    ]
    report = []

    options = uc.ChromeOptions()
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
    present_periods = set()
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
        files_on_site[(year, period)][section_type] = (href, save_name, ext)
        present_periods.add((year, period))

    # PRINT unmatched links for debugging
    if unmatched_links:
        print("\n[DEBUG] Unmatched links (not mapped):")
        for orig, normed, href in unmatched_links:
            print(f"  RAW: {orig} | NORM: {normed} | {href}")

    def period_key(x):
        year, period = x
        qorder = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4, "12m": 5}
        return (int(year), qorder.get(period, 99))
    periods_sorted = sorted(list(present_periods), key=period_key)

    total_downloaded = 0
    for y, q in periods_sorted:
        is_after = is_2022_or_after(y, q)

        if is_after:
            expected_types = BASE_EXPECTED + ["capital_change", "capital_adequacy"]
        else:
            expected_types = BASE_EXPECTED + ["capital_change"]

        found_types = files_on_site.get((y, q), {})
        for typ in expected_types:
            on_site = [k for k in found_types.keys() if k == typ]
            file_downloaded = False
            if on_site:
                href, actual_fname, ext = found_types[typ]
                fpath_actual = os.path.join(RAW_DATA_DIR, actual_fname)
                if not os.path.exists(fpath_actual):
                    try:
                        print(f"    Downloading: {actual_fname}")
                        r = session.get(href, headers=headers, timeout=20)
                        if (actual_fname.endswith(".pdf") and not r.content.startswith(b'%PDF-')) or (actual_fname.endswith(".xlsx") and r.content[:2] != b'PK'):
                            report.append(f"[SKIP_CORRUPT] {actual_fname}")
                            continue
                        with open(fpath_actual, "wb") as out:
                            out.write(r.content)
                        report.append(f"[OK] {actual_fname}")
                        total_downloaded += 1
                    except Exception as e:
                        report.append(f"[ERROR] {actual_fname}: {e}")
                        continue
                else:
                    report.append(f"[OK] {actual_fname}")
                    total_downloaded += 1
                file_downloaded = True
            # For 2022 Q1+ (and after), if capital_adequacy missing but capital_change exists, RENAME ON DISK!
            if (typ == "capital_adequacy" and is_after and not file_downloaded):
                moved = False
                for ext2 in VALID_EXTENSIONS:
                    cap_change_path = os.path.join(RAW_DATA_DIR, f"capital_change_{y}_{q}{ext2}")
                    cap_adequacy_path = os.path.join(RAW_DATA_DIR, f"capital_adequacy_{y}_{q}{ext2}")
                    if os.path.exists(cap_change_path) and not os.path.exists(cap_adequacy_path):
                        shutil.move(cap_change_path, cap_adequacy_path)
                        report.append(f"[RENAME] capital_change_{y}_{q}{ext2} → capital_adequacy_{y}_{q}{ext2}")
                        total_downloaded += 1
                        moved = True
                        break
                # DO NOT REPORT MISSING IF NOT MOVED
            elif not file_downloaded and not (typ == "capital_adequacy" and is_after):
                report.append(f"[MISSING_ON_SITE] {typ}_{y}_{q}.pdf")

    print("\n=== FULL ABB-STYLE REPORT ===")
    for line in report:
        print(line)

    print("\nSUMMARY REPORT")
    print(f"Total files downloaded: {total_downloaded}")
    missing = len([l for l in report if l.startswith("[MISSING_ON_SITE]")])
    skip = len([l for l in report if l.startswith("[SKIP")])
    error = len([l for l in report if l.startswith("[ERROR]")])
    renamed = len([l for l in report if l.startswith("[RENAME]")])
    print(f"Missing/Skipped: {missing + skip + error}")
    print(f"Renamed: {renamed}")

    print("\nBrowser will remain open for manual review. Close it when done.")

if __name__ == "__main__":
    main()