import os
import time
import re
import requests
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from collections import defaultdict

BASE_URL = "https://www.kapitalbank.az/en/reports"
RAW_DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'raw_data', 'kapital_bank')
os.makedirs(RAW_DATA_DIR, exist_ok=True)

def slugify(text):
    return re.sub(r'[\W_]+', '_', text).lower()

def is_real_pdf(r):
    # 1. Status check
    if r.status_code != 200:
        return False
    # 2. Header check
    ctype = r.headers.get('Content-Type', '').lower()
    if not (ctype.startswith('application/pdf') or ctype.startswith('application/octet-stream')):
        return False
    # 3. Magic bytes check
    return r.content[:5] == b'%PDF-'

def main():
    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    driver = uc.Chrome(options=options)
    driver.get(BASE_URL)
    time.sleep(3)

    # Accept cookies
    try:
        accept_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Accept')]")
        accept_btn.click()
        print("Accepted cookie banner.")
    except Exception:
        print("No cookie banner or already accepted.")

    time.sleep(2)

    # Prepare a requests session with Selenium cookies
    session = requests.Session()
    for cookie in driver.get_cookies():
        session.cookies.set(cookie['name'], cookie['value'])
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": BASE_URL
    }

    accordion_titles = driver.find_elements(By.CSS_SELECTOR, ".accordion--pls--title")
    print(f"Found {len(accordion_titles)} quarter blocks.")

    q_map = {"I": "Q1", "II": "Q2", "III": "Q3", "IV": "Q4"}
    global_stats = defaultdict(int)
    global_stats_types = defaultdict(int)
    per_quarter_stats = []
    empty_quarters = []

    for idx, title_elem in enumerate(accordion_titles):
        quarter_title = title_elem.text.strip()
        print(f"\nProcessing {quarter_title} [{idx+1}/{len(accordion_titles)}]")
        m = re.search(r"([IV]+)\s*quarter,?\s*(\d{4})", quarter_title)
        if not m:
            continue
        quarter_roman, year = m.group(1), m.group(2)
        quarter = q_map.get(quarter_roman, quarter_roman)
        if int(year) < 2020:
            continue

        try:
            driver.execute_script("arguments[0].scrollIntoView();", title_elem)
            ActionChains(driver).move_to_element(title_elem).perform()
            if not title_elem.get_attribute("aria-expanded") or title_elem.get_attribute("aria-expanded") == "false":
                title_elem.click()
            time.sleep(1.0)
        except Exception as e:
            print(f"  [!] Could not click: {e}")
            continue

        # Find downloadable links
        try:
            panel_wrap = title_elem.find_element(By.XPATH, "./ancestor::div[contains(@class,'border-bottom-2')]")
            links = panel_wrap.find_elements(By.XPATH, ".//a[@href]")
            file_links = []
            stats_types = defaultdict(int)
            for a in links:
                href = a.get_attribute("href")
                text = a.text.strip()
                ext_match = re.search(r'\.([a-z0-9]+)(?:\?|$)', href, re.IGNORECASE)
                if href and ext_match and ext_match.group(1) in ['pdf', 'xlsx', 'xls', 'csv']:
                    ext = ext_match.group(1).lower()
                    file_links.append((href, text, ext))
                    stats_types[ext] += 1
                    global_stats_types[ext] += 1

            nfiles = len(file_links)
            global_stats["total"] += nfiles
            per_quarter_stats.append((f"{year}_{quarter}", nfiles, dict(stats_types)))
            if nfiles == 0:
                empty_quarters.append(f"{year}_{quarter}")
            print(f"  Found {nfiles} downloadable file links.")

            save_dir = os.path.join(RAW_DATA_DIR, f"{year}_{quarter}")
            os.makedirs(save_dir, exist_ok=True)
            for href, text, ext in file_links:
                fname = slugify(text or "report") + '.' + ext
                fpath = os.path.join(save_dir, fname)
                try:
                    print(f"    Downloading: {href}")
                    # Always get fresh cookies for each download
                    session.cookies.clear()
                    for cookie in driver.get_cookies():
                        session.cookies.set(cookie['name'], cookie['value'])
                    r = session.get(href, headers=headers, timeout=15)
                    # For PDF, check that it's real before saving
                    if ext == 'pdf':
                        if not is_real_pdf(r):
                            print(f"    [!] Not a real PDF (skipped): {href}")
                            continue
                    # For Excel, check first bytes for 'PK' (xlsx)
                    elif ext in ('xlsx', 'xls'):
                        if not (r.content[:2] == b'PK'):
                            print(f"    [!] Not a real Excel (skipped): {href}")
                            continue
                    with open(fpath, "wb") as out:
                        out.write(r.content)
                except Exception as e:
                    print(f"    [!] Download error: {e}")

        except Exception as e:
            print(f"  [!] No links found or could not expand: {e}")
            empty_quarters.append(f"{year}_{quarter}")
            per_quarter_stats.append((f"{year}_{quarter}", 0, {}))
            continue

        time.sleep(0.4)

    driver.quit()

    # ---- SUMMARY REPORT ----
    print("\n\n========== SUMMARY ==========")
    print(f"Total quarters processed: {len(per_quarter_stats)}")
    print(f"Total files downloaded: {global_stats['total']}")
    print("Breakdown by file type:")
    for ext, count in global_stats_types.items():
        print(f"  .{ext}: {count}")
    print("\nPer quarter:")
    for name, nfiles, type_dict in per_quarter_stats:
        type_str = ', '.join([f"{k}: {v}" for k, v in type_dict.items()]) or "None"
        print(f"  {name} — {nfiles} files  ({type_str})")
    if empty_quarters:
        print("\nQuarters with **NO** downloadable files:")
        for q in empty_quarters:
            print(" ", q)
    print("========== END ==========")

if __name__ == "__main__":
    main()
