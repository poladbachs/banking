# -*- coding: utf-8 -*-
import os
import re
import time
import requests
import unidecode
import undetected_chromedriver as uc
from bs4 import BeautifulSoup
from collections import defaultdict
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains

BASE_URL = "https://abb-bank.az/az/hesabatlar"
RAW_DATA_DIR = os.path.join("raw_data", "abb_bank")
os.makedirs(RAW_DATA_DIR, exist_ok=True)

# ---- RANGE: 2020 Q1 -> open-ended future ----
MIN_YEAR = 2020
MAX_YEAR = None
MAX_QUARTER = None

# ---- CANONICAL TYPES (exactly what to keep) ----
CORE_REPORTS = [
    "balance_sheet",       # Maliyyə vəziyyəti
    "profit_and_loss",     # Mənfəət və zərər
    "capital_adequacy",    # Kapital adekvatlığı
    "portfolio_share",     # Portfel bölgüsü
    "credit_risk",         # Kredit riski (təminat üzrə bölgüsü)
    "currency_risk",       # Valyuta riski
]

# Header labels are flaky; we do NOT filter by headers anymore.
# We'll expand all sections and classify each PDF by its own text.

ROMAN_TO_Q = {"I": "Q1", "II": "Q2", "III": "Q3", "IV": "Q4"}
MONTH_TO_Q = {
    "yanvar": "Q1", "fevral": "Q1", "mart": "Q1",
    "aprel": "Q2", "may": "Q2", "iyun": "Q2",
    "iyul": "Q3", "avqust": "Q3", "sentyabr": "Q3",
    "oktyabr": "Q4", "noyabr": "Q4", "dekabr": "Q4",
}

# --- text utilities ---
def _strip_weird_ws(s: str) -> str:
    # remove NBSP and zero-width chars that break matching
    if not s:
        return ""
    return re.sub(r"[\u00A0\u200B\u200C\u200D\u202F]", " ", s)

def normalize(s: str) -> str:
    t = _strip_weird_ws(s or "")
    t = unidecode.unidecode(t)
    t = re.sub(r"\s+", " ", t)
    return t.strip().lower()

# --- quarter parsing ---
def guess_quarter_from_months(text_norm: str):
    months = [m for m in MONTH_TO_Q.keys() if m in text_norm]
    if not months:
        return None
    last = None
    last_pos = -1
    for m in months:
        p = text_norm.rfind(m)
        if p > last_pos:
            last_pos = p
            last = m
    return MONTH_TO_Q.get(last)

def extract_year_quarter(label_text: str):
    norm = normalize(label_text)
    y = re.search(r"\b(20\d{2})\b", norm)
    year = int(y.group(1)) if y else None

    q = None
    m = re.search(r"\b(i{1,3}v?)\s*rub\b", norm)  # "rüb" -> "rub" via unidecode
    if m:
        q = ROMAN_TO_Q.get(m.group(1).upper())

    if not q:
        if re.search(r"\b3\s*ay\b", norm):
            q = "Q1"
        elif re.search(r"\b6\s*ay\b", norm) or "yarimillik" in norm:
            q = "Q2"
        elif re.search(r"\b9\s*ay\b", norm):
            q = "Q3"
        elif re.search(r"\b12\s*ay\b", norm) or "illik" in norm:
            q = "Q4"

    if not q:
        q = guess_quarter_from_months(norm)

    return year, q

def in_upper_bound(year: int, quarter: str) -> bool:
    if MAX_YEAR is None:
        return True
    if year < MAX_YEAR:
        return True
    if year > MAX_YEAR:
        return False
    if MAX_QUARTER is None:
        return True
    order = {"Q1":1,"Q2":2,"Q3":3,"Q4":4}
    return order.get(quarter, 0) <= order.get(MAX_QUARTER, 4)

def ensure_period_dir(year: int, quarter: str):
    period = f"{year}_{quarter}"
    path = os.path.join(RAW_DATA_DIR, period)
    os.makedirs(path, exist_ok=True)
    return period, path

def already_downloaded(period, fname):
    return os.path.exists(os.path.join(RAW_DATA_DIR, period, fname))

# --- classify by link text ONLY (don’t trust headers) ---
def detect_report_type(context_norm: str):
    """
    Decide which of the 6 canonical types this PDF is.
    Return one of CORE_REPORTS or None.
    """
    # 1) Financial statements: exact phrases appear in link blocks
    if ("maliyye veziyyeti" in context_norm) or ("maliyye veziyyeti haqqinda" in context_norm):
        return "balance_sheet"
    # include the unicode version too (normalize() makes ASCII, but context might be raw in some cases)
    if "maliyyə vəziyyəti" in _strip_weird_ws(context_norm):
        return "balance_sheet"

    if ("menfeet ve zerer" in context_norm) or ("menfeet ve zerer haqqinda" in context_norm):
        return "profit_and_loss"
    if "mənfəət və zərər" in _strip_weird_ws(context_norm):
        return "profit_and_loss"

    # 2) Capital adequacy
    if "kapital adekvatligi" in context_norm or "adekvatliq" in context_norm:
        return "capital_adequacy"

    # 3) Risk subtypes we want (credit, currency, portfolio) — explicitly exclude interest rate risk
    if "faiz riski" in context_norm:
        return None  # skip interest rate risk entirely

    # Credit risk (be generous; ABB uses multiple wordings)
    if ("kredit riski" in context_norm) or ("kreditlerin" in context_norm) or ("kreditlerin teminat uzre bolgusu" in context_norm):
        # Prefer only items that look like "Kredit riski - kreditlərin təminat üzrə bölgüsü"
        # but allow looser forms too
        return "credit_risk"

    # Currency risk
    if ("valyuta riski" in context_norm) or ("xarici valyuta" in context_norm):
        return "currency_risk"

    # Portfolio share / segmentation
    if ("portfel" in context_norm) or ("portfolio" in context_norm) or ("iqtisadi bolgu" in context_norm) or ("bolgusu" in context_norm):
        return "portfolio_share"

    return None

# --- DOM helpers ---
def find_section_body_for_header(header_el):
    """Walk forward siblings until the body (class contains 'ac-a') or next header."""
    siblings = header_el.find_elements(By.XPATH, "following-sibling::*")
    for sib in siblings:
        cls = (sib.get_attribute("class") or "").lower()
        tag = sib.tag_name.lower()
        if "ac-a" in cls:
            return sib
        if tag == "h4" and "ac-q" in cls:
            break
    return None

def pull_pdf_links_from_section_html(section_html: str):
    """Return list[(href, context_text)] for each .pdf inside a section body."""
    soup = BeautifulSoup(section_html, "html.parser")
    out = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href.lower().endswith(".pdf"):
            continue
        # context: prefer outer card text, else link text
        parent = a
        context = ""
        hops = 0
        while parent and hops < 7:
            text = parent.get_text(" ", strip=True) or ""
            # take the longest reasonable text chunk
            if len(text) > len(context):
                context = text
            parent = parent.parent
            hops += 1
        if not context:
            context = a.get_text(" ", strip=True)
        out.append((href, context))
    return out

def main():
    # --- Selenium (uc) to load the hub and get session cookies ---
    options = uc.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    driver = uc.Chrome(options=options)
    driver.get(BASE_URL)
    time.sleep(2)

    # best-effort: accept cookies / close overlays
    try:
        for xp in [
            "//button[contains(.,'Qəbul et')]",
            "//button[contains(.,'Accept')]",
            "//button[contains(.,'Bağla')]",
        ]:
            els = driver.find_elements(By.XPATH, xp)
            if els:
                els[0].click()
                time.sleep(0.7)
                break
    except Exception:
        pass

    # click "Digər hesabatlar" to reveal more blocks
    try:
        other = driver.find_element(By.XPATH, "//span[contains(.,'Digər hesabatlar') or contains(.,'Diger hesabatlar')]")
        other.click()
        time.sleep(1.2)
    except Exception:
        pass

    # Scroll to mount everything
    try:
        last_h = 0
        for _ in range(8):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.6)
            h = driver.execute_script("return document.body.scrollHeight;")
            if h == last_h:
                break
            last_h = h
    except Exception:
        pass

    # mirror cookies to requests for faster, reliable PDF download
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML like Gecko) Chrome/124 Safari/537.36",
        "Referer": BASE_URL,
    })
    for c in driver.get_cookies():
        session.cookies.set(c["name"], c["value"])

    headers = driver.find_elements(By.CSS_SELECTOR, "h4.ac-q")
    print(f"Found {len(headers)} report sections.")

    quarter_files = defaultdict(set)
    total_new = 0

    for i, h in enumerate(headers, 1):
        title_raw = (h.text or "").strip()
        print(f"\n[{i}] header: {title_raw}")

        # Always expand — regardless of header text
        try:
            if h.get_attribute("aria-expanded") in (None, "false"):
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", h)
                ActionChains(driver).move_to_element(h).perform()
                h.click()
                time.sleep(0.9)
        except Exception:
            pass

        body = find_section_body_for_header(h)
        if not body:
            print(f"    [WARN] no section body found.")
            continue

        items = pull_pdf_links_from_section_html(body.get_attribute("innerHTML") or "")
        print(f"    links: {len(items)} PDF(s)")

        for href, context in items:
            if href.startswith("/"):
                href = "https://abb-bank.az" + href

            # try parse period
            year, quarter = extract_year_quarter(context)
            if (year is None) or (quarter is None):
                # parse from filename if needed
                fn_norm = normalize(os.path.basename(href))
                y = re.search(r"(20\d{2})", fn_norm)
                if y and not year:
                    year = int(y.group(1))
                r = re.search(r"\b(i{1,3}v?)\b", fn_norm)
                if r and not quarter:
                    quarter = ROMAN_TO_Q.get(r.group(1).upper())
                if not quarter:
                    if re.search(r"[_-]3\b", fn_norm): quarter = "Q1"
                    elif re.search(r"[_-]6\b", fn_norm): quarter = "Q2"
                    elif re.search(r"[_-]9\b", fn_norm): quarter = "Q3"
                    elif re.search(r"[_-]12\b", fn_norm): quarter = "Q4"

            if (year is None) or (quarter is None):
                print(f"      [SKIP] no year/quarter -> {context[:120]} ...")
                continue

            if year < MIN_YEAR or not in_upper_bound(year, quarter):
                print(f"      [SKIP] outside lower bound: {year} {quarter}")
                continue

            # Decide the exact type from the link text itself
            context_norm = normalize(context)
            rtype = detect_report_type(context_norm)

            if rtype not in CORE_REPORTS:
                # Explicitly refuse to save interest rate risk or generic 'risk reports'
                # or cash flow etc.
                # Uncomment the next line to debug what we skipped:
                # print(f"      [SKIP] not in CORE_REPORTS -> {context[:120]} ...")
                continue

            period, pdir = ensure_period_dir(year, quarter)
            save_name = f"{rtype}_{year}_{quarter}.pdf"
            if already_downloaded(period, save_name):
                quarter_files[period].add(rtype)
                continue

            try:
                print(f"      ↓ {period}/{save_name}")
                dr = session.get(href, timeout=50, allow_redirects=True)
                ok_pdf = (dr.status_code == 200 and (
                    dr.content.startswith(b"%PDF") or
                    "application/pdf" in (dr.headers.get("Content-Type","").lower())
                ))
                if ok_pdf:
                    with open(os.path.join(pdir, save_name), "wb") as f:
                        f.write(dr.content)
                    total_new += 1
                    quarter_files[period].add(rtype)
                else:
                    print(f"        [WARN] not a PDF or HTTP {dr.status_code}: {href}")
            except Exception as e:
                print(f"        [ERR] {e}")

    driver.quit()

    # include any preexisting files in the summary
    for sub in os.listdir(RAW_DATA_DIR):
        p = os.path.join(RAW_DATA_DIR, sub)
        if not os.path.isdir(p):
            continue
        for fname in os.listdir(p):
            m = re.match(r"([a-z_]+)_(20\d{2})_(Q[1-4])\.pdf$", fname)
            if m:
                quarter_files[sub].add(m.group(1))

    print("\n=== SUMMARY OF MISSING REPORTS PER QUARTER (>= {0}) ===".format(MIN_YEAR))
    for quarter in sorted(quarter_files.keys()):
        got = quarter_files[quarter]
        miss = [k for k in CORE_REPORTS if k not in got]
        if miss:
            print(f"  {quarter}: missing {miss}")
    print(f"\nDone. New files: {total_new}")
    print("All PDFs in raw_data/abb_bank/<year>_<quarter>/")

if __name__ == "__main__":
    main()
