import os
import time
import re
import requests
import unidecode
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By

BASE_URL = "https://www.accessbank.az/az/our-bank/in-figures/"
RAW_DATA_DIR = os.path.join("raw_data", "access_bank")
os.makedirs(RAW_DATA_DIR, exist_ok=True)

SECTION_MAP = {
    "Kapital adekvatlığı": "capital_adequacy",
    "Maliyyə vəziyyəti haqqında hesabat": "balance",
    "Mənfəət və zərər hesabatı": "profit_and_loss",
    "Kapital strukturunda dəyişikliklər haqqında hesabat": "capital_change",
    "Pul hərəkəti haqqında hesabat": "cash_flow",
    "Risklərin İdarə Edilməsi": "risk_reports"
}
RISK_REPORTS_AZ_TO_EN = {
    "Faiz riski": "interest_rate_risk",
    "Likvidlik riski": "liquidity_risk",
    "Kredit riski": "credit_risk",
    "Valyuta riski": "currency_risk",
    "Əhəmiyyətli risklərin idarə edilməsi": "material_risks"
}
VALID_EXTENSIONS = [".pdf", ".xlsx", ".xls"]

def normalize(txt):
    txt = unidecode.unidecode(txt or "")
    txt = txt.lower().strip()
    txt = re.sub(r"[\s\W_]+", " ", txt)
    return txt.strip()

def get_quarter_from_label(text):
    m = re.search(r"(\d{2})\.(\d{2})\.(20\d{2})", text)
    if not m:
        return None
    mm = m.group(2)
    q_map = {"03": "Q1", "06": "Q2", "09": "Q3", "12": "Q4"}
    return q_map.get(mm)

def safe_click(driver, elem, header_offset=120):
    driver.execute_script(
        "window.scrollTo(0, arguments[0].getBoundingClientRect().top + window.scrollY - arguments[1]);",
        elem, header_offset
    )
    time.sleep(0.3)
    driver.execute_script("arguments[0].click();", elem)
    time.sleep(1.1)

def scroll_all_years_in_preview(driver):
    try:
        preview = driver.find_element(By.CSS_SELECTOR, "div.faq__list-preview")
        last_html = ""
        for _ in range(20):
            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", preview)
            time.sleep(0.7)
            try:
                show_more = preview.find_element(By.CSS_SELECTOR, "a.button2[data-role='paginate']")
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", show_more)
                show_more.click()
                time.sleep(1.1)
            except Exception:
                pass
            new_html = preview.get_attribute('innerHTML')
            if new_html == last_html:
                break
            last_html = new_html
    except Exception as e:
        print(f"[WARN] Could not scroll preview panel: {e}")

def main():
    report = []
    total_downloaded = 0

    options = uc.ChromeOptions()
    driver = uc.Chrome(options=options)
    driver.get(BASE_URL)
    time.sleep(4)

    session = requests.Session()
    for cookie in driver.get_cookies():
        session.cookies.set(cookie['name'], cookie['value'])
    headers = {"User-Agent": "Mozilla/5.0", "Referer": BASE_URL}

    for az_title, section_en in SECTION_MAP.items():
        print(f"\n[INFO] Scraping section: {az_title} ({section_en})")
        try:
            qlink = driver.find_element(By.XPATH, f"//div[contains(@class, 'faq__question') and contains(., '{az_title}')]")
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", qlink)
            time.sleep(0.6)
            safe_click(driver, qlink)
            scroll_all_years_in_preview(driver)
            time.sleep(1.0)
        except Exception as e:
            report.append(f"[MISSING_ON_SITE] {section_en}: cannot find/click menu ({e})")
            continue

        doc_blocks = driver.find_elements(By.CSS_SELECTOR, "div.faq__document-group-wr")
        print(f"    [DEBUG] Found {len(doc_blocks)} year groups")
        if not doc_blocks:
            report.append(f"[SKIP] No doc groups for {section_en}")
            continue

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
                if not href or not any(ext == ve for ve in VALID_EXTENSIONS):
                    continue

                if section_en == "risk_reports":
                    # For risk_reports: quarter from label, year from group (fixes typos in label)
                    quarter = get_quarter_from_label(label)
                    yyyy = block_year
                else:
                    # Other sections: year/quarter from label
                    m = re.search(r"(\d{2})\.(\d{2})\.(20\d{2})", label)
                    if not m:
                        continue
                    mm, yyyy = m.group(2), m.group(3)
                    q_map = {"03": "Q1", "06": "Q2", "09": "Q3", "12": "Q4"}
                    quarter = q_map.get(mm)
                if not yyyy or not quarter:
                    continue

                if section_en == "risk_reports":
                    report_type = None
                    for az_risk, en_risk in RISK_REPORTS_AZ_TO_EN.items():
                        if az_risk in label:
                            report_type = f"{section_en}_{en_risk}"
                            break
                    if not report_type:
                        report_type = section_en
                else:
                    report_type = section_en

                save_name = f"{report_type}_{yyyy}_{quarter}{ext}"
                fpath = os.path.join(RAW_DATA_DIR, save_name)
                if os.path.exists(fpath):
                    report.append(f"[OK] {save_name} (already exists)")
                    total_downloaded += 1
                    continue
                url = href if href.startswith("http") else "https://www.accessbank.az" + href
                print(f"    Downloading: {save_name}")
                try:
                    r = session.get(url, headers=headers, timeout=25)
                    if ext == ".pdf" and not r.content.startswith(b'%PDF-'):
                        report.append(f"[SKIP_CORRUPT] {save_name}")
                        continue
                    if ext in [".xlsx", ".xls"] and r.content[:2] != b'PK':
                        report.append(f"[SKIP_CORRUPT] {save_name}")
                        continue
                    with open(fpath, "wb") as out:
                        out.write(r.content)
                    report.append(f"[OK] {save_name}")
                    total_downloaded += 1
                except Exception as e:
                    report.append(f"[ERROR] {save_name}: {e}")

    print("\n=== FULL ACCESSBANK REPORT ===")
    for line in report:
        print(line)
    print("\nSUMMARY REPORT")
    print(f"Total files downloaded: {total_downloaded}")
    missing = len([l for l in report if l.startswith('[MISSING_ON_SITE]') or l.startswith('[SKIP') or l.startswith('[ERROR')])
    print(f"Missing/Skipped: {missing}")
    print("\nBrowser will remain open for manual review. Close it when done.\n")
    driver.quit()

if __name__ == "__main__":
    main()
