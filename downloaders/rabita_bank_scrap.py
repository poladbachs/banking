import os
import re
import requests
from urllib.parse import urljoin
from bs4 import BeautifulSoup

BASE = "https://www.rabitabank.com"
OUTDIR = os.path.join("processed_data", "rabitabank")
os.makedirs(OUTDIR, exist_ok=True)

CORE_9 = {
    "balance_sheet":     [["maliyy", "veziyyet"]],
    "capital_adequacy":  [["kapital", "adekvat"]],
    "profit_loss":       [["menfeet", "zerer"]],
    "capital_change":    [["kapital", "struktur", "deyis"]],
    "cash_flow":         [["pul", "axin"], ["pul", "vesait", "hereket"]],
    "credit_risk":       [["kredit", "risk"]],
    "liquidity_risk":    [["likvidlik", "risk"]],
    "currency_risk":     [["valyuta", "risk"]],
    "interest_rate_risk":[["faiz", "risk"]],
}

def normalize(text):
    rep = (
        ("ə", "e"), ("ı", "i"), ("ü", "u"), ("ö", "o"), ("ç", "c"), ("ş", "s"), ("ğ", "g"),
        ("İ", "i"), ("Ü", "u"), ("Ö", "o"), ("Ç", "c"), ("Ş", "s"), ("Ğ", "g"),
        ("â", "a"), ("î", "i"), ("û", "u")
    )
    text = text.lower()
    for a, b in rep:
        text = text.replace(a, b)
    text = re.sub(r'[^a-z0-9 ]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text

def matches_keywords(label):
    t = normalize(label)
    for en, keywords_sets in CORE_9.items():
        for kw_set in keywords_sets:
            if all(kw in t for kw in kw_set):
                return en
    return None

def extract_quarter(label):
    m = re.search(r'([IVX]+)\s*[-–,]?\s*[rüub]+', label, re.I)
    if not m: return None
    roman = m.group(1).replace("X", "10").upper()
    mapping = {"I": "Q1", "II": "Q2", "III": "Q3", "IV": "Q4"}
    return mapping.get(roman)

def extract_year_from_url(url):
    m = re.search(r'reports[-_](\d{4})', url)
    if m: return m.group(1)
    m2 = re.search(r'(\d{4})-ci-ilin-hesabatlari', url)
    if m2: return m2.group(1)
    return None

def main():
    session = requests.Session()
    possible_menus = [
        "https://www.rabitabank.com/other/reports/quarterly-reports/reports-2025",
        "https://www.rabitabank.com/diger/hesabatlar/rubluk-hesabatlar/2025-ci-ilin-hesabatlari"
    ]
    year_links = set()
    for menu_url in possible_menus:
        try:
            r = session.get(menu_url, timeout=20)
            soup = BeautifulSoup(r.content, "html.parser")
            for a in soup.select("ul.reports-other__filters a"):
                href = a.get("href")
                if href and ("reports" in href or "hesabatlar" in href):
                    year_links.add(href)
        except Exception as e:
            print(f"[ERROR] couldn't fetch {menu_url}: {e}")

    # { period: {core_name: present_bool} }
    status = {}
    for year_url in year_links:
        year_full_url = year_url if year_url.startswith("http") else urljoin(BASE, year_url)
        year = extract_year_from_url(year_url)
        if not year or int(year) < 2020:
            continue
        try:
            rr = session.get(year_full_url, timeout=20)
        except Exception as e:
            print(f"[ERROR] could not fetch {year_full_url}: {e}")
            continue
        ss = BeautifulSoup(rr.content, "html.parser")
        for item in ss.select("div.reports-other__item"):
            label_tag = item.select_one("h4.reports-other__title")
            if not label_tag:
                continue
            label = label_tag.get_text(strip=True)
            en_name = matches_keywords(label)
            if not en_name:
                continue
            quarter = extract_quarter(label)
            if not quarter or not year:
                continue
            period = f"{year}_{quarter}"
            fname = f"{en_name}_{year}_{quarter}.xlsx"
            period_dir = os.path.join(OUTDIR, period)
            os.makedirs(period_dir, exist_ok=True)
            path = os.path.join(period_dir, fname)
            if os.path.exists(path):
                print(f"[SKIP] Already exists: {period}/{fname}")
                status.setdefault(period, {})[en_name] = True
                continue
            # Download
            a = item.find("a", class_="reports-other__link")
            if not a or not a.get("href"):
                continue
            file_url = urljoin(BASE, a["href"])
            print(f"Downloading {en_name} for {period} -> {fname}")
            try:
                file_r = session.get(file_url, timeout=30)
                with open(path, "wb") as out:
                    out.write(file_r.content)
                status.setdefault(period, {})[en_name] = True
            except Exception as e:
                print(f"[ERROR] {file_url}: {e}")

    # --------- FIX: Now rescan ALL folders for ALL files (even if manually added) ---------
    for period_folder in os.listdir(OUTDIR):
        abs_period = os.path.join(OUTDIR, period_folder)
        if not os.path.isdir(abs_period):
            continue
        for core in CORE_9:
            expected = f"{core}_{period_folder}.xlsx"
            if os.path.exists(os.path.join(abs_period, expected)):
                status.setdefault(period_folder, {})[core] = True

    # Check for all 9 reports in each period
    print("\n=== SUMMARY OF MISSING REPORTS PER QUARTER ===")
    all_periods = sorted(os.listdir(OUTDIR))
    for period in all_periods:
        period_path = os.path.join(OUTDIR, period)
        if not os.path.isdir(period_path):
            continue
        present = set(status.get(period, {}).keys())
        missing = [c for c in CORE_9.keys() if c not in present]
        if missing:
            print(f"{period}: missing {missing}")
        else:
            print(f"{period}: all 9 core reports present")

    print("\nDone.")

if __name__ == "__main__":
    main()


### MAYBE DECOMPOSE 2020 Q1 RABITA BANK INTO REPROT TYPES IDK