"""
Monmouth Group — Underwriting Tool Suite
Multi-page Streamlit app: landing page / navigation
"""

import datetime
import streamlit as st
from pathlib import Path

st.set_page_config(
    page_title="Monmouth | Underwriting Tools",
    page_icon="📋",
    layout="centered",
    initial_sidebar_state="expanded",
)

# ── Styling ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .stApp { background-color: #FFFFFF; }
    #MainMenu, footer, header { visibility: hidden; }
    .top-bar {
        background-color: #1B2A4A;
        padding: 14px 32px;
        margin: -1rem -1rem 2rem -1rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }
    .top-bar-title {
        color: white;
        font-size: 13px;
        font-family: sans-serif;
        letter-spacing: 0.5px;
        opacity: 0.85;
    }
    .top-bar-date {
        color: white;
        font-size: 12px;
        font-family: sans-serif;
        opacity: 0.6;
    }
    .tool-card {
        background: white;
        border: 1.5px solid #d0d9e8;
        border-radius: 10px;
        padding: 28px 32px;
        margin-bottom: 16px;
        transition: border-color 0.2s, box-shadow 0.2s;
    }
    .tool-card:hover {
        border-color: #2D5FA6;
        box-shadow: 0 2px 12px rgba(45,95,166,0.12);
    }
    .tool-title {
        font-size: 17px;
        font-weight: 700;
        color: #1B2A4A;
        margin-bottom: 6px;
    }
    .tool-desc {
        font-size: 13px;
        color: #666;
        line-height: 1.6;
    }
    .tool-badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 10px;
        font-size: 10px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 10px;
    }
    .badge-live { background: #EAFAF1; color: #1A7A3C; }
    .badge-new  { background: #EAF0FB; color: #2D5FA6; }
</style>
""", unsafe_allow_html=True)

# ── Top bar ────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="top-bar">
    <span class="top-bar-title">UNDERWRITING TOOL SUITE</span>
    <span class="top-bar-date">{datetime.date.today().strftime('%A %d %B %Y')}</span>
</div>
""", unsafe_allow_html=True)

# ── Logo ───────────────────────────────────────────────────────────────────
logo_path = Path(__file__).parent / "Monmouth_Logo_Navy_RGB.png"
if logo_path.exists():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.image(str(logo_path), width=260)
else:
    st.markdown("## Monmouth Group")

st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
st.markdown(
    "<p style='text-align:center;color:#666;font-size:14px;margin-bottom:28px'>"
    "Select a tool from the sidebar, or choose below.</p>",
    unsafe_allow_html=True,
)

# ── Tool cards ─────────────────────────────────────────────────────────────
st.markdown("""
<div class="tool-card">
    <span class="tool-badge badge-live">LIVE</span>
    <div class="tool-title">📋 Company Underwriting Report</div>
    <div class="tool-desc">
        Search Companies House by name or number. Generates a full PDF underwriting summary
        including directors, charges, PSC register, OSINT screening, and credit policy checks.
    </div>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div class="tool-card">
    <span class="tool-badge badge-new">NEW</span>
    <div class="tool-title">🏦 Bank Statement Analysis</div>
    <div class="tool-desc">
        Upload Barclays PDF bank statements. Parses all transactions via AI, runs reconciliation,
        credit analytics, affordability modelling, and generates a self-contained HTML credit report.
    </div>
</div>
""", unsafe_allow_html=True)

st.markdown(
    "<p style='text-align:center;color:#999;font-size:12px;margin-top:16px'>"
    "Use the <strong>sidebar ☰</strong> to navigate between tools.</p>",
    unsafe_allow_html=True,
)

# ── Footer ─────────────────────────────────────────────────────────────────
st.markdown("<hr>", unsafe_allow_html=True)
st.markdown(
    "<p style='text-align:center;font-size:11px;color:#aaa'>"
    "Monmouth Group · Internal use only · Data sourced from Companies House public register &amp; bank statements"
    "</p>",
    unsafe_allow_html=True,
)
