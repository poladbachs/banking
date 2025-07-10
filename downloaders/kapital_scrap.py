import os
import time
import re
import requests
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from collections import defaultdict
import sys
from urllib.parse import unquote, urlparse

# Ensure terminal print supports unicode (for macOS and Python 3.7+)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "https://www.kapitalbank.az/reports"
RAW_DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'raw_data', 'kapital_bank')
os.makedirs(RAW_DATA_DIR, exist_ok=True)

AZ_TO_EN = {
    "Mənfəət və zərər": "profit_and_loss",
    "Pul vəsaitlərinin hərəkəti": "cash_flows",
    "Kapital dəyişmələri": "changes_in_equity",
    "Kapital adekvatlığı": "capital_adequacy",
    "Ödəniş müddətlərinin bölgüsü barədə məlumat": "payment_terms",
    "Digər ümumi məlumatlar": "other_general_info",
    "Balans hesabatı": "balance_sheet"
}

def is_real_pdf(r):
    if r.status_code != 200:
        return False
    ctype = r.headers.get('Content-Type', '').lower()
    if not (ctype.startswith('application/pdf') or ctype.startswith('application/octet-stream')):
        return False
    return r.content[:5] == b'%PDF-'

def clean_for_header(val):
    # Only allow latin-1 chars for HTTP headers/cookies (per HTTP/1.x spec)
    if isinstance(val, str):
        return val.encode("latin-1", "ignore").decode("latin-1")
    return val

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
        # Clean value to latin-1 before setting as header
        session.cookies.set(cookie['name'], clean_for_header(cookie['value']))
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
        m = re.search(r"([IV]+)\s*rüb,?\s*(\d{4})", quarter_title, re.IGNORECASE)
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
                # Try AZ mapping first
                base_name = None
                # Use Azerbaijani base name (before _az_ or just text)
                if "_az_" in href:
                    # Sometimes the link has .../Mənfəət və zərər_az_1730360141.pdf
                    try:
                        base_candidate = os.path.basename(href)
                        base_candidate = unquote(base_candidate)
                        base_candidate = base_candidate.split("_az_")[0]
                        base_name = AZ_TO_EN.get(base_candidate, None)
                    except Exception:
                        base_name = None
                if not base_name and text:
                    base_name = AZ_TO_EN.get(text, None)
                if not base_name:
                    # Fallback: use URL filename (decoded)
                    url_fname = os.path.basename(urlparse(href).path)
                    base_name = unquote(url_fname).rsplit('.', 1)[0]
                fname = f"{base_name}_{year}_{quarter}.{ext}"
                fpath = os.path.join(save_dir, fname)
                print(f"    Downloading: {href} as {fname}")
                try:
                    session.cookies.clear()
                    for cookie in driver.get_cookies():
                        session.cookies.set(cookie['name'], clean_for_header(cookie['value']))
                    r = session.get(href, headers=headers, timeout=15)
                    if ext == 'pdf':
                        if not is_real_pdf(r):
                            print(f"    [!] Not a real PDF (skipped): {href}")
                            continue
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
