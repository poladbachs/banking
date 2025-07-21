import os
import time
import requests
from selenium.webdriver.common.by import By
import undetected_chromedriver as uc

BASE_URL = "https://unibank.az/az/documents/quarterlyReports"
RAW_DATA_DIR = os.path.join("processed_data", "unibank")
os.makedirs(RAW_DATA_DIR, exist_ok=True)
YEARS = [2025, 2024, 2023, 2022, 2021, 2020]

def normalize_quarter(text):
    roman_map = {"I": "Q1", "II": "Q2", "III": "Q3", "IV": "Q4"}
    text = text.upper().replace("RÜB", "").strip()
    return roman_map.get(text, text.replace(" ", "_"))

def main():
    options = uc.ChromeOptions()
    driver = uc.Chrome(options=options)
    driver.get(BASE_URL)
    time.sleep(3.5)

    session = requests.Session()
    for cookie in driver.get_cookies():
        session.cookies.set(cookie['name'], cookie['value'])
    headers = {"User-Agent": "Mozilla/5.0", "Referer": BASE_URL}

    report = []
    total_downloaded = 0

    for year in YEARS:
        try:
            # 1. Click year tab
            year_tab = driver.find_element(By.XPATH, f"//a[@data-year='{year}']")
            driver.execute_script("arguments[0].scrollIntoView(true);", year_tab)
            year_tab.click()
            time.sleep(1.4)  # Let content load

            # 2. Find ONLY VISIBLE quarter blocks
            btn_blocks = driver.find_elements(By.CSS_SELECTOR, "div.document__btn--1")
            found = False
            for block in btn_blocks:
                if not block.is_displayed():
                    continue
                try:
                    a = block.find_element(By.CSS_SELECTOR, "a.document__btn[title='Yüklə']")
                    qtext = a.text.strip()  # "I rüb", "II rüb", etc
                    quarter = normalize_quarter(qtext)
                    href = a.get_attribute("href")
                    if not href or not href.endswith(".xlsx") or not quarter.startswith("Q"):
                        continue
                    period = f"{yyyy}_{quarter}"
                    folder = os.path.join(RAW_DATA_DIR, period)
                    os.makedirs(folder, exist_ok=True)
                    filename = f"unibank_{year}_{quarter}.xlsx"
                    fpath = os.path.join(RAW_DATA_DIR, filename)
                    if os.path.exists(fpath):
                        report.append(f"[OK] {filename} (already exists)")
                        found = True
                        continue
                    url = "https://unibank.az" + href if href.startswith("/") else href
                    print(f"    Downloading: {filename}")
                    r = session.get(url, headers=headers, timeout=25)
                    if r.status_code == 200 and r.content[:2] == b'PK':
                        with open(fpath, "wb") as out:
                            out.write(r.content)
                        report.append(f"[OK] {filename}")
                        total_downloaded += 1
                        found = True
                    else:
                        report.append(f"[SKIP_CORRUPT] {filename}")
                except Exception as e:
                    report.append(f"[ERROR] {year} {quarter}: {e}")
            if not found:
                report.append(f"[SKIP] No reports found for {year}")
        except Exception as e:
            report.append(f"[SKIP] Year {year}: {e}")

    print("\n=== UNIBANK FULL REPORT ===")
    for line in report:
        print(line)
    print("\nSUMMARY REPORT")
    print(f"Total files downloaded: {total_downloaded}")
    missing = len([l for l in report if l.startswith('[SKIP') or l.startswith('[ERROR')])
    print(f"Missing/Skipped: {missing}")
    driver.quit()

if __name__ == "__main__":
    main()
