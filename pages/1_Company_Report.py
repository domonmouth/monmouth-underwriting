"""
Monmouth Group — Company Underwriting Report
Page 1: Companies House search → PDF report generation
(Previously the root app.py — moved to pages/ for multi-page structure)
"""

import os
import time
import json
import datetime
from pathlib import Path
import streamlit as st
import requests

# ── Page config (set_page_config must be first Streamlit call per page) ────
# NOTE: page config is set in the root app.py; this page inherits it.

if not st.session_state.get("authenticated", False):
    st.warning("Please log in from the home page.")
    st.stop()
# ── Config ─────────────────────────────────────────────────────────────────
CH_API_KEY   = os.environ.get("CH_API_KEY", st.secrets.get("CH_API_KEY", ""))
OUTPUT_DIR   = Path(os.environ.get("REPORT_OUTPUT_DIR", Path.home() / "monmouth_reports"))
HISTORY_FILE = OUTPUT_DIR / ".report_history.json"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Styling ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .stApp { background-color: #FFFFFF; }
    #MainMenu, footer, header { visibility: hidden; }
    .top-bar {
        background-color: #1B2A4A;
        padding: 14px 32px;
        margin: -1rem -1rem 2rem -1rem;
        display: flex; align-items: center; justify-content: space-between;
    }
    .top-bar-title { color: white; font-size: 13px; font-family: sans-serif; letter-spacing: 0.5px; opacity: 0.85; }
    .top-bar-date { color: white; font-size: 12px; font-family: sans-serif; opacity: 0.6; }
    .card { background: white; border-radius: 10px; padding: 28px 32px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); margin-bottom: 20px; }
    .section-label { font-size: 11px; font-weight: 700; letter-spacing: 1px; text-transform: uppercase; color: #2D5FA6; margin-bottom: 6px; }
    .result-item { background: #EAF0FB; border-left: 3px solid #2D5FA6; border-radius: 4px; padding: 10px 14px; margin-bottom: 8px; cursor: pointer; }
    .result-item:hover { background: #d6e4f7; }
    .result-name { font-weight: 600; font-size: 14px; color: #1B2A4A; }
    .result-meta { font-size: 12px; color: #666; margin-top: 2px; }
    .badge-active   { background:#EAFAF1; color:#1A7A3C; padding:2px 8px; border-radius:10px; font-size:11px; font-weight:600; }
    .badge-inactive { background:#FDEDEC; color:#C0392B; padding:2px 8px; border-radius:10px; font-size:11px; font-weight:600; }
    .badge-amber    { background:#FEF6EC; color:#D4780A; padding:2px 8px; border-radius:10px; font-size:11px; font-weight:600; }
    .stButton > button {
        background-color: #1B2A4A; color: white; border: none; border-radius: 6px;
        padding: 10px 28px; font-size: 14px; font-weight: 600; width: 100%; transition: background 0.2s;
    }
    .stButton > button:hover { background-color: #2D5FA6; }
    .status-msg { font-size: 13px; color: #555; padding: 6px 0; }
    hr { border: none; border-top: 1px solid #e8e8e8; margin: 16px 0; }
    .stTextInput > div > div > input {
        border-radius: 6px; border: 1.5px solid #d0d9e8; font-size: 14px; padding: 10px 14px;
    }
    .stTextInput > div > div > input:focus {
        border-color: #2D5FA6; box-shadow: 0 0 0 2px rgba(45,95,166,0.15);
    }
</style>
""", unsafe_allow_html=True)


# ── Helper: Companies House API ────────────────────────────────────────────
def ch_search(query: str):
    try:
        r = requests.get(
            "https://api.company-information.service.gov.uk/search/companies",
            params={"q": query, "items_per_page": 8},
            auth=(CH_API_KEY, ""), timeout=10,
        )
        r.raise_for_status()
        return r.json().get("items", [])
    except Exception as e:
        st.error(f"Companies House API error: {e}")
        return []


def ch_get(path: str):
    try:
        r = requests.get(
            f"https://api.company-information.service.gov.uk{path}",
            auth=(CH_API_KEY, ""), timeout=10,
        )
        r.raise_for_status()
        return r.json()
    except:
        return {}


def status_badge(status: str) -> str:
    s = status.lower()
    if s == "active":
        return f'<span class="badge-active">Active</span>'
    elif s in ("dissolved", "liquidation", "administration"):
        return f'<span class="badge-inactive">{status.title()}</span>'
    else:
        return f'<span class="badge-amber">{status.title()}</span>'


# ── History helpers ────────────────────────────────────────────────────────
def load_history():
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text())
        except:
            return []
    return []


def save_history(entry: dict):
    history = load_history()
    history.insert(0, entry)
    history = history[:50]
    HISTORY_FILE.write_text(json.dumps(history, indent=2))


# ── Session state defaults ─────────────────────────────────────────────────
for key, default in {
    "search_results": [],
    "selected_company": None,
    "report_path": None,
    "generating": False,
    "search_query": "",
    "last_query": "",
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


# ── Top bar ────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="top-bar">
    <span class="top-bar-title">COMPANY UNDERWRITING REPORT</span>
    <span class="top-bar-date">{datetime.date.today().strftime('%A %d %B %Y')}</span>
</div>
""", unsafe_allow_html=True)

# ── Logo ───────────────────────────────────────────────────────────────────
logo_path = Path(__file__).parent.parent / "Monmouth_Logo_Navy_RGB.png"
if logo_path.exists():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.image(str(logo_path), width=260)
else:
    st.markdown("## Monmouth Group")

st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
st.markdown(
    "<p style='text-align:center;color:#666;font-size:14px;margin-bottom:24px'>"
    "Enter a company name or registration number to generate an underwriting summary report.</p>",
    unsafe_allow_html=True,
)

# ── Search card ────────────────────────────────────────────────────────────
with st.container():
    st.markdown('<div class="section-label">Company Search</div>', unsafe_allow_html=True)
    col_input, col_btn = st.columns([4, 1])
    with col_input:
        query = st.text_input(
            label="company_search",
            placeholder="e.g. Spanish Slate Quarries  or  08584514",
            label_visibility="collapsed",
            key="search_box",
        )
    with col_btn:
        search_clicked = st.button("Search", use_container_width=True)

    if search_clicked and query.strip():
        st.session_state.search_query = query.strip()
        st.session_state.selected_company = None
        st.session_state.report_path = None
        with st.spinner("Searching Companies House..."):
            st.session_state.search_results = ch_search(query.strip())

    # ── Search results ─────────────────────────────────────────────────────
    if st.session_state.search_results and not st.session_state.selected_company:
        st.markdown("<hr>", unsafe_allow_html=True)
        st.markdown(
            f'<div class="section-label">'
            f'{len(st.session_state.search_results)} result(s) — select a company</div>',
            unsafe_allow_html=True,
        )
        for i, item in enumerate(st.session_state.search_results):
            name = item.get("title", "Unknown").title()
            number = item.get("company_number", "—")
            status = item.get("company_status", "unknown")
            inc = item.get("date_of_creation", "")
            address = item.get("address", {})
            addr_str = ", ".join(filter(None, [
                address.get("address_line_1", ""),
                address.get("locality", ""),
                address.get("postal_code", ""),
            ]))
            col_info, col_select = st.columns([5, 1])
            with col_info:
                st.markdown(f"""
                    <div class="result-item">
                        <div class="result-name">{name}</div>
                        <div class="result-meta">
                            No. {number} &nbsp;·&nbsp; {status_badge(status)}
                            &nbsp;·&nbsp; Inc. {inc}
                            {'&nbsp;·&nbsp; ' + addr_str if addr_str else ''}
                        </div>
                    </div>
                """, unsafe_allow_html=True)
            with col_select:
                st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
                if st.button("Select →", key=f"sel_{i}", use_container_width=True):
                    st.session_state.selected_company = item
                    st.session_state.report_path = None
                    st.rerun()

# ── Selected company + generate ────────────────────────────────────────────
if st.session_state.selected_company:
    company = st.session_state.selected_company
    name = company.get("title", "Unknown").title()
    number = company.get("company_number", "")
    status = company.get("company_status", "unknown")
    inc = company.get("date_of_creation", "")

    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown('<div class="section-label">Selected Company</div>', unsafe_allow_html=True)
    st.markdown(f"""
        <div style="background:#EAF0FB;border-radius:8px;padding:16px 20px;margin-bottom:16px">
            <div style="font-size:16px;font-weight:700;color:#1B2A4A">{name}</div>
            <div style="font-size:13px;color:#444;margin-top:4px">
                Company No. {number} &nbsp;·&nbsp; {status_badge(status)} &nbsp;·&nbsp; Incorporated {inc}
            </div>
        </div>
    """, unsafe_allow_html=True)

    if number:
        with st.spinner(""):
            co_detail = ch_get(f"/company/{number}")
            sic_codes = co_detail.get("sic_codes", [])
            addr = co_detail.get("registered_office_address", {})
            addr_str = ", ".join(filter(None, [
                addr.get("address_line_1", ""), addr.get("locality", ""), addr.get("postal_code", "")
            ]))
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown(f"**Registered address:** {addr_str or '—'}")
            st.markdown(f"**SIC code(s):** {', '.join(sic_codes) if sic_codes else '—'}")
        with col_b:
            charges = ch_get(f"/company/{number}/charges")
            outstanding = len([c for c in charges.get("items", []) if c.get("status") == "outstanding"])
            total_charges = charges.get("total_count", 0)
            officers = ch_get(f"/company/{number}/officers")
            active_officers = len([o for o in officers.get("items", []) if not o.get("resigned_on")])
            st.markdown(f"**Active officers:** {active_officers}")
            st.markdown(f"**Charges:** {outstanding} outstanding / {total_charges} total")

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    col_gen, col_clear = st.columns([3, 1])
    with col_gen:
        generate_clicked = st.button("⬇  Generate Underwriting Report", use_container_width=True)
    with col_clear:
        if st.button("✕  Clear", use_container_width=True):
            st.session_state.selected_company = None
            st.session_state.search_results = []
            st.session_state.report_path = None
            st.rerun()

    if generate_clicked:
        st.session_state.report_path = None
        progress_area = st.empty()
        status_area = st.empty()
        steps = [
            (0.10, "Fetching company profile..."),
            (0.20, "Fetching officers & PSC register..."),
            (0.35, "Fetching charges register..."),
            (0.50, "Fetching filing history..."),
            (0.65, "Downloading accounts PDFs..."),
            (0.80, "Running credit policy checks..."),
            (0.90, "Building PDF report..."),
            (1.00, "Complete ✓"),
        ]
        try:
            import sys
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from ch_report import build_report

            bar = progress_area.progress(0)
            status_area.markdown(
                '<p class="status-msg">⏳ Connecting to Companies House API...</p>',
                unsafe_allow_html=True,
            )
            for pct, msg in steps[:4]:
                bar.progress(pct)
                status_area.markdown(f'<p class="status-msg">⏳ {msg}</p>', unsafe_allow_html=True)
                time.sleep(0.4)

            bar.progress(0.5)
            status_area.markdown(
                '<p class="status-msg">⏳ Downloading accounts PDFs...</p>',
                unsafe_allow_html=True,
            )
            report_path = build_report(
                company_number=number,
                api_key=CH_API_KEY,
                anthropic_key="",
            )
            for pct, msg in steps[5:]:
                bar.progress(pct)
                status_area.markdown(
                    f'<p class="status-msg">{"✅" if pct == 1.0 else "⏳"} {msg}</p>',
                    unsafe_allow_html=True,
                )
                time.sleep(0.3)

            st.session_state.report_path = report_path
            save_history({
                "company_name": name,
                "company_number": number,
                "generated_at": datetime.datetime.now().isoformat(),
                "report_path": str(report_path),
            })
        except Exception as e:
            progress_area.empty()
            status_area.empty()
            st.error(f"Report generation failed: {e}")
            st.exception(e)

    if st.session_state.report_path:
        report_path = Path(st.session_state.report_path)
        if report_path.exists():
            st.markdown("<hr>", unsafe_allow_html=True)
            st.success("✅ Report ready")
            pdf_bytes = report_path.read_bytes()
            st.download_button(
                label=f"📄  Download Report — {name}",
                data=pdf_bytes,
                file_name=report_path.name,
                mime="application/pdf",
                use_container_width=True,
            )

# ── Footer ─────────────────────────────────────────────────────────────────
st.markdown("<hr>", unsafe_allow_html=True)
st.markdown(
    "<p style='text-align:center;font-size:11px;color:#aaa'>"
    "Monmouth Group · Internal use only · Data sourced from Companies House public register · "
    "CCJ and insolvency status must be confirmed via credit bureau search"
    "</p>",
    unsafe_allow_html=True,
)
