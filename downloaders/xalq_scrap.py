import os
import re
import time
import unidecode
import requests
from selenium.webdriver.common.by import By
import undetected_chromedriver as uc

BASE_URL = "https://xalqbank.az/az/ferdi/bank/bank-haqqinda-melumatlarin-aciqlanmasi/maliyye-gostericileri-tab?include=menu"
RAW_DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'raw_data', 'xalq_bank')
os.makedirs(RAW_DATA_DIR, exist_ok=True)

REPORT_TYPES = [
    ("Balans hesabatı", "balance"),
    ("Kapital dəyişmələri", "capital_change"),
    ("Mənfəət və zərər haqqında hesabat", "profit_and_loss"),
    ("Pul vəsaitinin hərəkəti", "cash_flow"),
    ("Bankın birinci və ikinci dərəcəli kapitalının məbləği və onun elementləri", "capital_adequacy"),
    ("Likvidlik riski", "liquidity_risk"),
    ("Faiz riski", "interest_rate_risk"),
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

def safe_click(driver, elem, header_offset=120):
    """Scrolls to the element with offset and clicks via JS (avoids header/interception)."""
    driver.execute_script(
        "window.scrollTo(0, arguments[0].getBoundingClientRect().top + window.scrollY - arguments[1]);",
        elem, header_offset
    )
    time.sleep(0.5)
    driver.execute_script("arguments[0].click();", elem)
    time.sleep(2.8)  # wait for page load

def main():
    report = []
    total_downloaded = 0

    options = uc.ChromeOptions()
    driver = uc.Chrome(options=options)
    driver.get(BASE_URL)
    time.sleep(4)  # Let the menu page fully load

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
            year, period = get_year_period(info_text)
            if not year or period == "unknown" or int(year) < 2020:
                continue
            ext = os.path.splitext(href.split('?')[0])[1].lower()
            save_name = f"{en_name}_{year}_{period}{ext}"
            fpath = os.path.join(RAW_DATA_DIR, save_name)
            if os.path.exists(fpath):
                report.append(f"[OK] {save_name}")
                total_downloaded += 1
                continue
            try:
                print(f"    Downloading: {save_name}")
                r = session.get(href, headers=headers, timeout=20)
                if (ext == ".pdf" and not r.content.startswith(b'%PDF-')) or (ext in [".xlsx", ".xls"] and r.content[:2] != b'PK'):
                    report.append(f"[SKIP_CORRUPT] {save_name}")
                    continue
                with open(fpath, "wb") as out:
                    out.write(r.content)
                report.append(f"[OK] {save_name}")
                total_downloaded += 1
            except Exception as e:
                report.append(f"[ERROR] {save_name}: {e}")

        # Go BACK to menu page for next section
        driver.get(BASE_URL)
        time.sleep(2.5)  # Let menu reload

    print("\n=== FULL XALQ-STYLE REPORT ===")
    for line in report:
        print(line)

    print("\nSUMMARY REPORT")
    print(f"Total files downloaded: {total_downloaded}")
    missing = len([l for l in report if l.startswith('[MISSING_ON_SITE]')])
    skip = len([l for l in report if l.startswith('[SKIP')])
    error = len([l for l in report if l.startswith('[ERROR]')])
    renamed = len([l for l in report if l.startswith('[RENAME]')])
    print(f"Missing/Skipped: {missing + skip + error}")
    print(f"Renamed: {renamed}")
    print("\nBrowser will remain open for manual review. Close it when done.\n")
    driver.quit()

if __name__ == "__main__":
    main()
