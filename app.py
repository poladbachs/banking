import os
import subprocess
import base64
import streamlit as st
import io, zipfile
from datetime import datetime
import re

# ---- CONFIG ----
st.set_page_config(
    page_title="PASHA Holding Data Automation Suite",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ---- APP CONSTANTS ----
BANKS = [
    ("ABB", "abb_bank"),
    ("Kapital Bank", "kapital_bank"),
    ("Pasha Bank", "pasha_bank"),
    ("Xalq Bank", "xalq_bank"),
    ("Unibank", "unibank"),
    ("Bank Respublika", "bank_respublika"),
    ("Access Bank", "access_bank"),
    ("Rabita Bank", "rabitabank"),
    ("Yelo Bank", "yelobank"),
    ("Bank of Baku", "bank_of_baku"),
    ("CBAR", "cbar"),
]
ARRANGERS = [
    ("pasha_bank", "arrangers/pasha_arrange.py"),
    ("kapital_bank", "arrangers/kapital_arrange.py"),
    ("yelobank", "arrangers/yelobank_arrange.py"),
    ("access_bank", "arrangers/accessbank_arrange.py"),
    ("xalq_bank", "arrangers/xalq_arrange.py"),
    ("abb_bank", "arrangers/abb_arrange.py"),
]
SCRAPERS = [
    "downloaders/pasha_scrap.py",
    "downloaders/kapital_scrap.py",
    "downloaders/yelobank_scrap.py",
    "downloaders/bank_of_baku_scrap.py",
    "downloaders/bank_respublika_scrap.py",
    "downloaders/unibank_scrap.py",
    "downloaders/accessbank_scrap.py",
    "downloaders/abb_scrap.py",
    "downloaders/rabita_bank_scrap.py",
    "downloaders/xalq_scrap.py",
    "downloaders/cbar_scrap.py",
]

def zip_processed_data():
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zipf:
        for root, _, files in os.walk("processed_data"):
            for file in files:
                fpath = os.path.join(root, file)
                arcname = os.path.relpath(fpath, "processed_data")
                zipf.write(fpath, arcname)
    zip_buffer.seek(0)
    return zip_buffer

def all_banks_fully_arranged():
    for _, folder in BANKS:
        if needs_acrobat(folder) or needs_arrange(folder) or not is_fully_arranged(folder):
            return False
    return True

def load_logo_b64(path):
    if not os.path.exists(path):
        return None
    data = open(path, "rb").read()
    return base64.b64encode(data).decode()

logo_b64 = load_logo_b64("Pasha_Holding_logo.png")

# ---- BANK LOGO UTILS ----
def get_bank_logo_b64(folder_key):
    if not os.path.exists("logos"):
        return None
    patterns = [
        f"{folder_key}.png",
        f"{folder_key}_logo.png",
        f"{folder_key.capitalize()}.png",
        f"{folder_key.capitalize()}_Logo.png",
        f"{folder_key.replace('_', '')}.png",
        f"{folder_key.replace('_', '').capitalize()}.png"
    ]
    for pattern in patterns:
        path = os.path.join("logos", pattern)
        if os.path.exists(path):
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode()
    for fname in os.listdir("logos"):
        if folder_key.replace("_", "").lower() in fname.lower() and fname.lower().endswith(".png"):
            path = os.path.join("logos", fname)
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode()
    return None

def render_bank_row(badge_html, folder, name):
    logo_b64 = get_bank_logo_b64(folder)
    logo_html = f"<img src='data:image/png;base64,{logo_b64}' style='height:25px;vertical-align:middle;margin-right:10px;border-radius:5px;'>" if logo_b64 else ""
    return f"{badge_html} {logo_html}<b>{name}</b>"

# ---- NEON DARK CSS ----
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
[data-testid="stAppViewContainer"] {
  background: #171720 !important;
  color: #E0E0E0;
  font-family: 'Inter', sans-serif !important;
}
.block-container {
  background: #232340 !important;
  border: 1px solid #34345A !important;
  border-radius: 1rem !important;
  padding: 2rem !important;
  max-width: 900px;
  margin: 2rem auto;
  box-shadow: 0 8px 24px rgba(0,0,0,0.70);
}
h1, h2, h3 { color: #fff !important; font-weight: 800 !important; }
.stButton>button {
  background: linear-gradient(90deg, #00FFA3, #DC1FFF) !important;
  color: #1E1E2E !important;
  border: none;
  border-radius: 0.75rem;
  padding: 0.65rem 1.6rem;
  font-weight: 600;
  font-size: 1.14rem;
  transition: 0.18s;
}
.stButton>button:hover {
  transform: translateY(-3px) scale(1.035);
  box-shadow: 0 7px 26px rgba(220,31,255,0.34);
}
.status-badge {
  font-weight:700;
  border-radius:7px;
  padding: 0.12em 0.73em;
  margin-right:0.6em;
  font-size:1.08em;
  letter-spacing:0.03em;
  background: #242c40;
  box-shadow: 0 2px 9px #00FFA366;
  color:#00FFA3;
  display:inline-block;
}
.status-badge.arrange { color:#FFEF00;background:#333220;box-shadow:0 1px 9px #fff13377;}
.status-badge.error { color:#FF4E85;background:#452233;box-shadow:0 1px 9px #ff1c6640;}
.status-badge.skip { color:#55A3FF;background:#23394a;}
.expander-badge { 
    font-size: 1em;
    margin: 5px 8px 5px 0;
    border-radius: 6px;
    padding: 2px 12px;
    font-weight: 600;
    display: inline-block;
    color: #191b23;
    background: #C8FCEA;
    border: 1px solid #86ffd2;
    box-shadow: 0 1px 3px #00FFA366;
}
.expander-badge.ready { background: #8effb8; color: #1a2922; border-color: #39e48b; }
.expander-badge.arrange { background: #fff799; color: #695c13; border-color: #ffe054; }
.expander-badge.acrobat { background: #ffe1e8; color: #b50045; border-color: #ff74a7; }
.expander-badge.missing { background: #f1f2f6; color: #5a5a5a; border-color: #d0d3d7; }

.quarters-grid {
    display: flex;
    flex-wrap: wrap;
    gap: 8px 9px;
    margin: 4px 0 0 0;
    padding-bottom: 2px;
}

.stExpanderHeader { color: #00FFA3!important; font-weight:700!important; }
.inline-expander details summary {
    cursor: pointer;
    outline: none;
    font-size: 1em;
    font-weight: 700;
    color: #00FFA3;
    display: inline;
}
.inline-expander details[open] summary {
    color: #DC1FFF;
}
.inline-expander details {
    display: inline-block;
    margin-left: 16px;
    vertical-align: middle;
}
hr { border: none; height:1px; background: #33334A; margin: 2.1rem 0; }
.footer-custom {
    margin-top: 4em; color: #a2a9b7; font-weight: 500; font-size: 1.09em; text-align: center;
}
.rotating-logo {
  animation: spin 9s linear infinite;
  display: block;
  height: 110px;
  margin-bottom: 5px;
  margin-left:auto; margin-right:auto;
}
@keyframes spin {from{transform:rotate(0deg);}to{transform:rotate(360deg);}
}
a.neon-btn {
  display: inline-block;
  padding: 0.7rem 1.7rem;
  background: #00FFA3;
  color: #1E1E2E!important;
  border-radius: 0.75rem;
  font-weight:600;
  text-decoration:none;
  box-shadow: 0 4px 12px rgba(0,255,163,0.45);
  transition: box-shadow 0.2s ease;
  margin-bottom:1.2em;
}
a.neon-btn:hover { box-shadow: 0 8px 24px rgba(0,255,163,0.85);}
</style>
""", unsafe_allow_html=True)

# ---- HEADER ----
col1, col2 = st.columns([3,1])
with col1:
    st.title("PASHA Holding Data Automation Suite")
    st.markdown(
        "Automated quarterly financial data pipeline for major AZE banks and the Central Bank.  \n"
        "One-click updates, no manual overhead."
    )
with col2:
    if logo_b64:
        st.markdown(f"<img src='data:image/png;base64,{logo_b64}' class='rotating-logo'/>", unsafe_allow_html=True)

st.markdown("<hr>", unsafe_allow_html=True)

# ---- STATUS UTILS ----
def has_any_data(bank_folder):
    raw = os.path.join("raw_data", bank_folder)
    processed = os.path.join("processed_data", bank_folder)
    return (
        (os.path.exists(raw) and any(os.scandir(raw)))
        or (os.path.exists(processed) and any(os.scandir(processed)))
    )

def needs_acrobat(bank_folder):
    raw = os.path.join("raw_data", bank_folder)
    processed = os.path.join("processed_data", bank_folder)
    if not os.path.exists(raw):
        return []
    periods_needed = []
    for period in os.listdir(raw):
        raw_p = os.path.join(raw, period)
        processed_p = os.path.join(processed, period)
        if os.path.isdir(raw_p):
            pdfs = [f for f in os.listdir(raw_p) if f.lower().endswith('.pdf')]
            has_excel = os.path.exists(processed_p) and any(f.lower().endswith(('.xlsx', '.xls')) for f in os.listdir(processed_p)) if os.path.exists(processed_p) else False
            if pdfs and not has_excel:
                periods_needed.append(period)
    return periods_needed

def needs_arrange(bank_folder):
    raw = os.path.join("raw_data", bank_folder)
    if not os.path.exists(raw):
        return []
    periods_needed = []
    for period in os.listdir(raw):
        raw_p = os.path.join(raw, period)
        if os.path.isdir(raw_p):
            excels = [f for f in os.listdir(raw_p) if f.lower().endswith(('.xlsx', '.xls'))]
            if excels:
                periods_needed.append(period)
    return periods_needed

def is_fully_arranged(bank_folder):
    if needs_acrobat(bank_folder):
        return False
    if needs_arrange(bank_folder):
        return False
    processed = os.path.join("processed_data", bank_folder)
    return os.path.exists(processed) and any(os.scandir(processed))

def list_quarters_status(bank_folder):

    # CBAR special handling: only display the latest available period (from filename)
    if bank_folder.lower() == "cbar":
        processed = os.path.join("processed_data", bank_folder)
        if os.path.exists(processed):
            files = [f for f in os.listdir(processed) if f.startswith("CBAR_") and f.endswith(".xlsx")]
            if files:
                # Sort by modified time, most recent first
                files = sorted(files, key=lambda f: os.path.getmtime(os.path.join(processed, f)), reverse=True)
                latest = files[0]
                # Extract period (e.g., July_2024 → July 2024)
                m = re.match(r"CBAR_(\w+_\d{4})\.xlsx", latest)
                period = m.group(1).replace("_", " ") if m else "Latest"
                return [(period, "ready")]
        # If nothing found, show no quarters
        return []
    
    raw = os.path.join("raw_data", bank_folder)
    processed = os.path.join("processed_data", bank_folder)
    # Get all unique period folders (union of both dirs)
    period_set = set()
    if os.path.exists(raw):
        period_set.update([d for d in os.listdir(raw) if os.path.isdir(os.path.join(raw, d))])
    if os.path.exists(processed):
        period_set.update([d for d in os.listdir(processed) if os.path.isdir(os.path.join(processed, d))])
    quarters = []
    for period in sorted(period_set):
        raw_p = os.path.join(raw, period)
        processed_p = os.path.join(processed, period)
        # PDF detection in raw, Excel detection in processed, fallback logic
        pdfs = []
        excels = []
        if os.path.isdir(raw_p):
            pdfs = [f for f in os.listdir(raw_p) if f.lower().endswith('.pdf')]
        if os.path.isdir(processed_p):
            excels = [f for f in os.listdir(processed_p) if f.lower().endswith(('.xlsx','.xls'))]
        if pdfs and not excels:
            quarters.append((period, "acrobat"))
        elif not excels:
            quarters.append((period, "arrange"))
        else:
            quarters.append((period, "ready"))
    return quarters

def render_quarters_expander(bank_folder, key):
    quarters = list_quarters_status(bank_folder)
    with st.expander("View Quarters", expanded=False):
        if quarters:
            badges = ""
            for q, s in quarters:
                css_class = "ready" if s=="ready" else "arrange" if s=="arrange" else "acrobat" if s=="acrobat" else "missing"
                status_text = "Ready" if s=="ready" else "Needs Arrange" if s=="arrange" else "Acrobat Needed" if s=="acrobat" else "Missing"
                badges += f"<span class='expander-badge {css_class}' title='{status_text}'>{q}</span>"
            st.markdown(
                f"<div class='quarters-grid'>{badges}</div>",
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                "<div class='quarters-grid'><span class='expander-badge missing'>No quarters</span></div>",
                unsafe_allow_html=True
            )

# ---- SCRAPE LOCK STATE ----
if 'scraping_any' not in st.session_state:
    st.session_state['scraping_any'] = False

def run_scraper(idx, name, folder):
    st.session_state['scraping_any'] = True
    badge_html = "<span class='status-badge arrange'>⏳ Scraping...</span>"
    status_holders[idx].markdown(render_bank_row(badge_html, folder, name), unsafe_allow_html=True)
    script = SCRAPERS[idx] if idx < len(SCRAPERS) else None
    if script and os.path.exists(script):
        try:
            res = subprocess.run(["python3", script], capture_output=True, text=True, timeout=420)
            log_out = (res.stdout or "") + "\n" + (res.stderr or "")
            if res.returncode == 0:
                acrobat_periods = needs_acrobat(folder)
                if acrobat_periods:
                    period_str = ', '.join(acrobat_periods)
                    badge_html = f"<span class='status-badge arrange'>🟨 Acrobat Needed</span>"
                    msg = (
                        f"{badge_html} "
                        f"{render_bank_row('', folder, name)} <span style='color:#aaa;font-size:0.96em'>({period_str})</span><br>"
                        "<b style='color:#FFEF00;'>PDF files detected. Open <u>Adobe Acrobat Wizard</u>. It will convert PDFs to Excel.<br>Only then proceed to <u>Arrange Files</u>.</b>"
                    )
                    status_holders[idx].markdown(msg, unsafe_allow_html=True)
                else:
                    arrange_periods = needs_arrange(folder)
                    if arrange_periods:
                        period_str = ', '.join(arrange_periods)
                        badge_html = f"<span class='status-badge arrange'>🟨 Needs Arrange</span>"
                        status_holders[idx].markdown(
                            render_bank_row(badge_html, folder, name) + f" <span style='color:#aaa;font-size:0.96em'>({period_str})</span>",
                            unsafe_allow_html=True
                        )
                    elif is_fully_arranged(folder):
                        badge_html = f"<span class='status-badge'>✅ Ready</span>"
                        status_holders[idx].markdown(render_bank_row(badge_html, folder, name), unsafe_allow_html=True)
                    elif has_any_data(folder):
                        badge_html = f"<span class='status-badge'>🟩 Downloaded</span>"
                        status_holders[idx].markdown(render_bank_row(badge_html, folder, name), unsafe_allow_html=True)
                    else:
                        badge_html = f"<span class='status-badge error'>❌ No Data</span>"
                        status_holders[idx].markdown(render_bank_row(badge_html, folder, name), unsafe_allow_html=True)
            else:
                error_logs[idx] = log_out
                with status_holders[idx]:
                    badge_html = f"<span class='status-badge error'>❌ Error</span>"
                    st.markdown(render_bank_row(badge_html, folder, name), unsafe_allow_html=True)
                    st.expander("View Error / Missing Summary").code(error_logs[idx] or "No details.", language="text")
        except Exception as e:
            badge_html = f"<span class='status-badge error'>❌ Error</span>"
            status_holders[idx].markdown(
                render_bank_row(badge_html, folder, name) + f" <span style='color:#888;font-size:0.97em'>{e}</span>",
                unsafe_allow_html=True
            )
    else:
        badge_html = f"<span class='status-badge error'>❌ Script missing</span>"
        status_holders[idx].markdown(render_bank_row(badge_html, folder, name), unsafe_allow_html=True)
    st.session_state['scraping_any'] = False

# ---- STEP 1: SCRAPING ----
st.subheader("1️⃣ Scrape & Update")

status_holders = [st.empty() for _ in BANKS]
scrape_clicked = st.button("🔄 Run All Scrapers", disabled=st.session_state['scraping_any'])
error_logs = [None] * len(BANKS)

for idx, (name, folder) in enumerate(BANKS):
    col1, col2, col3, col4 = st.columns([0.15, 0.20, 0.48, 0.17])
    if needs_acrobat(folder):
        badge_html = "<span class='status-badge arrange'>🟨 Acrobat Needed</span>"
    elif needs_arrange(folder):
        badge_html = "<span class='status-badge arrange'>🟨 Needs Arrange</span>"
    elif is_fully_arranged(folder):
        badge_html = "<span class='status-badge'>✅ Fully Arranged</span>"
    elif has_any_data(folder):
        badge_html = "<span class='status-badge'>🟩 Downloaded</span>"
    else:
        badge_html = "<span class='status-badge error'>❌ Not Downloaded</span>"

    with col1:
        st.markdown(
            f"<div style='display:flex;align-items:center;min-height:54px'>{badge_html}</div>",
            unsafe_allow_html=True
        )
    with col2:
        logo_b64 = get_bank_logo_b64(folder)
        logo_html = (
            f"<img src='data:image/png;base64,{logo_b64}' "
            "style='height:27px;width:auto;margin-right:10px;border-radius:5px;display:inline-block;'>"
            if logo_b64 else ""
        )
        st.markdown(
            f"""
            <div style="display:flex;align-items:center;min-height:54px;">
                {logo_html}<b style="font-size:1.08em;display:inline-block;vertical-align:middle;">{name}</b>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col3:
        # EXPANDER
        render_quarters_expander(folder, key=f"exp_{idx}")
    with col4:
        # SCRAPE BUTTON
        indiv_btn = st.button("Scrape", key=f"scrape_{idx}", disabled=st.session_state['scraping_any'])
        if indiv_btn:
            with st.spinner(f"Scraping {name}…"):
                run_scraper(idx, name, folder)
                st.rerun()

if scrape_clicked:
    with st.spinner("Scraping all banks…"):
        st.session_state['scraping_any'] = True
        for idx, (name, folder) in enumerate(BANKS):
            run_scraper(idx, name, folder)
        st.session_state['scraping_any'] = False
    st.success("🎉 Scraping complete!")
    st.rerun()

# ---- STEP 2: ARRANGEMENT (AFTER ACROBAT) ----
st.markdown("---")
st.subheader("2️⃣ Arrange Files")

needs_arrange_banks = []
for name, folder in BANKS:
    arrange_periods = needs_arrange(folder)
    if arrange_periods:
        needs_arrange_banks.append((name, arrange_periods))
if needs_arrange_banks:
    msg = "<br>".join(
        f"<b>{name}</b>: <span style='color:#ccc;font-size:0.96em'>{', '.join(periods)}</span>"
        for name, periods in needs_arrange_banks
    )
    st.markdown(
    "<div style='padding:0.8em 1em;background:#2b2b40;border-radius:8px;color:#F7E967;border-left:5px solid #FFEF00;margin-bottom:1em;font-weight:500;'>"
    "<b>After converting PDFs with Acrobat:</b> Click <b>Arrange Files</b> to finalize processing for the periods below.<br><br>" + msg +
    "</div>", unsafe_allow_html=True)
else:
    st.success("✅ No banks need arranging. All processed.")

arrange_clicked = st.button("📂 Arrange Files for Banks Needing It", disabled=st.session_state['scraping_any'])
if arrange_clicked:
    with st.spinner("Arranging all Excels from raw_data…"):
        arrange_logs = []
        for name, folder in BANKS:
            script = next((p for f, p in ARRANGERS if f == folder), None)
            if script and os.path.exists(script):
                res = subprocess.run(["python3", script], capture_output=True, text=True)
                arrange_logs.append(f"[{name}] " + (res.stdout.strip() or "OK"))
                if res.stderr:
                    arrange_logs.append(res.stderr.strip())
        st.success("✅ All arrange scripts have been executed.")
        st.expander("View arrange logs").code('\n'.join(arrange_logs))
    st.rerun()

# ---- STEP 3: FINAL BANK STATUS ----
st.markdown("---")
st.subheader("3️⃣ Final Bank Status")
for idx, (name, folder) in enumerate(BANKS):
    col1, col2, col3, col4 = st.columns([0.15, 0.20, 0.48, 0.17])
    if needs_acrobat(folder):
        badge_html = "<span class='status-badge arrange'>🟨 Acrobat Needed</span>"
    elif needs_arrange(folder):
        badge_html = "<span class='status-badge arrange'>🟨 Needs Arrange</span>"
    elif is_fully_arranged(folder):
        badge_html = "<span class='status-badge'>✅ Fully Arranged</span>"
    elif has_any_data(folder):
        badge_html = "<span class='status-badge'>🟩 Downloaded</span>"
    else:
        badge_html = "<span class='status-badge error'>❌ Not Downloaded</span>"

    with col1:
        st.markdown(
            f"<div style='display:flex;align-items:center;min-height:54px'>{badge_html}</div>",
            unsafe_allow_html=True
        )
    with col2:
        logo_b64 = get_bank_logo_b64(folder)
        logo_html = (
            f"<img src='data:image/png;base64,{logo_b64}' "
            "style='height:27px;width:auto;margin-right:10px;border-radius:5px;display:inline-block;'>"
            if logo_b64 else ""
        )
        st.markdown(
            f"""
            <div style="display:flex;align-items:center;min-height:54px;">
                {logo_html}<b style="font-size:1.08em;display:inline-block;vertical-align:middle;">{name}</b>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col3:
        render_quarters_expander(folder, key=f"final_{idx}")
    with col4:
        pass  # Nothing here for now

# ---- STEP 4: EXPORT ----
st.markdown("---")
st.subheader("4️⃣ Export Processed Data")

if all_banks_fully_arranged():
    zip_buffer = zip_processed_data()
    st.download_button(
        label="⬇️ Download All Processed Data (ZIP)",
        data=zip_buffer,
        file_name=f"processed_data_{datetime.now().strftime('%Y%m%d')}.zip",
        mime="application/zip"
    )
else:
    st.warning("⚠️ Processed data is incomplete. Finish arranging first.")

# ---- STEP 5: LAUNCH POWERBI ----
st.markdown("---")
st.subheader("5️⃣ Launch PowerBI")

st.markdown(
    '<a class="neon-btn" href="https://app.powerbi.com/" target="_blank">'
    '📊 Open PowerBI Dashboard'
    '</a>',
    unsafe_allow_html=True
)
st.markdown("<hr>", unsafe_allow_html=True)
st.markdown("<div class='footer-custom'>© 2025 PASHA Holding</div>", unsafe_allow_html=True)
