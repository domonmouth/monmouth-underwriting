"""
Monmouth Group — Bank Statement Analysis
Page 2: Upload PDFs → Parse → Validate → Analyse → HTML Report
"""

import os
import sys
import time
import json
import tempfile
import datetime
from datetime import timedelta
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
    .stat-value {
        font-size: 20px; font-weight: 700; color: #1B2A4A;
    }
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
    "bank_stage": "upload",      # upload → parsed → report
    "bank_accepted": [],
    "bank_rejected": [],
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


# ── API key check ──────────────────────────────────────────────────────────
if not ANTHROPIC_API_KEY:
    st.warning(
        "⚠️ **Anthropic API key not configured.** "
        "Add `ANTHROPIC_API_KEY` in Streamlit secrets (Settings → Secrets) to enable PDF parsing. "
        "Without it, only pre-parsed JSON files can be used."
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
        parsed_statements = []

        progress = st.progress(0)
        status = st.empty()
        total = len(uploaded_files)

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
        else:
            if not ANTHROPIC_API_KEY:
                progress.empty()
                status.empty()
                st.error(
                    "Cannot parse statements — no Anthropic API key configured. "
                    "Add `ANTHROPIC_API_KEY` in Streamlit secrets."
                )
            else:
                import anthropic
                client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

                from core.parser import PARSE_PROMPT, BANK_HINTS

                MAX_CHARS_PER_CHUNK = 30000

                def split_text_into_chunks(full_text, max_chars=MAX_CHARS_PER_CHUNK):
                    """Split extracted text into chunks that stay under max_chars each."""
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
                    """Parse a single chunk via streaming API. Returns parsed dict or None."""
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
                            "IMPORTANT: If amounts are prefixed with [IN] or [OUT] tags (e.g. '[IN]£500.00' or '[OUT]£200.00'), "
                            "use these tags to determine money_in vs money_out. [IN] means money_in, [OUT] means money_out. "
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
                        for text_chunk_api in stream.text_stream:
                            raw += text_chunk_api
                    raw = raw.strip()
                    if raw.startswith('```'):
                        raw = raw.split('```')[1]
                        if raw.startswith('json'):
                            raw = raw[4:]
                    raw = raw.strip()
                    return json.loads(raw)

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
                            status.markdown(
                                f'<p class="status-msg">⏳ Large statement — parsing in {len(chunks)} chunks... (1/{len(chunks)})</p>',
                                unsafe_allow_html=True,
                            )
                            merged_transactions = []
                            parsed_metadata = {}

                            for ci, chunk in enumerate(chunks):
                                status.markdown(
                                    f'<p class="status-msg">⏳ Parsing chunk {ci+1}/{len(chunks)} of {pdf_data["filename"]}...</p>',
                                    unsafe_allow_html=True,
                                )
                                chunk_result = parse_chunk(
                                    client, chunk, pdf_data['filename'],
                                    is_first_chunk=(ci == 0), bank_name=pdf_data['bank_name']
                                )
                                if ci == 0:
                                    parsed_metadata = chunk_result.get('metadata', {})
                                merged_transactions.extend(chunk_result.get('transactions', []))

                            parsed = {
                                'metadata': parsed_metadata,
                                'transactions': merged_transactions,
                            }

                        parsed['_filename'] = pdf_data['filename']
                        parsed['_page_count'] = pdf_data['page_count']
                        st.write(parsed.get('metadata', {}))  # TEMP DEBUG
                        parsed_statements.append(parsed)
                    except Exception as e:
                        rejected.append({
                            "filename": pdf_data["filename"],
                            "reason": f"API parse failed: {e}"
                        })

                progress.progress(1.0)
                status.markdown(
                    '<p class="status-msg">✅ All statements parsed</p>',
                    unsafe_allow_html=True,
                )
                time.sleep(0.5)
                progress.empty()
                status.empty()

                if parsed_statements:
                    st.session_state.bank_parsed = parsed_statements
                    st.session_state.bank_rejected = rejected
                    st.session_state.bank_stage = "parsed"
                    st.rerun()
                else:
                    st.error("All statements failed to parse. Check the API key and try again.")


# Show accepted/rejected from upload
if st.session_state.bank_accepted:
    for a in st.session_state.bank_accepted:
        st.markdown(
            f'<div class="file-ok">✓ {a["filename"]} — '
            f'{a["page_count"]} pages, {a["avg_chars_per_page"]} avg chars/page</div>',
            unsafe_allow_html=True,
        )
if st.session_state.bank_rejected:
    for r in st.session_state.bank_rejected:
        st.markdown(
            f'<div class="file-fail">✗ {r["filename"]} — {r["reason"]}</div>',
            unsafe_allow_html=True,
        )


# ════════════════════════════════════════════════════════════════════════════
# STAGE 2: VALIDATION + ANALYTICS + REPORT
# ════════════════════════════════════════════════════════════════════════════

if st.session_state.bank_stage == "parsed" and st.session_state.bank_parsed:
    parsed = st.session_state.bank_parsed

    def split_multi_month_statements(parsed_statements):
        """
        If a single parsed statement covers multiple calendar months,
        split it into one statement object per month.
        """
        from datetime import datetime as dt

        output = []
        for stmt in parsed_statements:
            txs = stmt.get('transactions', [])
            meta = stmt.get('metadata', {})

            if not txs:
                output.append(stmt)
                continue

            DATE_FMTS = ['%d/%m/%y', '%d/%m/%Y']
            monthly_buckets = {}
            for tx in txs:
                d = tx.get('date', '')
                parsed_date = None
                for fmt in DATE_FMTS:
                    try:
                        parsed_date = dt.strptime(d, fmt)
                        break
                    except ValueError:
                        continue
                if parsed_date:
                    key = (parsed_date.year, parsed_date.month)
                    if key not in monthly_buckets:
                        monthly_buckets[key] = []
                    monthly_buckets[key].append(tx)
                else:
                    if monthly_buckets:
                        first_key = list(monthly_buckets.keys())[0]
                        monthly_buckets[first_key].append(tx)
                    else:
                        monthly_buckets[(9999, 1)] = [tx]

            if len(monthly_buckets) <= 2:
                output.append(stmt)
                continue

            sorted_months = sorted(monthly_buckets.keys())
            opening_bal = meta.get('opening_balance', 0)

            for i, month_key in enumerate(sorted_months):
                month_txs = monthly_buckets[month_key]
                year, month = month_key

                last_tx_with_bal = None
                for tx in reversed(month_txs):
                    if tx.get('balance', 0) != 0:
                        last_tx_with_bal = tx
                        break

                if last_tx_with_bal:
                    closing_bal = last_tx_with_bal['balance']
                else:
                    total_in = sum(t.get('money_in', 0) for t in month_txs)
                    total_out = sum(t.get('money_out', 0) for t in month_txs)
                    closing_bal = opening_bal + total_in - total_out

                first_day = f"01/{month:02d}/{str(year)[2:]}"
                if month == 12:
                    last_day_dt = dt(year + 1, 1, 1) - timedelta(days=1)
                else:
                    last_day_dt = dt(year, month + 1, 1) - timedelta(days=1)
                last_day = last_day_dt.strftime('%d/%m/%y')

                if i == 0:
                    first_day = meta.get('statement_start', first_day)
                if i == len(sorted_months) - 1:
                    last_day = meta.get('statement_end', last_day)

                month_meta = {
                    **meta,
                    'opening_balance': round(opening_bal, 2),
                    'closing_balance': round(closing_bal, 2),
                    'statement_start': first_day,
                    'statement_end': last_day,
                }

                month_label = dt(year, month, 1).strftime('%b %Y')
                month_stmt = {
                    'metadata': month_meta,
                    'transactions': month_txs,
                    '_filename': stmt.get('_filename', 'unknown').replace('.pdf', f' ({month_label}).pdf'),
                    '_page_count': stmt.get('_page_count', 0),
                }
                output.append(month_stmt)
                opening_bal = closing_bal

        return output

    parsed = split_multi_month_statements(parsed)
    st.session_state.bank_parsed = parsed

    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown('<div class="section-label">Parsed Statements</div>', unsafe_allow_html=True)

    total_tx = sum(len(p.get('transactions', [])) for p in parsed)
    cols = st.columns(3)
    with cols[0]:
        st.markdown(
            f'<div class="stat-card"><div class="stat-value">{len(parsed)}</div>'
            f'<div class="stat-label">Statements Parsed</div></div>',
            unsafe_allow_html=True,
        )
    with cols[1]:
        st.markdown(
            f'<div class="stat-card"><div class="stat-value">{total_tx}</div>'
            f'<div class="stat-label">Transactions Found</div></div>',
            unsafe_allow_html=True,
        )
    with cols[2]:
        first_meta = parsed[0].get('metadata', {})
        acct = first_meta.get('account_name', 'Unknown')
        st.markdown(
            f'<div class="stat-card"><div class="stat-value" style="font-size:14px">{acct}</div>'
            f'<div class="stat-label">Account Name</div></div>',
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

    st.markdown('<div class="section-label">Reconciliation & Validation</div>', unsafe_allow_html=True)

    validation = validate_all(parsed)
    st.session_state.bank_validation = validation

    for r in validation['reconciliation_results']:
        if r['passed']:
            st.markdown(
                f'<div class="recon-pass">✓ <strong>{r["filename"]}</strong> — '
                f'Reconciled (diff: £{r["difference"]:.2f})</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="recon-fail">✗ <strong>{r["filename"]}</strong> — '
                f'FAILED — expected £{r["expected_closing"]:,.2f}, '
                f'actual £{r["actual_closing"]:,.2f}, diff £{r["difference"]:,.2f}</div>',
                unsafe_allow_html=True,
            )

    suff = validation['sufficiency']
    if suff['months_covered'] < 6:
        st.markdown(
            f'<div class="warn-box">⚠ Only {suff["months_covered"]} month(s) provided — '
            f'6 required. Missing {6 - suff["months_covered"]} month(s).</div>',
            unsafe_allow_html=True,
        )

    if validation['warnings']:
        for w in validation['warnings']:
            if 'RECONCILIATION' not in w:
                st.markdown(f'<div class="warn-box">⚠ {w}</div>', unsafe_allow_html=True)

    if not validation['all_reconciled']:
        st.markdown(
            '<div class="warn-box">⚠ One or more statements did not fully reconcile. '
            'The report will still be generated but some transaction data may be incomplete. '
            'Consider re-uploading if the differences are large.</div>',
            unsafe_allow_html=True,
        )

    if validation['can_proceed']:
        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
        if st.button("📊  Run Analytics & Generate Report", use_container_width=True):
            progress = st.progress(0)
            status = st.empty()

            status.markdown(
                '<p class="status-msg">⏳ Running credit analytics engine...</p>',
                unsafe_allow_html=True,
            )
            progress.progress(0.3)

            try:
                data = run_analytics(parsed)
                data['validation'] = st.session_state.bank_validation
                st.session_state.bank_analytics = data
                progress.progress(0.7)

                status.markdown(
                    '<p class="status-msg">⏳ Building HTML report...</p>',
                    unsafe_allow_html=True,
                )

                html = build_html_report(data)
                st.session_state.bank_report_html = html
                progress.progress(1.0)

                status.markdown(
                    '<p class="status-msg">✅ Report complete</p>',
                    unsafe_allow_html=True,
                )
                time.sleep(0.5)
                progress.empty()
                status.empty()

                st.session_state.bank_stage = "report"
                st.rerun()
            except Exception as e:
                progress.empty()
                status.empty()
                st.error(f"Analytics/report failed: {e}")
                st.exception(e)


# ════════════════════════════════════════════════════════════════════════════
# STAGE 3: REPORT DISPLAY + DOWNLOAD
# ════════════════════════════════════════════════════════════════════════════

if st.session_state.bank_stage == "report" and st.session_state.bank_report_html:
    html = st.session_state.bank_report_html
    data = st.session_state.bank_analytics

    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown('<div class="section-label">Report Ready</div>', unsafe_allow_html=True)

    if data:
        aff = data.get('affordability', {})
        cols = st.columns(4)
        with cols[0]:
            st.markdown(
                f'<div class="stat-card"><div class="stat-value">{data.get("n_months", 0)}</div>'
                f'<div class="stat-label">Months Analysed</div></div>',
                unsafe_allow_html=True,
            )
        with cols[1]:
            surplus = aff.get('surplus_full', 0)
            color = '#1A7A3C' if surplus >= 0 else '#C0392B'
            sign = '+' if surplus >= 0 else '-'
            st.markdown(
                f'<div class="stat-card"><div class="stat-value" style="color:{color}">'
                f'{sign}£{abs(surplus):,}</div>'
                f'<div class="stat-label">Avg Monthly Surplus</div></div>',
                unsafe_allow_html=True,
            )
        with cols[2]:
            max_loan = aff.get('max_loan_full_dscr', 0)
            st.markdown(
                f'<div class="stat-card"><div class="stat-value">£{max_loan:,}</div>'
                f'<div class="stat-label">Max Loan (1.5× DSCR)</div></div>',
                unsafe_allow_html=True,
            )
        with cols[3]:
            lenders_data = data.get('lenders', {})
            if 'confirmed' in lenders_data:
                n_lenders = len([v for v in lenders_data['confirmed'].values() if (v.get('total_out', 0) + v.get('total_in', 0)) > 0])
            else:
                n_lenders = len([v for v in lenders_data.values() if isinstance(v, dict) and v.get('total', 0) > 0])
            st.markdown(
                f'<div class="stat-card"><div class="stat-value">{n_lenders}</div>'
                f'<div class="stat-label">Active Lenders</div></div>',
                unsafe_allow_html=True,
            )

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

    account_name = data.get('account_name', 'Unknown') if data else 'Unknown'
    safe_name = "".join(c if c.isalnum() or c in (' ', '-', '_') else '' for c in account_name).strip().replace(' ', '_')
    filename = f"{safe_name}_Bank_Analysis_{datetime.date.today().isoformat()}.html"

    st.download_button(
        label=f"📄  Download Report — {account_name}",
        data=html.encode('utf-8'),
        file_name=filename,
        mime="text/html",
        use_container_width=True,
    )

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

    with st.expander("📊  Preview Report", expanded=False):
        st.components.v1.html(html, height=800, scrolling=True)

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

    if st.button("🔄  Analyse New Statements", use_container_width=True):
        st.session_state.bank_parsed = []
        st.session_state.bank_validation = None
        st.session_state.bank_analytics = None
        st.session_state.bank_report_html = None
        st.session_state.bank_stage = "upload"
        st.session_state.bank_accepted = []
        st.session_state.bank_rejected = []
        st.rerun()


# ── Footer ─────────────────────────────────────────────────────────────────
st.markdown("<hr>", unsafe_allow_html=True)
st.markdown(
    "<p style='text-align:center;font-size:11px;color:#aaa'>"
    "Monmouth Group · Internal use only · Bank statement analysis tool · "
    "60% APR · 12-month term · £10k–£50k range · 1.5× DSCR buffer"
    "</p>",
    unsafe_allow_html=True,
)
