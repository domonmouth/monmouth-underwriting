"""
Monmouth Group — Bank Statement Analysis
Page 2: Upload PDFs → Parse → Validate → Analyse → HTML Report
"""

import os
import sys
import json
import tempfile
import datetime
from pathlib import Path

import streamlit as st

# ── Ensure core/ is importable ─────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from core.pdf_intake import check_pdf_quality, extract_text
from core.validator import validate_all
from core.analytics import run_analytics
from core.report_builder import build_report as build_html_report

if not st.session_state.get("authenticated", False):
    st.warning("Please log in from the home page.")
    st.stop()

# ── Config ─────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get(
    "ANTHROPIC_API_KEY",
    st.secrets.get("ANTHROPIC_API_KEY", ""),
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
        display: flex; align-items: center; justify-content: space-between;
    }
    .top-bar-title { color: white; font-size: 13px; font-family: sans-serif; letter-spacing: 0.5px; opacity: 0.85; }
    .top-bar-date  { color: white; font-size: 12px; font-family: sans-serif; opacity: 0.6; }

    .section-label {
        font-size: 11px; font-weight: 700; letter-spacing: 1px;
        text-transform: uppercase; color: #2D5FA6; margin-bottom: 6px;
    }

    .stButton > button {
        background-color: #1B2A4A; color: white; border: none; border-radius: 6px;
        padding: 10px 28px; font-size: 14px; font-weight: 600; width: 100%; transition: background 0.2s;
    }
    .stButton > button:hover { background-color: #2D5FA6; }

    .status-msg { font-size: 13px; color: #555; padding: 6px 0; }
    hr { border: none; border-top: 1px solid #e8e8e8; margin: 16px 0; }

    .stat-card {
        background: #EAF0FB; border-radius: 8px; padding: 14px 18px;
        text-align: center;
    }
    .stat-value { font-size: 20px; font-weight: 700; color: #1B2A4A; }
    .stat-label {
        font-size: 11px; color: #666; text-transform: uppercase;
        letter-spacing: 0.5px; margin-top: 4px;
    }

    .file-ok {
        background: #EAFAF1; border-left: 3px solid #1A7A3C;
        border-radius: 4px; padding: 8px 14px; margin-bottom: 6px;
        font-size: 13px; color: #1A7A3C;
    }
    .file-fail {
        background: #FDEDEC; border-left: 3px solid #C0392B;
        border-radius: 4px; padding: 8px 14px; margin-bottom: 6px;
        font-size: 13px; color: #C0392B;
    }
    .recon-pass {
        background: #EAFAF1; border: 1px solid #86efac;
        border-radius: 6px; padding: 10px 16px; margin-bottom: 6px; font-size: 13px;
    }
    .recon-fail {
        background: #FDEDEC; border: 1px solid #fca5a5;
        border-radius: 6px; padding: 10px 16px; margin-bottom: 6px; font-size: 13px;
    }
    .warn-box {
        background: #FEF6EC; border: 1px solid #fcd34d; border-left: 4px solid #D4780A;
        border-radius: 6px; padding: 10px 16px; margin-bottom: 6px; font-size: 13px; color: #92400e;
    }
</style>
""", unsafe_allow_html=True)

# ── Top bar ────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="top-bar">
    <span class="top-bar-title">BANK STATEMENT ANALYSIS</span>
    <span class="top-bar-date">{datetime.date.today().strftime('%A %d %B %Y')}</span>
</div>
""", unsafe_allow_html=True)

# ── Logo ───────────────────────────────────────────────────────────────────
logo_path = ROOT / "Monmouth_Logo_Navy_RGB.png"
if logo_path.exists():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.image(str(logo_path), width=260)
else:
    st.markdown("## Monmouth Group")

st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
st.markdown(
    "<p style='text-align:center;color:#666;font-size:14px;margin-bottom:24px'>"
    "Upload PDF bank statements to generate a credit analysis report.</p>",
    unsafe_allow_html=True,
)

# ── Session state ──────────────────────────────────────────────────────────
for key, default in {
    "bank_parsed": [],
    "bank_validation": None,
    "bank_analytics": None,
    "bank_report_html": None,
    "bank_stage": "upload",
    "bank_accepted": [],
    "bank_rejected": [],
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# ── API key check ──────────────────────────────────────────────────────────
if not ANTHROPIC_API_KEY:
    st.warning(
        "⚠️ **Anthropic API key not configured.** "
        "Add `ANTHROPIC_API_KEY` in Streamlit secrets (Settings → Secrets) to enable PDF parsing."
    )

# ════════════════════════════════════════════════════════════════════════════
# STAGE 1: FILE UPLOAD
# ════════════════════════════════════════════════════════════════════════════

st.markdown('<div class="section-label">Upload Bank Statements</div>', unsafe_allow_html=True)

uploaded_files = st.file_uploader(
    "Upload PDF bank statements",
    type=["pdf"],
    accept_multiple_files=True,
    label_visibility="collapsed",
    help="Upload PDF bank statements (native digital, not scanned). Minimum 3 months recommended, 6+ ideal.",
)

if uploaded_files and st.session_state.bank_stage == "upload":
    if st.button("🔍  Check & Parse Statements", use_container_width=True):
        accepted = []
        rejected = []

        progress = st.progress(0)
        status = st.empty()
        total = len(uploaded_files)

        # ── Step 1: quality check all files ───────────────────────────────
        for i, uf in enumerate(uploaded_files):
            pct = (i + 1) / (total + 2)
            status.markdown(
                f'<p class="status-msg">⏳ Checking {uf.name}... ({i+1}/{total})</p>',
                unsafe_allow_html=True,
            )
            progress.progress(pct)

            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(uf.read())
                tmp_path = tmp.name

            try:
                quality = check_pdf_quality(tmp_path)
                if not quality['is_text_based']:
                    rejected.append({"filename": uf.name, "reason": quality['reason']})
                    continue

                text, bank_name = extract_text(tmp_path)
                accepted.append({
                    "filename": uf.name,
                    "page_count": quality['page_count'],
                    "avg_chars_per_page": quality['avg_chars_per_page'],
                    "text": text,
                    "bank_name": bank_name,
                })
            except Exception as e:
                rejected.append({"filename": uf.name, "reason": str(e)})
            finally:
                os.unlink(tmp_path)

        st.session_state.bank_accepted = accepted
        st.session_state.bank_rejected = rejected

        if not accepted:
            progress.empty()
            status.empty()
            st.error("No valid statements found. All files were rejected — see details below.")

        elif not ANTHROPIC_API_KEY:
            progress.empty()
            status.empty()
            st.error(
                "Cannot parse statements — no Anthropic API key configured. "
                "Add `ANTHROPIC_API_KEY` in Streamlit secrets."
            )

        else:
            # ── Step 2: parse via Claude API ──────────────────────────────
            import anthropic
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

            from core.parser import PARSE_PROMPT, BANK_HINTS

            MAX_CHARS_PER_CHUNK = 30000

            def split_text_into_chunks(full_text, max_chars=MAX_CHARS_PER_CHUNK):
                import re
                parts = re.split(r'(?=\n--- PAGE \d+)', full_text)
                parts = [p for p in parts if p.strip()]
                if sum(len(p) for p in parts) <= max_chars:
                    return [full_text]
                chunks = []
                current_chunk = ''
                for part in parts:
                    if current_chunk and len(current_chunk) + len(part) > max_chars:
                        chunks.append(current_chunk)
                        current_chunk = part
                    else:
                        current_chunk += part
                if current_chunk:
                    chunks.append(current_chunk)
                return chunks

            def parse_chunk(client, text_chunk, filename, is_first_chunk, bank_name='unknown'):
                if is_first_chunk:
                    hints = BANK_HINTS.get(bank_name, '')
                    prompt = PARSE_PROMPT.format(bank_hints=hints, text=text_chunk)
                else:
                    prompt = (
                        "You are a bank statement parser. This is a CONTINUATION of a bank statement. "
                        "Extract every transaction and return JSON with two keys:\n"
                        '- "metadata": {} (empty object — metadata was already extracted)\n'
                        '- "transactions": array of transaction objects\n\n'
                        "Each transaction must have: date (DD/MM/YY), description (string), "
                        "money_out (number, 0 if none), money_in (number, 0 if none), "
                        "balance (number, 0 if not shown).\n\n"
                        "IMPORTANT: If amounts are prefixed with [IN] or [OUT] tags (e.g. '[IN]£500.00' or "
                        "'[OUT]£200.00'), use these tags to determine money_in vs money_out. "
                        "[IN] means money_in, [OUT] means money_out. "
                        "Untagged £ amounts on the same line are the end-of-day balance.\n\n"
                        "CRITICAL: Include EVERY transaction. Do NOT include BROUGHT FORWARD lines. "
                        "Money values must be numbers, not strings. Return only valid JSON.\n\n"
                        f"Bank statement text:\n{text_chunk}"
                    )
                raw = ''
                with client.messages.stream(
                    model="claude-sonnet-4-6",
                    max_tokens=32000,
                    messages=[{"role": "user", "content": prompt}],
                ) as stream:
                    for text_bit in stream.text_stream:
                        raw += text_bit
                raw = raw.strip()
                if raw.startswith('```'):
                    raw = raw.split('```')[1]
                    if raw.startswith('json'):
                        raw = raw[4:]
                raw = raw.strip()
                return json.loads(raw)

            parsed_statements = []

            for j, pdf_data in enumerate(accepted):
                step_pct = (total + j + 1) / (total + len(accepted) + 1)
                status.markdown(
                    f'<p class="status-msg">⏳ Parsing {pdf_data["filename"]} via Claude API... ({j+1}/{len(accepted)})</p>',
                    unsafe_allow_html=True,
                )
                progress.progress(step_pct)

                try:
                    chunks = split_text_into_chunks(pdf_data['text'])

                    if len(chunks) == 1:
                        parsed = parse_chunk(
                            client, chunks[0], pdf_data['filename'],
                            is_first_chunk=True, bank_name=pdf_data['bank_name']
                        )
                    else:
                        # Multi-chunk: parse each and merge
                        all_transactions = []
                        metadata = {}
                        for k, chunk in enumerate(chunks):
                            status.markdown(
                                f'<p class="status-msg">⏳ Large statement — chunk {k+1}/{len(chunks)}...</p>',
                                unsafe_allow_html=True,
                            )
                            chunk_parsed = parse_chunk(
                                client, chunk, pdf_data['filename'],
                                is_first_chunk=(k == 0), bank_name=pdf_data['bank_name']
                            )
                            if k == 0:
                                metadata = chunk_parsed.get('metadata', {})
                            all_transactions.extend(chunk_parsed.get('transactions', []))
                        parsed = {'metadata': metadata, 'transactions': all_transactions}

                    parsed['_filename'] = pdf_data['filename']
                    parsed['_bank_name'] = pdf_data['bank_name']
                    parsed_statements.append(parsed)

                except Exception as e:
                    st.warning(f"⚠️ Failed to parse {pdf_data['filename']}: {e}")

            st.session_state.bank_parsed = parsed_statements

            if parsed_statements:
                progress.progress(1.0)
                status.markdown(
                    '<p class="status-msg">✅ Parsing complete — running validation...</p>',
                    unsafe_allow_html=True,
                )

                # ── Step 3: validate ──────────────────────────────────────
                validation = validate_all(parsed_statements)
                st.session_state.bank_validation = validation

                # ── Step 4: analytics ─────────────────────────────────────
                analytics = run_analytics(parsed_statements)
                st.session_state.bank_analytics = analytics

                # ── Step 5: build report ──────────────────────────────────
                report_html = build_html_report(parsed_statements, validation)
                st.session_state.bank_report_html = report_html

                st.session_state.bank_stage = "results"
                progress.empty()
                status.empty()
                st.rerun()
            else:
                progress.empty()
                status.empty()
                st.error("All statements failed to parse. Check the warnings above.")

# ── Show rejected files ────────────────────────────────────────────────────
if st.session_state.bank_rejected:
    for r in st.session_state.bank_rejected:
        st.markdown(
            f'<div class="file-fail">✗ {r["filename"]} — {r["reason"]}</div>',
            unsafe_allow_html=True,
        )

# Show accepted file list while in upload stage
if st.session_state.bank_stage == "upload" and st.session_state.bank_accepted:
    for a in st.session_state.bank_accepted:
        st.markdown(
            f'<div class="file-ok">✓ {a["filename"]} — {a["page_count"]} pages, '
            f'{a["avg_chars_per_page"]} avg chars/page</div>',
            unsafe_allow_html=True,
        )

# ════════════════════════════════════════════════════════════════════════════
# STAGE 2: RESULTS
# ════════════════════════════════════════════════════════════════════════════

if st.session_state.bank_stage == "results":

    validation = st.session_state.bank_validation
    analytics  = st.session_state.bank_analytics
    parsed     = st.session_state.bank_parsed

    # ── Summary cards ──────────────────────────────────────────────────────
    months     = len(parsed)
    total_in   = sum(
        sum(t.get('money_in', 0) for t in s.get('transactions', []))
        for s in parsed
    )
    total_out  = sum(
        sum(t.get('money_out', 0) for t in s.get('transactions', []))
        for s in parsed
    )
    lenders    = analytics.get('lenders', {})
    confirmed  = lenders.get('confirmed', {})
    suspected  = lenders.get('suspected', {})
    lender_count = len(confirmed) + len(suspected)

    c1, c2, c3, c4 = st.columns(4)
    for col, val, label in [
        (c1, months,           "Months"),
        (c2, f"£{total_in:,.0f}",  "Total In"),
        (c3, f"£{total_out:,.0f}", "Total Out"),
        (c4, lender_count,     "Lenders Detected"),
    ]:
        col.markdown(
            f'<div class="stat-card"><div class="stat-value">{val}</div>'
            f'<div class="stat-label">{label}</div></div>',
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    # ── Reconciliation results ─────────────────────────────────────────────
    st.markdown('<div class="section-label">Reconciliation</div>', unsafe_allow_html=True)

    recon_results = validation.get('reconciliation', [])
    for r in recon_results:
        if r['status'] == 'PASS':
            st.markdown(
                f'<div class="recon-pass">✓ {r["filename"]} — reconciled '
                f'(diff £{r.get("diff", 0):.2f})</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="recon-fail">✗ {r["filename"]} — '
                f'{r.get("reason", "reconciliation failed")} '
                f'(diff £{r.get("diff", 0):.2f})</div>',
                unsafe_allow_html=True,
            )

    # ── Warnings ───────────────────────────────────────────────────────────
    warnings = validation.get('warnings', [])
    if warnings:
        st.markdown('<div class="section-label" style="margin-top:16px">Warnings</div>', unsafe_allow_html=True)
        for w in warnings:
            st.markdown(f'<div class="warn-box">⚠️ {w}</div>', unsafe_allow_html=True)

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    # ── Download report ────────────────────────────────────────────────────
    st.markdown('<div class="section-label">Report</div>', unsafe_allow_html=True)

    report_html = st.session_state.bank_report_html
    if report_html:
        st.download_button(
            label="⬇️  Download Credit Analysis Report (HTML)",
            data=report_html,
            file_name="monmouth_bank_analysis.html",
            mime="text/html",
            use_container_width=True,
        )

    # ── Reset ──────────────────────────────────────────────────────────────
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    if st.button("↩  Start New Analysis", use_container_width=True):
        for key in ["bank_parsed", "bank_validation", "bank_analytics",
                    "bank_report_html", "bank_accepted", "bank_rejected"]:
            st.session_state[key] = [] if key in ["bank_parsed", "bank_accepted", "bank_rejected"] else None
        st.session_state.bank_stage = "upload"
        st.rerun()
