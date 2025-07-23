import os
import re
import time
import requests
from selenium.webdriver.common.by import By
import undetected_chromedriver as uc

BASE_URL = "https://unibank.az/az/documents/quarterlyReports"
PROCESSED_ROOT = os.path.join("processed_data", "unibank")
os.makedirs(PROCESSED_ROOT, exist_ok=True)

def normalize_quarter(text):
    roman_map = {"I": "Q1", "II": "Q2", "III": "Q3", "IV": "Q4"}
    text = text.upper().replace("RÜB", "").strip()
    return roman_map.get(text, text.replace(" ", "_"))

def file_exists_anywhere(root, fname):
    for dirpath, _, files in os.walk(root):
        if fname in files:
            return True
    return False

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
    years = []
    # Get all available years dynamically
    for year_tab in driver.find_elements(By.CSS_SELECTOR, "a[data-year]"):
        y = year_tab.get_attribute("data-year")
        if y and y.isdigit():
            years.append(int(y))
    years = sorted(list(set(years)), reverse=True)

    # To record what we have on disk later
    all_quarters = set()
    for year in years:
        try:
            # Click year tab
            year_tab = driver.find_element(By.XPATH, f"//a[@data-year='{year}']")
            driver.execute_script("arguments[0].scrollIntoView(true);", year_tab)
            year_tab.click()
            time.sleep(1.4)
            btn_blocks = driver.find_elements(By.CSS_SELECTOR, "div.document__btn--1")
            found_any = False
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
                    subfolder = f"{year}_{quarter}"
                    save_name = f"unibank_{year}_{quarter}.xlsx"
                    period_dir = os.path.join(PROCESSED_ROOT, subfolder)
                    os.makedirs(period_dir, exist_ok=True)
                    fpath = os.path.join(period_dir, save_name)
                    all_quarters.add((year, quarter))
                    if file_exists_anywhere(PROCESSED_ROOT, save_name):
                        report.append(f"[SKIP] Already exists: {subfolder}/{save_name}")
                        found_any = True
                        continue
                    url = "https://unibank.az" + href if href.startswith("/") else href
                    print(f"    Downloading: {subfolder}/{save_name}")
                    r = session.get(url, headers=headers, timeout=25)
                    if r.status_code == 200 and r.content[:2] == b'PK':
                        with open(fpath, "wb") as out:
                            out.write(r.content)
                        report.append(f"[OK] {subfolder}/{save_name}")
                        total_downloaded += 1
                        found_any = True
                    else:
                        report.append(f"[SKIP_CORRUPT] {subfolder}/{save_name}")
                except Exception as e:
                    report.append(f"[ERROR] {year} {quarter}: {e}")
            if not found_any:
                report.append(f"[SKIP] No reports found for {year}")
        except Exception as e:
            report.append(f"[SKIP] Year {year}: {e}")

    print("\n=== UNIBANK FULL REPORT ===")
    for line in report:
        print(line)

    # Scan all present files on disk for missing report
    present_files = set()
    for dirpath, _, files in os.walk(PROCESSED_ROOT):
        for fname in files:
            m = re.match(r"unibank_(\d{4})_(Q[1-4])\.xlsx", fname)
            if m:
                present_files.add((int(m.group(1)), m.group(2)))
    if not all_quarters:
        # In case no quarters were found on site, build all combinations for present years
        for year in years:
            for q in ["Q1", "Q2", "Q3", "Q4"]:
                all_quarters.add((year, q))

    print("\n=== SUMMARY OF MISSING REPORTS PER YEAR/QUARTER ===")
    for y, q in sorted(all_quarters, reverse=True):
        if (y, q) not in present_files:
            print(f"{y}_{q}: MISSING unibank_{y}_{q}.xlsx")
    print("Done.\nAll Excels in processed_data/unibank/<year>_<quarter>/")
    driver.quit()

if __name__ == "__main__":
    main()
