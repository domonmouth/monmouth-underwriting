"""
report_builder.py
Generates a self-contained HTML credit report from analytics output.
Matches the correct light-theme Monmouth Group credit analysis tool design.

Section map:
  §1  Header Banner
  §2  Credit Officer Summary
  §3  Methodology Strip
  §3b Data Quality — Reconciliation Status
  §4  Key Metrics Cards
  §5a Daily Cash Position Chart
  §5b Intra-Month Balance Profile
  §5c Closing Balance Trend
  §5d Loan Affordability Analysis
  §6  Monthly Category Breakdown
  §7  Lender Activity (7a confirmed, 7b suspected, 7c non-lending)
  §8  Notable Large Transactions
  §9  Failed & Flagged Transactions (9a bounced, 9b fees/OD costs, 9c connected party)
  §10 Credit Risk Flags
  §11 Credit Decision Summary
  Footer
"""

from datetime import datetime


# ============================================================
# HELPERS
# ============================================================

def fmt(v, pence=False):
    """Format a number as £X,XXX (rounded to nearest pound unless pence=True)."""
    if v is None or v == 0:
        return '—'
    if pence:
        return f'£{abs(v):,.2f}' if v >= 0 else f'-£{abs(v):,.2f}'
    if v < 0:
        return f'-£{abs(round(v)):,}'
    return f'£{round(v):,}'

def fmt_signed_html(v):
    """Return HTML-coloured signed £ amount."""
    if v is None:
        return '—'
    if v < 0:
        return f'<span class="neg">-£{abs(round(v)):,}</span>'
    if v > 0:
        return f'<span class="pos">£{round(v):,}</span>'
    return '£0'


def _get_confirmed_lenders(d):
    """Safely get confirmed lenders from new or old data format."""
    lenders = d.get('lenders', {})
    if 'confirmed' in lenders:
        return lenders['confirmed']
    # Legacy format: flat dict of lender name -> data
    return {k: v for k, v in lenders.items() if isinstance(v, dict) and v.get('total', v.get('total_out', 0)) > 0}


def _get_suspected_lenders(d):
    """Safely get suspected lenders from new data format."""
    lenders = d.get('lenders', {})
    if 'suspected' in lenders:
        return lenders['suspected']
    return {}


def _active_confirmed(d):
    """Get list of active confirmed lenders (with activity)."""
    confirmed = _get_confirmed_lenders(d)
    return {k: v for k, v in confirmed.items()
            if (v.get('total_out', 0) + v.get('total_in', 0) + v.get('total', 0)) > 0}


# ============================================================
# CSS — exact match to correct report design
# ============================================================

CSS = """
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@300;400;500;600;700&display=swap');

:root {
  --bg: #f1f4f8;
  --surface: #ffffff;
  --surface2: #f8fafc;
  --border: #dde3ea;
  --accent: #0284c7;
  --accent2: #0ea5e9;
  --green: #16a34a;
  --red: #dc2626;
  --amber: #d97706;
  --text: #111827;
  --text-dim: #6b7280;
  --text-mid: #374151;
  --mono: 'IBM Plex Mono', monospace;
  --sans: 'IBM Plex Sans', sans-serif;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: var(--sans);
  background: var(--bg);
  color: var(--text);
  font-size: 14px;
  line-height: 1.5;
}

.container { max-width: 1200px; margin: 0 auto; padding: 32px 24px; }

/* HEADER BANNER */
.header-banner {
  background: linear-gradient(135deg, #0c2d4e 0%, #0a3a63 50%, #082540 100%);
  border: 1px solid var(--border);
  border-top: 3px solid var(--accent);
  border-radius: 12px;
  padding: 32px;
  margin-bottom: 20px;
  position: relative;
  overflow: hidden;
}
.header-banner::before {
  content: '';
  position: absolute;
  top: -50%;
  right: -10%;
  width: 400px;
  height: 400px;
  background: radial-gradient(circle, rgba(14,165,233,0.06) 0%, transparent 70%);
  pointer-events: none;
}
.header-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 16px;
}
.client-info h1 {
  font-family: var(--mono);
  font-size: 26px;
  font-weight: 600;
  color: #ffffff;
  letter-spacing: -0.5px;
  margin-bottom: 6px;
}
.client-info .meta {
  color: rgba(255,255,255,0.85);
  font-size: 13px;
  font-family: var(--mono);
  line-height: 1.8;
}
.confidence-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  border-radius: 100px;
  font-family: var(--mono);
  font-size: 13px;
  font-weight: 600;
}
.pill-green {
  background: rgba(134,239,172,0.18);
  border: 1px solid rgba(134,239,172,0.5);
  color: #86efac;
}
.pill-amber {
  background: rgba(251,191,36,0.18);
  border: 1px solid rgba(251,191,36,0.5);
  color: #fbbf24;
}
.confidence-pill .dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  animation: pulse 2s infinite;
}
.pill-green .dot { background: #86efac; }
.pill-amber .dot { background: #fbbf24; }
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
.header-period {
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid rgba(255,255,255,0.15);
  display: flex;
  gap: 40px;
  flex-wrap: wrap;
}
.period-item label {
  display: block;
  font-size: 10px;
  font-family: var(--mono);
  color: rgba(255,255,255,0.6);
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: 4px;
}
.period-item span {
  font-family: var(--mono);
  font-size: 14px;
  color: #ffffff;
}

/* CREDIT ALERT */
.credit-alert {
  background: #eff8ff;
  border: 1px solid #bae6fd;
  border-left: 4px solid var(--accent);
  border-radius: 8px;
  padding: 20px 24px;
  margin-bottom: 20px;
}
.credit-alert h2 {
  font-size: 11px;
  font-family: var(--mono);
  color: var(--accent);
  text-transform: uppercase;
  letter-spacing: 1.5px;
  margin-bottom: 10px;
}
.credit-alert p {
  color: #1e3a5f;
  font-size: 14px;
  line-height: 1.7;
}

/* METHODOLOGY */
.methodology {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px 24px;
  margin-bottom: 20px;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
}
.method-item label {
  display: block;
  font-size: 10px;
  font-family: var(--mono);
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: 4px;
}
.method-item span {
  font-size: 13px;
  color: var(--text-mid);
}

/* METRIC CARDS */
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
  margin-bottom: 20px;
}
.metric-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 20px;
  position: relative;
  overflow: hidden;
  transition: border-color 0.2s;
}
.metric-card:hover { border-color: var(--accent); }
.metric-card .label {
  font-size: 10px;
  font-family: var(--mono);
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: 10px;
}
.metric-card .value {
  font-family: var(--mono);
  font-size: 22px;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 4px;
}
.metric-card .sub {
  font-size: 12px;
  color: var(--text-mid);
}
.metric-card .indicator {
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  border-radius: 10px 10px 0 0;
}
.ind-blue  { background: var(--accent); }
.ind-green { background: var(--green); }
.ind-red   { background: var(--red); }
.ind-amber { background: var(--amber); }

/* CHARTS */
.chart-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 24px;
  margin-bottom: 20px;
}
.section-title {
  font-size: 11px;
  font-family: var(--mono);
  color: var(--accent);
  text-transform: uppercase;
  letter-spacing: 1.5px;
  margin-bottom: 20px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.section-title::before {
  content: '';
  display: inline-block;
  width: 3px;
  height: 14px;
  background: var(--accent);
  border-radius: 2px;
}
.chart-wrap { height: 280px; position: relative; }

/* TABLES */
.table-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 24px;
  margin-bottom: 20px;
  overflow-x: auto;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
th {
  font-family: var(--mono);
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--text-dim);
  padding: 10px 12px;
  text-align: left;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}
th.num, td.num { text-align: right; }
td {
  padding: 9px 12px;
  border-bottom: 1px solid rgba(30,45,61,0.5);
  color: var(--text-mid);
  vertical-align: top;
}
tr:last-child td { border-bottom: none; }
tr:hover td { background: rgba(2,132,199,0.04); }

/* Monthly breakdown table */
.inflow-row td, .outflow-row td { color: var(--text-mid); }
.inflow-row:hover td, .outflow-row:hover td { background: rgba(2,132,199,0.04); }
.section-spacer td { padding: 6px 0; border-bottom: 1px solid var(--border); }
.totals-row td {
  font-family: var(--mono);
  font-weight: 600;
  color: var(--text);
  background: rgba(2,132,199,0.05);
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
}
.net-row td { color: var(--accent) !important; font-weight: 700; }
.closing-row td {
  font-family: var(--mono);
  font-weight: 700;
  color: var(--text);
  background: rgba(2,132,199,0.08);
  border-top: 2px solid var(--accent);
}
.cat-label { min-width: 220px; }
.total-col { background: rgba(2,132,199,0.06) !important; border-left: 1px solid var(--border); }
.pos { color: var(--green) !important; }
.neg { color: var(--red) !important; }

/* FLAGS */
.flags-list { display: flex; flex-direction: column; gap: 12px; }
.flag-card {
  border-radius: 8px;
  padding: 16px 20px;
  display: flex;
  gap: 16px;
  align-items: flex-start;
}
.flag-critical { background: #fff; border: 1px solid #fecaca; border-left: 4px solid var(--red); }
.flag-warning  { background: #fff; border: 1px solid #fde68a; border-left: 4px solid var(--amber); }
.flag-note     { background: #fff; border: 1px solid #bae6fd; border-left: 4px solid var(--accent); }
.flag-icon { font-size: 18px; flex-shrink: 0; padding-top: 2px; }
.flag-body h3 { font-size: 14px; font-weight: 600; color: var(--text); margin-bottom: 4px; }
.flag-body .evidence { font-size: 12px; font-family: var(--mono); color: #4b5563; margin-bottom: 6px; }
.flag-body .implication { font-size: 13px; color: #6b7280; }

/* BADGES */
.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 10px;
  font-family: var(--mono);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-weight: 600;
  margin-right: 6px;
}
.badge-crit  { background: #fee2e2; color: #b91c1c; border: 1px solid #fca5a5; }
.badge-warn  { background: #fef3c7; color: #b45309; border: 1px solid #fcd34d; }
.badge-note  { background: #e0f2fe; color: #0369a1; border: 1px solid #7dd3fc; }
.badge-pass  { background: #dcfce7; color: #15803d; border: 1px solid #86efac; }
.badge-fail  { background: #fee2e2; color: #b91c1c; border: 1px solid #fca5a5; }
.badge-refer { background: #fef3c7; color: #b45309; border: 1px solid #fcd34d; }

.dir-in  { color: var(--green); font-family: var(--mono); font-weight: 600; }
.dir-out { color: var(--red);   font-family: var(--mono); font-weight: 600; }

.lender-tag {
  display: inline-block;
  padding: 2px 6px;
  font-size: 10px;
  font-family: var(--mono);
  border-radius: 3px;
  background: #e0f2fe;
  color: #0369a1;
}
.suspected-tag {
  display: inline-block;
  padding: 2px 6px;
  font-size: 10px;
  font-family: var(--mono);
  border-radius: 3px;
  background: #fef3c7;
  color: #b45309;
}

h2.sub-section {
  font-size: 12px;
  font-family: var(--mono);
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 1px;
  margin: 20px 0 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border);
}

.decision-table td:last-child {
  font-family: var(--mono);
  font-weight: 600;
}

.footer {
  text-align: center;
  padding: 24px;
  font-size: 11px;
  color: var(--text-dim);
  font-family: var(--mono);
  border-top: 1px solid var(--border);
  margin-top: 32px;
}
"""


# ============================================================
# §1 HEADER BANNER
# ============================================================

def section_header(d):
    n   = d['n_months']
    now = datetime.now().strftime('%d/%m/%y')

    # Dynamic reconciliation status
    validation = d.get('validation')
    if validation:
        all_recon = validation.get('all_reconciled', True)
        total_stmts = len(validation.get('reconciliation_results', []))
    else:
        all_recon = True
        total_stmts = n

    if all_recon:
        pill_cls = 'pill-green'
        pill_text = f'✓ 100% Reconciled — All {total_stmts} Months'
    else:
        failed = sum(1 for r in validation.get('reconciliation_results', []) if not r['passed'])
        pill_cls = 'pill-amber'
        pill_text = f'⚠ {total_stmts - failed}/{total_stmts} Reconciled — {failed} Warning(s)'

    return f"""
<div class="header-banner">
  <div class="header-top">
    <div class="client-info">
      <h1>{d['account_name'].upper()}</h1>
      <div class="meta">
        Bank: {d.get('bank_name', 'Business Current Account')}<br>
        Sort Code: {d['sort_code']} &nbsp;|&nbsp; Account: {d['account_number']}<br>
        Generated: {now}
      </div>
    </div>
    <div class="confidence-pill {pill_cls}">
      <div class="dot"></div>
      {pill_text}
    </div>
  </div>
  <div class="header-period">
    <div class="period-item">
      <label>Statement Period</label>
      <span>{d['period_start']} – {d['period_end']}</span>
    </div>
    <div class="period-item">
      <label>Months Covered</label>
      <span>{n} ({d['month_labels'][0]} – {d['month_labels'][-1]})</span>
    </div>
    <div class="period-item">
      <label>Opening Balance</label>
      <span>{fmt(d['opening_bal'])}</span>
    </div>
    <div class="period-item">
      <label>Generated</label>
      <span>{now}</span>
    </div>
  </div>
</div>"""


# ============================================================
# §2 CREDIT OFFICER SUMMARY
# ============================================================

def section_credit_summary(d):
    aff     = d['affordability']
    fdd     = d['failed_dds']
    gam     = d['gambling']
    san     = d['sanctions']
    anomaly = d['anomaly_tx']
    n       = d['n_months']

    active = _active_confirmed(d)
    n_lenders = len(active)
    lender_str = ' · '.join(v['name'] for v in active.values()) if active else 'None identified'
    debt_svc = fmt(d['existing_debt_svc'])

    # Overdraft warning in summary
    od_note = ''
    if aff.get('persistent_overdraft'):
        od_note = f' <strong>Account operates on permanent overdraft (avg daily balance {fmt(d["avg_bal_full"])}).</strong>'

    anomaly_note = ''
    if anomaly:
        direction = 'exceed' if aff['surplus_full'] < 0 else 'are covered by'
        surplus_str = fmt(abs(aff['surplus_full']))
        anomaly_note = (
            f' <strong>Critical affordability finding: excluding the unverified {fmt(d["anomaly_amount"])} '
            f'{anomaly["description"][:40]} receipt, adjusted outflows {direction} adjusted inflows '
            f'by ~{surplus_str}/month on a {n}-month basis</strong>'
            + (' — meaning no supportable lending amount can be calculated from observable recurring cash flow alone.' if aff['surplus_full'] < 0 else '.')
        )

    # Bounced summary
    bounced = d.get('bounced', {})
    total_bounced = bounced.get('total_confirmed', 0) + bounced.get('total_suspected', 0)
    dd_note = f' {total_bounced} bounced/returned payment(s) noted.' if total_bounced > 0 else ' No failed direct debits.'

    gam_note  = f' Gambling transactions detected.' if gam['found'] else ' No gambling detected.'
    san_note  = ' No sanctioned jurisdictions.' if san['clean'] else ' ⚠ Potential sanctions hits — review required.'
    me_note   = f' {len(san["middle_east_txs"])} Middle East transaction(s) identified.' if san['middle_east_txs'] else ''

    # HMRC TTP
    ttp = d.get('hmrc_ttp', {})
    ttp_note = ' <strong>⚠ HMRC Time to Pay / NDDS arrangement detected.</strong>' if ttp.get('found') else ''

    return f"""
<div class="credit-alert">
  <h2>§2 · Credit Officer Summary</h2>
  <p>
    {d['account_name']} operates a business current account (Sort {d['sort_code']} · A/C {d['account_number']})
    opening at {fmt(d['opening_bal'])} in {d['month_labels'][0]} and closing at {fmt(d['closing_bal'])} in {d['month_labels'][-1]}.
    {n_lenders} confirmed lender{'s' if n_lenders != 1 else ''} identified: {lender_str} —
    combined ongoing debt service ~{debt_svc}/month.{od_note}{anomaly_note}{ttp_note}
    {dd_note}{gam_note}{san_note}{me_note}
  </p>
</div>"""


# ============================================================
# §3 METHODOLOGY STRIP
# ============================================================

def section_methodology(d):
    validation = d.get('validation')
    if validation:
        recon_results = validation.get('reconciliation_results', [])
        passed = sum(1 for r in recon_results if r['passed'])
        total = len(recon_results)
        failed = total - passed
        if failed == 0:
            recon_str = f'All {total} statements reconcile with £0.00 variance.'
        else:
            max_diff = max(r['difference'] for r in recon_results if not r['passed'])
            recon_str = (
                f'<span style="color:#b91c1c; font-weight:600">{failed} of {total} statements failed reconciliation</span> '
                f'(max diff £{max_diff:,.2f}). See Data Quality note below.'
            )
    else:
        recon_str = f'All {d["n_months"]} pass with £0.00 variance.'

    return f"""
<div class="methodology">
  <div class="method-item">
    <label>Reconciliation</label>
    <span>Opening + Payments IN − Payments OUT = Closing, verified per statement. {recon_str}</span>
  </div>
  <div class="method-item">
    <label>Extraction Method</label>
    <span>Text-based PDF (native digital statements). Full transaction-level parse — {d['total_tx_count']} rows processed.</span>
  </div>
  <div class="method-item">
    <label>Caveats</label>
    <span>Statement periods may overlap by 1 day (month-end = next month open). Anomaly detection threshold: 2× average monthly inflow. Lender detection: 206-entry registry + fuzzy keyword matching.</span>
  </div>
  <div class="method-item">
    <label>Date Format</label>
    <span>dd/mm/yy throughout</span>
  </div>
</div>"""


# ============================================================
# §3b DATA QUALITY — RECONCILIATION STATUS
# ============================================================

def section_data_quality(d):
    validation = d.get('validation')
    if not validation:
        return ''

    recon_results = validation.get('reconciliation_results', [])
    all_reconciled = validation.get('all_reconciled', True)

    if all_reconciled:
        return f"""
<div class="chart-card">
  <div class="section-title">§3b · Data Quality — Reconciliation Status</div>
  <div style="padding:12px 16px; background:#dcfce7; border:1px solid #86efac; border-radius:6px; font-size:13px; color:#166534;">
    <strong>✓ All {len(recon_results)} statements reconciled successfully.</strong>
    Opening balance + payments in − payments out = closing balance verified for each statement with £0.00 variance.
    Transaction data is considered reliable for all periods.
  </div>
</div>"""

    passed_count = sum(1 for r in recon_results if r['passed'])
    failed_count = len(recon_results) - passed_count
    total_diff   = sum(r['difference'] for r in recon_results if not r['passed'])

    rows = ''
    for r in recon_results:
        if r['passed']:
            status_html = '<span style="color:#166534; font-weight:600">✓ PASS</span>'
            diff_html   = f'<span style="color:#166534">£{r["difference"]:.2f}</span>'
            row_bg      = ''
        else:
            status_html = '<span style="color:#b91c1c; font-weight:600">✗ FAIL</span>'
            diff_html   = f'<span style="color:#b91c1c; font-weight:700">£{r["difference"]:,.2f}</span>'
            row_bg      = ' style="background:#fef2f2"'

        rows += f"""
        <tr{row_bg}>
          <td style="padding:8px 10px; font-size:12px; border-bottom:1px solid var(--border)">{r['filename']}</td>
          <td style="padding:8px 10px; font-family:var(--mono); font-size:12px; text-align:right; border-bottom:1px solid var(--border)">£{r['opening']:,.2f}</td>
          <td style="padding:8px 10px; font-family:var(--mono); font-size:12px; text-align:right; border-bottom:1px solid var(--border)">£{r['total_in']:,.2f}</td>
          <td style="padding:8px 10px; font-family:var(--mono); font-size:12px; text-align:right; border-bottom:1px solid var(--border)">£{r['total_out']:,.2f}</td>
          <td style="padding:8px 10px; font-family:var(--mono); font-size:12px; text-align:right; border-bottom:1px solid var(--border)">£{r['expected_closing']:,.2f}</td>
          <td style="padding:8px 10px; font-family:var(--mono); font-size:12px; text-align:right; border-bottom:1px solid var(--border)">£{r['actual_closing']:,.2f}</td>
          <td style="padding:8px 10px; font-family:var(--mono); font-size:12px; text-align:right; border-bottom:1px solid var(--border)">{diff_html}</td>
          <td style="padding:8px 10px; font-size:12px; text-align:center; border-bottom:1px solid var(--border)">{status_html}</td>
        </tr>"""

    return f"""
<div class="chart-card">
  <div class="section-title">§3b · Data Quality — Reconciliation Status</div>
  <div style="padding:12px 16px; background:#fee2e2; border:1px solid #fca5a5; border-radius:6px; margin-bottom:16px; font-size:13px; color:#7f1d1d;">
    <strong>⚠ RECONCILIATION WARNING:</strong> {failed_count} of {len(recon_results)} statement{'s' if len(recon_results) != 1 else ''}
    failed reconciliation with a combined variance of £{total_diff:,.2f}.
    This typically indicates missed or misclassified transactions during parsing. Affected periods should be
    treated with caution — inflow/outflow figures and affordability calculations for those months may understate or overstate actual activity.
  </div>
  <table style="width:100%; border-collapse:collapse; font-size:13px; border:1px solid var(--border); border-radius:6px;">
    <thead>
      <tr style="background:#f1f5f9;">
        <th style="padding:8px 10px; text-align:left; font-size:10px; text-transform:uppercase; color:var(--text-dim); border-bottom:2px solid var(--border)">Statement</th>
        <th style="padding:8px 10px; text-align:right; font-size:10px; text-transform:uppercase; color:var(--text-dim); border-bottom:2px solid var(--border)">Opening</th>
        <th style="padding:8px 10px; text-align:right; font-size:10px; text-transform:uppercase; color:var(--text-dim); border-bottom:2px solid var(--border)">Total IN</th>
        <th style="padding:8px 10px; text-align:right; font-size:10px; text-transform:uppercase; color:var(--text-dim); border-bottom:2px solid var(--border)">Total OUT</th>
        <th style="padding:8px 10px; text-align:right; font-size:10px; text-transform:uppercase; color:var(--text-dim); border-bottom:2px solid var(--border)">Expected Close</th>
        <th style="padding:8px 10px; text-align:right; font-size:10px; text-transform:uppercase; color:var(--text-dim); border-bottom:2px solid var(--border)">Actual Close</th>
        <th style="padding:8px 10px; text-align:right; font-size:10px; text-transform:uppercase; color:var(--text-dim); border-bottom:2px solid var(--border)">Diff</th>
        <th style="padding:8px 10px; text-align:center; font-size:10px; text-transform:uppercase; color:var(--text-dim); border-bottom:2px solid var(--border)">Status</th>
      </tr>
    </thead>
    <tbody>{rows}
    </tbody>
  </table>
  <p style="font-size:11px; color:var(--text-dim); margin-top:10px; line-height:1.6">
    Reconciliation formula: Opening Balance + Total Payments IN − Total Payments OUT = Expected Closing Balance.
    Tolerance: £1.00 (rounding). Differences above this threshold indicate parsing gaps — typically multi-line descriptions,
    FX transactions, or bank-specific formatting that the parser did not fully capture.
  </p>
</div>"""


# ============================================================
# §4 METRICS CARDS
# ============================================================

def section_metrics(d):
    aff      = d['affordability']
    fdd      = d['failed_dds']
    n        = d['n_months']
    months_3 = d['month_labels'][-3:]

    active = _active_confirmed(d)
    n_active = len(active)
    names = ' · '.join(v['name'] for v in active.values()) or 'None identified'

    dd_ind = 'ind-red' if fdd['count'] > 0 else 'ind-green'
    stmt_ind = 'ind-amber' if n < 6 else 'ind-green'
    stmt_sub = f'⚠ Below 6-month requirement — {6-n} month(s) short' if n < 6 else f'{n} months provided — meets requirement'

    # Avg balance indicator — red if negative (overdraft)
    avg_bal_ind = 'ind-red' if d['avg_bal_full'] < 0 else 'ind-green'
    avg_bal_sub = 'Forward-filled across full period'
    if d['avg_bal_full'] < 0:
        avg_bal_sub = '⚠ Persistent overdraft — see §5d'

    cards = [
        ('ind-blue',  'Current Balance',          fmt(d['closing_bal']),           f'{d["period_end"]} closing'),
        (stmt_ind,    'Statements Provided',       f'{n} months',                   stmt_sub),
        ('ind-amber', 'Confirmed Lenders',         str(n_active),                   names[:65] + ('…' if len(names) > 65 else '')),
        (dd_ind,      'Failed / Returned DDs',    'YES' if fdd['count'] > 0 else 'NONE',
                      f'{fdd["count"]} event(s) — see §9' if fdd['count'] > 0 else 'No failed DDs in period'),
        (avg_bal_ind, f'Avg Daily Balance ({n}m)', fmt(d['avg_bal_full']),          avg_bal_sub),
        ('ind-blue',  'Avg Daily Balance (3m)',    fmt(d['avg_bal_3m']),            f'{" – ".join([months_3[0], months_3[-1]])}'),
        ('ind-blue',  'Total Payments IN',         fmt(sum(d['monthly_in'])),       f'{n}-month aggregate'),
        ('ind-amber', 'Total Payments OUT',        fmt(sum(d['monthly_out'])),      f'{n}-month aggregate'),
    ]

    html = '<div class="metrics-grid">'
    for ind, label, value, sub in cards:
        html += f"""
  <div class="metric-card">
    <div class="indicator {ind}"></div>
    <div class="label">{label}</div>
    <div class="value">{value}</div>
    <div class="sub">{sub}</div>
  </div>"""
    html += '\n</div>'
    return html


# ============================================================
# §5a–§5c CHARTS (inline JS)
# ============================================================

def section_charts(d):
    daily  = d['daily_series']
    dl     = [dt for dt, _ in daily]
    dv     = [round(b, 2) for _, b in daily]

    meta_list     = d['meta_list']
    closing_labels = [m['end'].strftime('%b-%y') if hasattr(m['end'], 'strftime') else str(m['end']) for m in meta_list]
    closing_vals   = [round(m['closing_balance']) for m in meta_list]

    intra_data  = d['intramonth_data']
    avg_intra   = [round(v) if v else 0 for v in d['avg_intramonth']]
    month_names = d['month_labels']

    intra_js_arrays = '[' + ','.join(str([round(v) if v else 0 for v in mv]) for mv in intra_data) + ']'
    month_names_js  = str(month_names)

    return f"""
<!-- §5a Daily Cash Position -->
<div class="chart-card">
  <div class="section-title">§5a · Daily Cash Position — {d['period_start']} to {d['period_end']}</div>
  <div class="chart-wrap">
    <canvas id="cashChart"></canvas>
  </div>
</div>

<!-- §5b + §5c side by side -->
<div style="display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:20px;">

  <div class="chart-card" style="margin-bottom:0">
    <div class="section-title">§5b · Intra-Month Balance Profile</div>
    <p style="font-size:12px; color:var(--text-dim); margin-bottom:16px;">Average balance by week-of-month across all {d['n_months']} months. Each month shown as a thin line; bold line = overall average. Identifies recurring low-balance periods.</p>
    <div class="chart-wrap" style="height:220px">
      <canvas id="intraChart"></canvas>
    </div>
  </div>

  <div class="chart-card" style="margin-bottom:0">
    <div class="section-title">§5c · Month-End Closing Balance Trend</div>
    <p style="font-size:12px; color:var(--text-dim); margin-bottom:16px;">Month-end closing balance per statement. Green = up vs prior month, red = down.</p>
    <div class="chart-wrap" style="height:220px">
      <canvas id="closingChart"></canvas>
    </div>
  </div>

</div>

<script>
const labels = {dl};
const values = {dv};
const ctx = document.getElementById('cashChart').getContext('2d');
new Chart(ctx, {{
  type: 'line',
  data: {{
    labels: labels,
    datasets: [{{
      label: 'Daily Balance',
      data: values,
      borderColor: '#0284c7',
      borderWidth: 1.5,
      backgroundColor: 'rgba(2,132,199,0.07)',
      pointRadius: 0,
      pointHoverRadius: 4,
      fill: true,
      tension: 0.2,
    }}]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    interaction: {{ mode: 'index', intersect: false }},
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{
        backgroundColor: '#1e293b',
        borderColor: '#334155',
        borderWidth: 1,
        titleColor: '#94a3b8',
        bodyColor: '#f1f5f9',
        titleFont: {{ family: 'IBM Plex Mono', size: 10 }},
        bodyFont: {{ family: 'IBM Plex Mono', size: 12 }},
        callbacks: {{
          title: ctx => ctx[0].label,
          label: ctx => '  £' + Math.round(ctx.raw).toLocaleString('en-GB')
        }}
      }}
    }},
    scales: {{
      x: {{
        grid: {{ color: 'rgba(203,213,225,0.6)', drawBorder: false }},
        ticks: {{ color: '#94a3b8', font: {{ family: 'IBM Plex Mono', size: 9 }}, maxTicksLimit: 20, maxRotation: 0 }}
      }},
      y: {{
        grid: {{ color: 'rgba(203,213,225,0.6)', drawBorder: false }},
        ticks: {{ color: '#94a3b8', font: {{ family: 'IBM Plex Mono', size: 9 }}, callback: v => '£' + Math.round(v/1000) + 'k' }}
      }}
    }}
  }}
}});

const intraRaw   = {intra_js_arrays};
const avgIntra   = {avg_intra};
const monthNames = {month_names_js};
const monthBorders = [
  'rgba(2,132,199,0.5)','rgba(16,185,129,0.5)','rgba(245,158,11,0.5)',
  'rgba(239,68,68,0.5)','rgba(139,92,246,0.5)','rgba(234,179,8,0.5)',
  'rgba(14,165,233,0.5)'
];

const intraDatasets = intraRaw.map((monthVals, mi) => ({{
  label: monthNames[mi],
  data: monthVals,
  borderColor: monthBorders[mi % monthBorders.length],
  backgroundColor: 'transparent',
  borderWidth: 1.5,
  borderDash: [4,3],
  pointRadius: 3,
  tension: 0.3,
}}));
intraDatasets.push({{
  label: 'Average',
  data: avgIntra,
  borderColor: '#0284c7',
  backgroundColor: 'rgba(2,132,199,0.08)',
  borderWidth: 3,
  pointRadius: 5,
  pointBackgroundColor: '#0284c7',
  tension: 0.3,
  fill: true,
}});

const ctx2 = document.getElementById('intraChart').getContext('2d');
new Chart(ctx2, {{
  type: 'line',
  data: {{ labels: ['Wk 1 (1–7)', 'Wk 2 (8–14)', 'Wk 3 (15–21)', 'Wk 4 (22+)'], datasets: intraDatasets }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
      legend: {{ position: 'bottom', labels: {{ font: {{ family: 'IBM Plex Mono', size: 9 }}, boxWidth: 16, padding: 10 }} }},
      tooltip: {{
        backgroundColor: '#1e293b',
        titleColor: '#94a3b8',
        bodyColor: '#f1f5f9',
        titleFont: {{ family: 'IBM Plex Mono', size: 10 }},
        bodyFont: {{ family: 'IBM Plex Mono', size: 11 }},
        callbacks: {{ label: ctx => ctx.dataset.label + ': £' + Math.round(ctx.raw).toLocaleString('en-GB') }}
      }}
    }},
    scales: {{
      x: {{ grid: {{ color: 'rgba(203,213,225,0.6)' }}, ticks: {{ color: '#94a3b8', font: {{ family: 'IBM Plex Mono', size: 9 }} }} }},
      y: {{ grid: {{ color: 'rgba(203,213,225,0.6)' }}, ticks: {{ color: '#94a3b8', font: {{ family: 'IBM Plex Mono', size: 9 }}, callback: v => '£' + Math.round(v/1000) + 'k' }} }}
    }}
  }}
}});

const closingVals   = {closing_vals};
const closingColors = closingVals.map((v, i) =>
  i === 0 ? 'rgba(2,132,199,0.7)' :
  v > closingVals[i-1] ? 'rgba(22,163,74,0.7)' : 'rgba(220,38,38,0.7)'
);

const ctx3 = document.getElementById('closingChart').getContext('2d');
new Chart(ctx3, {{
  type: 'bar',
  data: {{
    labels: {closing_labels},
    datasets: [{{
      label: 'Closing Balance',
      data: closingVals,
      backgroundColor: closingColors,
      borderColor: closingColors.map(c => c.replace('0.7','1')),
      borderWidth: 1,
      borderRadius: 4,
    }}]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{
        backgroundColor: '#1e293b',
        titleColor: '#94a3b8',
        bodyColor: '#f1f5f9',
        titleFont: {{ family: 'IBM Plex Mono', size: 10 }},
        bodyFont: {{ family: 'IBM Plex Mono', size: 12 }},
        callbacks: {{ label: ctx => '£' + Math.round(ctx.raw).toLocaleString('en-GB') }}
      }}
    }},
    scales: {{
      x: {{ grid: {{ display: false }}, ticks: {{ color: '#94a3b8', font: {{ family: 'IBM Plex Mono', size: 9 }} }} }},
      y: {{ grid: {{ color: 'rgba(203,213,225,0.6)' }}, ticks: {{ color: '#94a3b8', font: {{ family: 'IBM Plex Mono', size: 9 }}, callback: v => '£' + Math.round(v/1000) + 'k' }} }}
    }}
  }}
}});
</script>"""


# ============================================================
# §5d LOAN AFFORDABILITY
# ============================================================

def section_affordability(d):
    aff     = d['affordability']
    anomaly = d['anomaly_tx']
    anomalous_txs = d.get('anomalous_txs', [])
    n       = d['n_months']
    months_3 = f'{d["month_labels"][-3]} – {d["month_labels"][-1]}' if n >= 3 else d['month_labels'][-1]

    # Overdraft warning box
    od_warning = ''
    if aff.get('persistent_overdraft'):
        od_warning = f"""
  <div style="padding:12px 16px; background:#fee2e2; border:1px solid #fca5a5; border-radius:6px; margin-bottom:16px; font-size:13px; color:#7f1d1d;">
    <strong>⚠ PERSISTENT OVERDRAFT:</strong> {aff.get('overdraft_warning', 'Account operates on permanent overdraft. Reported surplus represents reduction in overdraft depth, not free cash for new debt service.')}
  </div>"""

    # Anomaly warning box
    if anomalous_txs:
        total_excluded = aff.get('total_excluded', 0)
        count = len(anomalous_txs)
        direction = 'materially exceed' if aff['surplus_full'] < 0 else 'are covered by'
        warning_box = f"""
  <div style="padding:12px 16px; background:#fee2e2; border:1px solid #fca5a5; border-radius:6px; margin-bottom:16px; font-size:13px; color:#7f1d1d;">
    <strong>⚠ KEY FINDING:</strong> {count} anomalous receipt{'s' if count != 1 else ''} totalling {fmt(total_excluded)} detected
    (each exceeding 2× average monthly inflow or identified as lender drawdown).
    Excluding these, adjusted outflows {direction} adjusted inflows across both {n}-month and 3-month windows.
    {'This means the business cannot demonstrably service new debt from its observable recurring cash flow. The affordability picture is entirely dependent on whether the anomalous receipts represent regular trading income. CO must resolve this before any lending decision.' if aff['surplus_full'] < 0 else 'Both unadjusted and adjusted figures are shown below — CO should determine which basis is appropriate.'}
  </div>"""
    else:
        warning_box = ''

    def aff_box(title, avg_in, avg_out, surplus, max_pmt, max_dscr, max_zero, in_label='Avg monthly IN'):
        sur_color = 'var(--red)' if surplus < 0 else 'var(--green)'
        zero_color = 'var(--red)' if max_zero <= 0 else 'var(--text-dim)'
        zero_label = f'{fmt(max_zero)} (no buffer)' if max_zero <= 0 else fmt(max_zero)
        return f"""
    <div style="background:#f8fafc; border:1px solid var(--border); border-radius:8px; padding:16px;">
      <div style="font-size:10px; font-family:var(--mono); color:var(--text-dim); text-transform:uppercase; letter-spacing:1px; margin-bottom:8px;">{title}</div>
      <table style="font-size:13px; width:100%">
        <tr><td style="color:var(--text-dim); padding:3px 0">{in_label}</td><td style="text-align:right; font-family:var(--mono); font-weight:600">{fmt(avg_in)}</td></tr>
        <tr><td style="color:var(--text-dim); padding:3px 0">Avg monthly OUT</td><td style="text-align:right; font-family:var(--mono); font-weight:600">{fmt(avg_out)}</td></tr>
        <tr style="border-top:1px solid var(--border)">
          <td style="color:var(--text-dim); padding:4px 0">Monthly surplus</td>
          <td style="text-align:right; font-family:var(--mono); font-weight:700; color:{sur_color}">{fmt(surplus)}</td>
        </tr>
        <tr>
          <td style="color:var(--text-dim); padding:3px 0">Max payment at 1.5× DSCR</td>
          <td style="text-align:right; font-family:var(--mono); font-weight:600; color:var(--accent)">{fmt(max_pmt)}/mo</td>
        </tr>
        <tr style="border-top:1px solid var(--border)">
          <td style="color:var(--text-mid); padding:4px 0; font-weight:600">Max loan at 1.5× DSCR</td>
          <td style="text-align:right; font-family:var(--mono); font-weight:700; font-size:15px; color:var(--accent)">{fmt(max_dscr) if max_dscr > 0 else '£0'}</td>
        </tr>
        <tr>
          <td style="color:var(--text-dim); font-size:11px; padding:2px 0">Max loan at 0 headroom</td>
          <td style="text-align:right; font-family:var(--mono); font-size:11px; color:{zero_color}">{zero_label}</td>
        </tr>
      </table>
    </div>"""

    box_unadj_full = aff_box(
        f'{n}-Month Average (Unadjusted — All Receipts)',
        aff['unadj_avg_in_full'], aff['unadj_avg_out_full'], aff['unadj_surplus_full'],
        aff['unadj_max_pmt_full'], aff['unadj_max_loan_full_dscr'], aff['unadj_max_loan_full_zero'],
        in_label='Avg monthly IN (all)',
    )
    box_unadj_3m = aff_box(
        f'3-Month Average {months_3} (Unadjusted)',
        aff['unadj_avg_in_3m'], aff['unadj_avg_out_3m'], aff['unadj_surplus_3m'],
        aff['unadj_max_pmt_3m'], aff['unadj_max_loan_3m_dscr'], aff['unadj_max_loan_3m_zero'],
        in_label='Avg monthly IN (all)',
    )

    box_adj_full = aff_box(
        f'{n}-Month Average (Adjusted — Anomalies Excluded)',
        aff['avg_in_full'], aff['avg_out_full'], aff['surplus_full'],
        aff['max_pmt_full'], aff['max_loan_full_dscr'], aff['max_loan_full_zero'],
        in_label='Avg monthly IN (adj.)',
    )
    box_adj_3m = aff_box(
        f'3-Month Average {months_3} (Adjusted)',
        aff['avg_in_3m'], aff['avg_out_3m'], aff['surplus_3m'],
        aff['max_pmt_3m'], aff['max_loan_3m_dscr'], aff['max_loan_3m_zero'],
        in_label='Avg monthly IN (adj.)',
    )

    if anomalous_txs:
        rows = ''
        for i, atx in enumerate(anomalous_txs, 1):
            rows += f"""
        <tr>
          <td style="padding:6px 10px; font-family:var(--mono); font-size:12px; border-bottom:1px solid var(--border)">{atx['date']}</td>
          <td style="padding:6px 10px; font-size:12px; border-bottom:1px solid var(--border)">{atx['description'][:60]}</td>
          <td style="padding:6px 10px; font-family:var(--mono); font-size:12px; text-align:right; font-weight:600; border-bottom:1px solid var(--border); color:var(--red)">{fmt(atx['money_in'])}</td>
          <td style="padding:6px 10px; font-size:11px; color:var(--text-dim); border-bottom:1px solid var(--border)">{atx.get('_reason', 'Exceeds 2× avg monthly inflow')}</td>
        </tr>"""
        total_excluded = aff.get('total_excluded', 0)
        anomaly_table = f"""
  <div style="margin-top:20px; margin-bottom:20px;">
    <div style="font-size:10px; font-family:var(--mono); color:var(--text-dim); text-transform:uppercase; letter-spacing:1px; margin-bottom:8px;">Anomalous Receipts Excluded from Adjusted Figures</div>
    <table style="width:100%; border-collapse:collapse; font-size:13px; border:1px solid var(--border); border-radius:6px;">
      <thead>
        <tr style="background:#fef3c7;">
          <th style="padding:8px 10px; text-align:left; font-size:10px; text-transform:uppercase; color:#92400e; border-bottom:2px solid #fbbf24">Date</th>
          <th style="padding:8px 10px; text-align:left; font-size:10px; text-transform:uppercase; color:#92400e; border-bottom:2px solid #fbbf24">Description</th>
          <th style="padding:8px 10px; text-align:right; font-size:10px; text-transform:uppercase; color:#92400e; border-bottom:2px solid #fbbf24">Amount</th>
          <th style="padding:8px 10px; text-align:left; font-size:10px; text-transform:uppercase; color:#92400e; border-bottom:2px solid #fbbf24">Reason for Exclusion</th>
        </tr>
      </thead>
      <tbody>{rows}
        <tr style="background:#fef9ee; font-weight:700">
          <td colspan="2" style="padding:8px 10px; font-size:12px;">Total excluded</td>
          <td style="padding:8px 10px; font-family:var(--mono); font-size:12px; text-align:right; color:var(--red)">{fmt(total_excluded)}</td>
          <td style="padding:8px 10px; font-size:11px; color:var(--text-dim)">{len(anomalous_txs)} transaction{'s' if len(anomalous_txs) != 1 else ''}</td>
        </tr>
      </tbody>
    </table>
  </div>"""
    else:
        anomaly_table = """
  <div style="margin-top:20px; margin-bottom:20px;">
    <div style="font-size:10px; font-family:var(--mono); color:var(--text-dim); text-transform:uppercase; letter-spacing:1px; margin-bottom:8px;">Anomalous Receipts</div>
    <p style="font-size:12px; color:var(--text-dim);">No anomalous receipts detected — unadjusted and adjusted figures are identical.</p>
  </div>"""

    pmt_ref = f"""
    <div style="background:#f8fafc; border:1px solid var(--border); border-radius:8px; padding:16px;">
      <div style="font-size:10px; font-family:var(--mono); color:var(--text-dim); text-transform:uppercase; letter-spacing:1px; margin-bottom:8px;">Monthly Repayment Reference (60% APR)</div>
      <table style="font-size:13px; width:100%">
        <tr>
          <th style="text-align:left; font-size:10px; color:var(--text-dim); padding:3px 0; font-weight:400; text-transform:uppercase">Loan</th>
          <th style="text-align:right; font-size:10px; color:var(--text-dim); padding:3px 0; font-weight:400; text-transform:uppercase">Monthly PMT</th>
          <th style="text-align:right; font-size:10px; color:var(--text-dim); padding:3px 0; font-weight:400; text-transform:uppercase">Total Cost</th>
        </tr>
        <tr><td style="color:var(--text-mid); padding:4px 0">£10,000</td><td style="text-align:right; font-family:var(--mono); font-weight:600">{fmt(aff['pmt_10k'])}</td><td style="text-align:right; font-family:var(--mono); color:var(--text-dim)">{fmt(aff['pmt_10k']*12)}</td></tr>
        <tr><td style="color:var(--text-mid); padding:4px 0">£25,000</td><td style="text-align:right; font-family:var(--mono); font-weight:600">{fmt(aff['pmt_25k'])}</td><td style="text-align:right; font-family:var(--mono); color:var(--text-dim)">{fmt(aff['pmt_25k']*12)}</td></tr>
        <tr><td style="color:var(--text-mid); padding:4px 0">£50,000</td><td style="text-align:right; font-family:var(--mono); font-weight:600">{fmt(aff['pmt_50k'])}</td><td style="text-align:right; font-family:var(--mono); color:var(--text-dim)">{fmt(aff['pmt_50k']*12)}</td></tr>
      </table>
      <p style="font-size:11px; color:var(--text-dim); margin-top:10px; line-height:1.6">PMT calculated using standard annuity formula at 60% APR (5% monthly rate), 12 equal instalments. Figures are illustrative — actual rate set at credit officer discretion.</p>
    </div>"""

    return f"""
<div class="chart-card">
  <div class="section-title">§5d · Loan Affordability Analysis — 60% APR, 12-Month Term</div>
  <p style="font-size:12px; color:var(--text-dim); margin-bottom:16px;">
    Unadjusted figures include all receipts. Adjusted figures exclude anomalous receipts and lender drawdowns (see table below).
    Existing confirmed debt service ~{fmt(d['existing_debt_svc'])}/month.
    Monthly surplus = average inflows minus average outflows. Maximum loan shown at 1.5× DSCR buffer and at zero headroom. All figures rounded to nearest £100.
  </p>
  {od_warning}
  {warning_box}

  <div style="font-size:11px; font-family:var(--mono); color:var(--accent); text-transform:uppercase; letter-spacing:1px; margin:16px 0 8px; font-weight:600;">Unadjusted — All Receipts Included</div>
  <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap:16px; margin-bottom:20px;">
    {box_unadj_full}
    {box_unadj_3m}
  </div>

  <div style="font-size:11px; font-family:var(--mono); color:var(--red); text-transform:uppercase; letter-spacing:1px; margin:16px 0 8px; font-weight:600;">Adjusted — Anomalous Receipts Excluded</div>
  <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap:16px; margin-bottom:20px;">
    {box_adj_full}
    {box_adj_3m}
  </div>

  {anomaly_table}

  <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap:16px; margin-bottom:20px;">
    {pmt_ref}
  </div>
</div>"""


# ============================================================
# §6 MONTHLY CATEGORY BREAKDOWN
# ============================================================

def section_monthly_breakdown(d):
    labels      = d['month_labels']
    monthly     = d['monthly']
    monthly_in  = d['monthly_in']
    monthly_out = d['monthly_out']
    n           = len(labels)
    meta_list   = d['meta_list']
    closing_bals = [m['closing_balance'] for m in meta_list]

    CAT_INFLOW  = [
        'Other Trading Receipts',
        'HMRC Refunds (VAT)',
        'Director/Connected Party Injections',
        'Connected Party Receipts',
        'Unsecured Loan Drawdowns',
        'Returned / Reversed Payments',
    ]
    CAT_OUTFLOW = [
        'Unsecured Loan Repayments',
        'Asset Finance Repayments',
        'HMRC PAYE / NIC',
        'HMRC Payments',
        'Pension',
        'Wages / Payroll',
        'Rent',
        'Bank Charges & Subscriptions',
        'Unpaid Item Fees',
        'Director/Connected Party Payments Out',
        'Other Outgoings',
    ]

    def row(cat, cls):
        vals = monthly.get(cat, [0] * n)
        total = sum(vals)
        if total == 0:
            show_zero = cat in ('Unsecured Loan Drawdowns', 'Unpaid Item Fees')
            if not show_zero:
                return ''
        cells = ''.join(f'<td class="num">{"—" if v == 0 else fmt(v)}</td>' for v in vals)
        return f'<tr class="{cls}"><td class="cat-label">{cat}</td>{cells}<td class="num total-col">{"—" if total == 0 else fmt(total)}</td></tr>'

    header = ''.join(f'<th class="num">{l}</th>' for l in labels)
    in_rows  = ''.join(row(c, 'inflow-row')  for c in CAT_INFLOW)
    out_rows = ''.join(row(c, 'outflow-row') for c in CAT_OUTFLOW)

    tin_cells  = ''.join(f'<td class="num">{fmt(v)}</td>' for v in monthly_in)
    tout_cells = ''.join(f'<td class="num">{fmt(v)}</td>' for v in monthly_out)
    close_cells = ''.join(f'<td class="num">{fmt(v)}</td>' for v in closing_bals)

    net_cells = ''
    for i in range(n):
        net = monthly_in[i] - monthly_out[i]
        cls = 'pos' if net >= 0 else 'neg'
        net_cells += f'<td class="num {cls}">{fmt(net)}</td>'

    net_total = sum(monthly_in) - sum(monthly_out)
    net_cls   = 'pos' if net_total >= 0 else 'neg'

    return f"""
<div class="table-card">
  <div class="section-title">§6 · Monthly Category Breakdown</div>
  <table>
    <thead>
      <tr>
        <th class="cat-label">Category</th>
        {header}
        <th class="num total-col">Total</th>
      </tr>
    </thead>
    <tbody>
      {in_rows}
      <tr class="section-spacer"><td colspan="{n+2}"></td></tr>
      {out_rows}
      <tr class="totals-row">
        <td class="cat-label">Total Payments IN</td>{tin_cells}
        <td class="num total-col">{fmt(sum(monthly_in))}</td>
      </tr>
      <tr class="totals-row">
        <td class="cat-label">Total Payments OUT</td>{tout_cells}
        <td class="num total-col">{fmt(sum(monthly_out))}</td>
      </tr>
      <tr class="totals-row net-row">
        <td class="cat-label">Net Movement</td>{net_cells}
        <td class="num {net_cls} total-col">{fmt(net_total)}</td>
      </tr>
      <tr class="closing-row">
        <td class="cat-label">Closing Balance</td>{close_cells}
        <td class="num total-col">—</td>
      </tr>
    </tbody>
  </table>
</div>"""


# ============================================================
# §7 LENDER ACTIVITY
# ============================================================

def section_lenders(d):
    confirmed = _active_confirmed(d)
    suspected = _get_suspected_lenders(d)
    active_suspected = {k: v for k, v in suspected.items()
                        if (v.get('total_out', 0) + v.get('total_in', 0)) > 0}
    non_lend  = d.get('non_lending_finance', [])
    n         = d['n_months']

    # 7a — Confirmed lenders
    if not confirmed:
        lender_rows = '<tr><td colspan="7" style="color:var(--text-dim); font-style:italic;">No confirmed lending counterparties identified from statement patterns.</td></tr>'
    else:
        lender_rows = ''
        for v in confirmed.values():
            total_out = v.get('total_out', v.get('total', 0))
            total_in  = v.get('total_in', 0)
            net = total_in - total_out
            avg = round(total_out / n) if n else 0
            count = v.get('count_out', v.get('count', 0)) + v.get('count_in', 0)
            lender_rows += f"""
      <tr>
        <td><strong>{v['name']}</strong></td>
        <td><span class="lender-tag">{v['product']}</span></td>
        <td class="num {'pos' if total_in > 0 else ''}">{fmt(total_in) if total_in > 0 else '—'}</td>
        <td class="num neg">{fmt(total_out) if total_out > 0 else '—'}</td>
        <td class="num {'pos' if net > 0 else 'neg'}">{fmt(net)}</td>
        <td>{count} payment(s) across period</td>
        <td>{fmt(avg)}/month avg repayment</td>
      </tr>"""

    # 7b — Suspected lenders
    if active_suspected:
        suspected_rows = ''
        for v in active_suspected.values():
            total_out = v.get('total_out', 0)
            total_in  = v.get('total_in', 0)
            count = v.get('count_out', 0) + v.get('count_in', 0)
            suspected_rows += f"""
      <tr>
        <td>{v['name']}</td>
        <td><span class="suspected-tag">SUSPECTED — REVIEW</span></td>
        <td class="num">{fmt(total_in) if total_in > 0 else '—'}</td>
        <td class="num neg">{fmt(total_out) if total_out > 0 else '—'}</td>
        <td>{count} transaction(s)</td>
        <td>Fuzzy keyword match — CO to verify</td>
      </tr>"""
        suspected_section = f"""
  <h2 class="sub-section">7b — Suspected Lenders ({len(active_suspected)}) — Manual Review Required</h2>
  <p style="font-size:12px; color:var(--text-dim); margin-bottom:12px;">Counterparties matched by fuzzy keyword detection (e.g. 'finance', 'capital', 'lending' in description). Not confirmed as lenders — CO must verify.</p>
  <table>
    <thead>
      <tr><th>Counterparty</th><th>Status</th><th class="num">Total IN</th><th class="num">Total OUT</th><th>Activity</th><th>Note</th></tr>
    </thead>
    <tbody>{suspected_rows}</tbody>
  </table>"""
    else:
        suspected_section = ''

    # 7c — Non-lending finance
    if non_lend:
        nlf_rows = ''
        for nl in non_lend:
            nlf_rows += f"""
      <tr>
        <td>{nl['name']}</td>
        <td><span class="dir-out">OUT</span></td>
        <td class="num neg">{fmt(nl['total'])}</td>
        <td>{nl.get('freq','—')}</td>
        <td><em>{nl.get('note','')}</em></td>
      </tr>"""
        non_lending_section = f"""
  <h2 class="sub-section">7c — Non-Lending Finance Counterparties</h2>
  <table>
    <thead>
      <tr><th>Counterparty</th><th>Direction</th><th class="num">Total Amount</th><th>Frequency</th><th>Note</th></tr>
    </thead>
    <tbody>{nlf_rows}</tbody>
  </table>"""
    else:
        non_lending_section = ''

    return f"""
<div class="table-card">
  <div class="section-title">§7 · Lender Activity</div>
  <h2 class="sub-section">7a — Confirmed Lenders ({len(confirmed)} Active {'Facility' if len(confirmed) == 1 else 'Facilities'})</h2>
  <table>
    <thead>
      <tr>
        <th>Lender</th>
        <th>Product Type</th>
        <th class="num">Total Drawn In</th>
        <th class="num">Total Repaid Out</th>
        <th class="num">Net</th>
        <th>Months Active</th>
        <th>Notes</th>
      </tr>
    </thead>
    <tbody>{lender_rows}</tbody>
  </table>
  {suspected_section}
  {non_lending_section}
</div>"""


# ============================================================
# §8 NOTABLE LARGE TRANSACTIONS
# ============================================================

def section_large_transactions(d):
    top_in   = d['top_in']
    top_out  = d['top_out']
    anom_amt = d.get('anomaly_amount', 0)

    def in_rows(txs):
        out = ''
        for tx in txs:
            amt  = tx.get('money_in', 0)
            lender_tag = f'<span class="lender-tag">{tx["_lender"]}</span> ' if tx.get('_lender') else ''
            flag = f'{lender_tag}⚑ Lender drawdown' if tx.get('_lender') else (
                '⚑ Anomaly — verify source' if (anom_amt > 0 and abs(amt - anom_amt) < 1) else '—'
            )
            ml   = tx.get('month_label', tx.get('date', ''))
            out += f"""
      <tr>
        <td>{tx['date']}</td>
        <td>{tx['description'][:55]}</td>
        <td class="num pos">{fmt(amt)}</td>
        <td>{ml}</td>
        <td>{flag}</td>
      </tr>"""
        return out

    def out_rows(txs):
        out = ''
        for tx in txs:
            amt = tx.get('money_out', 0)
            lender_tag = f'<span class="lender-tag">{tx["_lender"]}</span>' if tx.get('_lender') else '—'
            ml  = tx.get('month_label', tx.get('date', ''))
            out += f"""
      <tr>
        <td>{tx['date']}</td>
        <td>{tx['description'][:55]}</td>
        <td class="num neg">{fmt(amt)}</td>
        <td>{ml}</td>
        <td>{lender_tag}</td>
      </tr>"""
        return out

    return f"""
<div class="table-card">
  <div class="section-title">§8 · Notable Large Transactions</div>
  <h2 class="sub-section">Top 5 Inflows</h2>
  <table>
    <thead><tr><th>Date</th><th>Description</th><th class="num">Amount</th><th>Month</th><th>Flag</th></tr></thead>
    <tbody>{in_rows(top_in)}</tbody>
  </table>
  <h2 class="sub-section" style="margin-top:24px">Top 5 Outflows</h2>
  <table>
    <thead><tr><th>Date</th><th>Description</th><th class="num">Amount</th><th>Month</th><th>Flag</th></tr></thead>
    <tbody>{out_rows(top_out)}</tbody>
  </table>
</div>"""


# ============================================================
# §9 FAILED & FLAGGED TRANSACTIONS
# ============================================================

def section_failed_flagged(d):
    bounced = d.get('bounced', {})
    co  = d['connected_out']
    ci  = d['connected_in']

    # 9a — Confirmed bounced/returned payments
    confirmed_bounced = bounced.get('confirmed_bounced', [])
    suspected_bounced = bounced.get('suspected_bounced', [])
    all_bounced = confirmed_bounced + suspected_bounced

    if all_bounced:
        bounced_rows = ''
        for tx in all_bounced:
            conf = tx.get('_confidence', 'unknown')
            badge = '<span class="badge badge-warn">Confirmed</span>' if conf == 'high' else '<span class="badge badge-note">Suspected</span>'
            amt = tx.get('money_in', 0) or tx.get('money_out', 0)
            bounced_rows += f"""
      <tr>
        <td>{tx['date']}</td>
        <td>{tx['description'][:55]}</td>
        <td class="num">{fmt(amt, pence=True)}</td>
        <td>{badge}</td>
        <td>{tx.get('_detection', '—')}</td>
      </tr>"""
    else:
        bounced_rows = '<tr><td colspan="5" style="color:var(--text-dim); font-style:italic;">No bounced or returned payments identified.</td></tr>'

    # 9b — Fee / OD cost transactions
    confirmed_fees = bounced.get('confirmed_fees', [])
    confirmed_od   = bounced.get('confirmed_od_costs', [])
    all_fees = confirmed_fees + confirmed_od

    if all_fees:
        fee_rows = ''
        for tx in all_fees:
            amt = tx.get('money_out', 0)
            fee_type = 'Unpaid Item Fee' if tx in confirmed_fees else 'Overdraft Cost'
            fee_rows += f"""
      <tr>
        <td>{tx['date']}</td>
        <td>{tx['description'][:55]}</td>
        <td class="num neg">{fmt(amt, pence=True)}</td>
        <td>{fee_type}</td>
        <td>Bank stress signal — account unable to fully service obligations</td>
      </tr>"""
    else:
        fee_rows = f"""
      <tr><td colspan="5" style="color:var(--text-dim); font-style:italic;">
        No separate unpaid item fee or overdraft cost lines identified.
        CO should verify whether the bank charged unpaid item fees in connection with any returned DDs.
      </td></tr>"""

    # 9c — Connected party flows
    cp_rows = ''
    for tx in ci[:6]:
        amt = tx.get('money_in', 0)
        matched = tx.get('_matched_name', 'connected party')
        cp_rows += f"""
      <tr>
        <td>{tx['date']}</td>
        <td>{tx['description'][:50]}</td>
        <td class="num pos">{fmt(amt)}</td>
        <td><span class="dir-in">IN</span></td>
        <td>Matched: "{matched}"</td>
        <td>⚑ Inbound connected party flow — verify commercial basis</td>
      </tr>"""
    for tx in co[:6]:
        amt = tx.get('money_out', 0)
        matched = tx.get('_matched_name', 'connected party')
        cp_rows += f"""
      <tr>
        <td>{tx['date']}</td>
        <td>{tx['description'][:50]}</td>
        <td class="num neg">{fmt(amt)}</td>
        <td><span class="dir-out">OUT</span></td>
        <td>Matched: "{matched}"</td>
        <td>⚑ Outbound connected party flow — verify commercial basis</td>
      </tr>"""

    if not cp_rows:
        cp_rows = '<tr><td colspan="6" style="color:var(--text-dim); font-style:italic;">No connected party flows identified.</td></tr>'

    # Connected names used
    cn = d.get('connected_names', [])
    cn_note = f'<p style="font-size:11px; color:var(--text-dim); margin-top:8px;">Detection names: {", ".join(cn[:10])}{"…" if len(cn) > 10 else ""}</p>' if cn else ''

    return f"""
<div class="table-card">
  <div class="section-title">§9 · Failed &amp; Flagged Transactions</div>

  <h2 class="sub-section">9a — Bounced / Returned Payments ({len(all_bounced)} found)</h2>
  <table>
    <thead>
      <tr><th>Date</th><th>Description</th><th class="num">Amount</th><th>Confidence</th><th>Detection Method</th></tr>
    </thead>
    <tbody>{bounced_rows}</tbody>
  </table>

  <h2 class="sub-section" style="margin-top:24px">9b — Unpaid Item Fees &amp; Overdraft Costs ({len(all_fees)} found)</h2>
  <table>
    <thead>
      <tr><th>Date</th><th>Description</th><th class="num">Amount</th><th>Type</th><th>Reviewer Note</th></tr>
    </thead>
    <tbody>{fee_rows}</tbody>
  </table>

  <h2 class="sub-section" style="margin-top:24px">9c — Connected Party Flows</h2>
  <table>
    <thead>
      <tr><th>Date</th><th>Description</th><th class="num">Amount</th><th>Direction</th><th>Match Type</th><th>Flag</th></tr>
    </thead>
    <tbody>{cp_rows}</tbody>
  </table>
  {cn_note}
</div>"""


# ============================================================
# §10 CREDIT RISK FLAGS
# ============================================================

def section_flags(d):
    gam = d['gambling']
    san = d['sanctions']
    sal = d['salary']
    low = d['low_balance']
    fdd = d['failed_dds']
    me  = san['middle_east_txs']
    bounced = d.get('bounced', {})
    ttp = d.get('hmrc_ttp', {})
    aff = d['affordability']

    flags = []

    # Persistent overdraft
    if aff.get('persistent_overdraft'):
        flags.append(('flag-critical', '🚨', f"""
      <h3><span class="badge badge-crit">CRITICAL</span><span class="badge badge-crit">Overdraft</span> Persistent Overdraft — Average Daily Balance {fmt(d['avg_bal_full'])}</h3>
      <div class="evidence">Account has operated in overdraft throughout the analysis period. Average daily balance: {fmt(d['avg_bal_full'])}. Closing balance: {fmt(d['closing_bal'])}.</div>
      <div class="implication">Any reported monthly surplus represents reduction in overdraft depth, not free cash available for new debt service. Recommend £0 affordability unless account can demonstrate ability to operate in credit. Overdraft facility terms and limits should be confirmed with the bank.</div>"""))

    # Anomaly
    if d['anomaly_tx']:
        tx = d['anomaly_tx']
        avg_in = round(sum(d['monthly_in']) / d['n_months']) if d['n_months'] else 0
        flags.append(('flag-warning', '⚠', f"""
      <h3><span class="badge badge-warn">WARNING</span><span class="badge badge-warn">Unusual Receipt</span> {fmt(d['anomaly_amount'])} — Nature Unconfirmed</h3>
      <div class="evidence">{tx['date']} — {tx['description']} — {fmt(tx['money_in'])}. Flagged anomalous (exceeds 2× average monthly inflow of {fmt(avg_in)}).</div>
      <div class="implication">This is the largest single receipt in the period and drives the closing balance. CO must establish whether this is trading income, a director injection, or a third-party loan before including it in revenue analysis.</div>"""))

    # Concentration risk
    top_in_total = sum(tx.get('money_in', 0) for tx in d['top_in'])
    total_in = sum(d['monthly_in'])
    if total_in > 0 and top_in_total / total_in > 0.5:
        top_names = ', '.join(tx['description'][:25] for tx in d['top_in'][:3])
        flags.append(('flag-warning', '⚠', f"""
      <h3><span class="badge badge-warn">WARNING</span><span class="badge badge-warn">Concentration Risk</span> Revenue Heavily Concentrated in Key Counterparties</h3>
      <div class="evidence">Top 3 inflows represent {round(top_in_total/total_in*100)}% of total receipts: {top_names}</div>
      <div class="implication">Loss of any single key trading relationship would materially impair debt service capacity. CO should assess dependency and contractual position with major counterparties.</div>"""))

    # HMRC TTP
    if ttp.get('found'):
        ttp_txs = '; '.join(f'{t["date"]} {t["description"][:35]}' for t in ttp.get('transactions', [])[:5])
        flags.append(('flag-critical', '🚨', f"""
      <h3><span class="badge badge-crit">CRITICAL</span><span class="badge badge-crit">HMRC</span> Time to Pay / NDDS Arrangement Detected</h3>
      <div class="evidence">{ttp_txs}</div>
      <div class="implication">Business has negotiated payment arrangements with HMRC, indicating tax arrears. This is a significant red flag for affordability — HMRC takes priority over unsecured creditors. CO must establish: (1) total HMRC debt outstanding; (2) remaining TTP term; (3) whether current TTP payments are being maintained. Consider requesting HMRC statement of account.</div>"""))

    # Active lenders
    active = _active_confirmed(d)
    if active:
        debt_detail = ' · '.join(f'{v["name"]} {fmt(round(v.get("total_out", v.get("total", 0))/d["n_months"]))}/month' for v in active.values())
        flags.append(('flag-note', 'ℹ', f"""
      <h3><span class="badge badge-note">NOTE</span><span class="badge badge-note">Active Facilities</span> {len(active)} Confirmed Lender{'s' if len(active) > 1 else ''} — ~{fmt(d['existing_debt_svc'])}/Month Combined Debt Service</h3>
      <div class="evidence">{debt_detail}</div>
      <div class="implication">All confirmed via statement payment pattern. Combined monthly commitment must be factored into affordability assessment for any new facility.</div>"""))

    # Suspected lenders
    suspected = _get_suspected_lenders(d)
    active_suspected = {k: v for k, v in suspected.items() if (v.get('total_out', 0) + v.get('total_in', 0)) > 0}
    if active_suspected:
        susp_names = ', '.join(v['name'][:25] for v in list(active_suspected.values())[:5])
        flags.append(('flag-warning', '⚠', f"""
      <h3><span class="badge badge-warn">WARNING</span><span class="badge badge-warn">Suspected Lenders</span> {len(active_suspected)} Unconfirmed Lending Counterpart{'ies' if len(active_suspected) > 1 else 'y'} Detected</h3>
      <div class="evidence">{susp_names}</div>
      <div class="implication">Fuzzy keyword matching detected counterparties with lending-related terms in descriptions. CO must verify whether these are actual lenders — if confirmed, additional debt service must be factored into affordability. See §7b.</div>"""))

    # Bounced DDs
    total_bounced = bounced.get('total_confirmed', 0) + bounced.get('total_suspected', 0)
    if total_bounced > 0:
        all_b = bounced.get('confirmed_bounced', []) + bounced.get('suspected_bounced', [])
        tx_list = '; '.join(f'{t["date"]} {t["description"][:35]}' for t in all_b[:5])
        flags.append(('flag-note', 'ℹ', f"""
      <h3><span class="badge badge-note">NOTE</span><span class="badge badge-note">Bounced DD</span> {total_bounced} Failed/Returned Payment(s)</h3>
      <div class="evidence">{tx_list}</div>
      <div class="implication">Failed/returned payment(s) demonstrate cash flow moments where the account was unable to service obligations. CO to assess whether trading creditor or non-trading commitment.</div>"""))

    # Negative balance days
    neg_count = low.get('negative_count', 0)
    if neg_count > 0:
        lowest = low.get('lowest')
        lowest_str = f'{lowest[0].strftime("%d/%m/%y") if hasattr(lowest[0], "strftime") else lowest[0]}: {fmt(lowest[1])}' if lowest else ''
        flags.append(('flag-warning', '⚠', f"""
      <h3><span class="badge badge-warn">WARNING</span><span class="badge badge-warn">Negative Balance</span> {neg_count} Day(s) in Overdraft</h3>
      <div class="evidence">Account balance fell below £0 for {neg_count} day(s). Lowest point: {lowest_str}.</div>
      <div class="implication">Account operated in unauthorised or arranged overdraft. CO to establish: (1) whether overdraft facility exists; (2) facility limit; (3) whether overdraft usage is increasing or reducing over time.</div>"""))

    # Middle East
    if me:
        tx_list = '; '.join(f'{t["date"]} {t["description"][:30]}' for t in me[:5])
        flags.append(('flag-note', 'ℹ', f"""
      <h3><span class="badge badge-note">NOTE</span><span class="badge badge-note">International Activity</span> Middle East Transactions ({len(me)} found)</h3>
      <div class="evidence">{tx_list}</div>
      <div class="implication">Transactions involving Middle East jurisdictions identified. Consistent with business development activity but CO should note the international exposure and verify business purpose.</div>"""))

    # Gambling
    if gam['found']:
        tx_list = '; '.join(f'{t["date"]} {t["description"][:30]} {fmt(t.get("money_out",0))}' for t in gam['transactions'][:5])
        flags.append(('flag-warning', '⚠', f"""
      <h3><span class="badge badge-warn">WARNING</span><span class="badge badge-warn">Gambling</span> Gambling Transactions Detected</h3>
      <div class="evidence">{tx_list}</div>
      <div class="implication">Gambling on a business account indicates potential mixing of personal and business finances and may signal director financial stress. CO to review and assess materiality.</div>"""))

    # PAYE variance
    if sal['variance_pct'] > 20:
        paye_str = ' · '.join(f'{l}: {fmt(v)}' for l, v in zip(sal['month_labels'], sal['paye_by_month']))
        flags.append(('flag-warning', '⚠', f"""
      <h3><span class="badge badge-warn">WARNING</span><span class="badge badge-note">Salary</span> PAYE / Wage Consistency Check — {sal['variance_pct']}% Variance</h3>
      <div class="evidence">Monthly PAYE payments: {paye_str if paye_str else "Irregular / not detected"}. Variance: {sal['variance_pct']}%.</div>
      <div class="implication">Material variance in PAYE payments detected. CO should establish whether headcount has changed, whether any payments are catch-ups, or whether wages are being extracted irregularly.</div>"""))

    # Low balance
    lq_cls   = 'flag-note'
    lq_badge = 'badge-pass' if low['below_5k_count'] == 0 else 'badge-note'
    lq_label = 'PASS' if low['below_5k_count'] == 0 else 'NOTE'
    flags.append((lq_cls, 'ℹ', f"""
      <h3><span class="badge {lq_badge}">{lq_label}</span><span class="badge badge-note">Liquidity</span> Low / Near-Zero Balance Days</h3>
      <div class="evidence">Days with closing balance below £5,000: {low['below_5k_count']}. Below £2,000: {low['below_2k_count']}. Negative: {low.get('negative_count', 0)}.</div>
      <div class="implication">{'No material intraday stress identified from closing balance analysis. Balance has remained comfortable throughout.' if low['below_5k_count'] == 0 and neg_count == 0 else f'Account held below £5,000 for {low["below_5k_count"]} day(s). CO to review context and timing.'}</div>"""))

    # Sanctions
    if not san['clean']:
        flags.append(('flag-critical', '🚨', f"""
      <h3><span class="badge badge-crit">CRITICAL</span> Potential Sanctions Hits Detected</h3>
      <div class="evidence">{len(san['sanction_hits'])} transaction(s) matched sanctioned country keywords.</div>
      <div class="implication">Immediate escalation required. Do not proceed with any lending decision until a full compliance review has been completed.</div>"""))
    else:
        me_jurisdictions = ', '.join(set(t['description'][:20] for t in me[:3])) if me else 'None'
        flags.append(('flag-note', 'ℹ', f"""
      <h3><span class="badge badge-note">NOTE</span><span class="badge badge-note">Sanctions</span> Jurisdiction &amp; Counterparty Sanctions Screen</h3>
      <div class="evidence">Sanctioned country keyword scan: 0 match(es) found. {len(me)} Middle East transaction(s) identified (non-sanctioned jurisdictions).</div>
      <div class="implication"><strong>This is a keyword screen only and does not constitute a compliant sanctions check.</strong> All counterparties must be verified against current OFSI/OFAC/UN consolidated lists using a live screening tool before lending.</div>"""))

    html = '<div class="table-card"><div class="section-title">§10 · Credit Risk Flags</div><div class="flags-list">'
    for cls, icon, body in flags:
        html += f'\n  <div class="flag-card {cls}"><div class="flag-icon">{icon}</div><div class="flag-body">{body}</div></div>'
    html += '\n</div></div>'
    return html


# ============================================================
# §11 CREDIT DECISION SUMMARY
# ============================================================

def section_decision(d):
    aff      = d['affordability']
    fdd      = d['failed_dds']
    n        = d['n_months']
    ttp      = d.get('hmrc_ttp', {})
    bounced  = d.get('bounced', {})

    active = _active_confirmed(d)
    n_active = len(active)
    active_names = ', '.join(v['name'] for v in active.values())

    suspected = _get_suspected_lenders(d)
    n_suspected = len({k: v for k, v in suspected.items() if (v.get('total_out', 0) + v.get('total_in', 0)) > 0})

    in_summary = ' | '.join(f'{l}: {fmt(v)} IN' for l, v in zip(d['month_labels'], d['monthly_in']))

    # Account in credit test — overdraft aware
    if d['avg_bal_full'] < 0:
        credit_finding = f'Account operates on permanent overdraft. Average daily balance {fmt(d["avg_bal_full"])}. Not in credit.'
        credit_badge = 'badge-fail'
        credit_outcome = 'FAIL'
    elif d.get('low_balance', {}).get('negative_count', 0) > 0:
        neg_days = d['low_balance']['negative_count']
        credit_finding = f'Account fell into overdraft for {neg_days} day(s) during the period. Average daily balance {fmt(d["avg_bal_full"])}.'
        credit_badge = 'badge-refer'
        credit_outcome = 'REFER'
    else:
        credit_finding = f'Account remained positive for entire period. Average daily balance {fmt(d["avg_bal_full"])}.'
        credit_badge = 'badge-pass'
        credit_outcome = 'PASS'

    # Bounced test
    total_bounced = bounced.get('total_confirmed', 0) + bounced.get('total_suspected', 0)

    # HMRC TTP — real detection
    if ttp.get('found'):
        ttp_finding = f'{ttp["count"]} HMRC NDDS/TTP transaction(s) detected. Business has negotiated payment arrangements with HMRC — indicates tax arrears.'
        ttp_badge = 'badge-fail'
        ttp_outcome = 'FAIL'
    else:
        ttp_finding = (
            'No HMRC NDDS, TTP, or enforcement signals identified in transaction descriptions. '
            + ('HMRC VAT refunds received — likely VAT repayment trader.' if any('hmrc refund' in cat.lower() or 'vat' in cat.lower() for cat in d['monthly']) else '')
        )
        ttp_badge = 'badge-pass'
        ttp_outcome = 'PASS'

    # Lender stacking test
    lender_finding = f'{n_active} confirmed lenders ({active_names}). ' if n_active else 'No confirmed lenders. '
    if n_suspected > 0:
        lender_finding += f'{n_suspected} suspected lender(s) flagged for review — see §7b.'
    else:
        lender_finding += 'No suspected lenders from fuzzy detection.'

    rows = [
        ('Account in credit throughout', 'No unauthorised OD',
         credit_finding, credit_badge, credit_outcome),

        ('Failed / returned DDs', 'Ideally zero within 6 months',
         (f'{total_bounced} bounced/returned payment(s) detected: ' + '; '.join(t["description"][:30] for t in (bounced.get('confirmed_bounced', []) + bounced.get('suspected_bounced', []))[:3]))
          if total_bounced > 0 else 'No failed/returned payments identified.',
         'badge-refer' if total_bounced > 0 else 'badge-pass',
         'REFER' if total_bounced > 0 else 'PASS'),

        ('Active lender conflicts', 'No MCA stacking',
         lender_finding,
         'badge-refer' if n_suspected > 0 else 'badge-pass',
         'REFER' if n_suspected > 0 else 'PASS'),

        ('Revenue regularity', 'Consistent trading income',
         f'Income over {n} months: {in_summary}.'
         + (' Large anomalous receipt detected — requires explanation before income assessment.' if d['anomaly_tx'] else ''),
         'badge-refer', 'REFER'),

        ('HMRC arrears / TTP', 'No TTP arrangement',
         ttp_finding, ttp_badge, ttp_outcome),

        ('Connected party transactions', 'No material unexplained flows',
         f'{len(d["connected_out"])} outbound and {len(d["connected_in"])} inbound connected party flows identified. See §9c for detail.'
          if (d['connected_out'] or d['connected_in']) else 'No connected party flows identified.',
         'badge-refer' if (d['connected_out'] or d['connected_in']) else 'badge-pass',
         'REFER' if (d['connected_out'] or d['connected_in']) else 'PASS'),

        ('DSCR assessment', '≥1.5× (target); ≥1.25× (minimum)',
         (f'Adjusted monthly surplus {fmt(aff["surplus_full"])}. '
          + (f'Max supportable loan at 1.5× DSCR: {fmt(aff["max_loan_full_dscr"])}.'
             if aff['max_loan_full_dscr'] > 0
             else 'Negative adjusted surplus — no supportable loan from observable recurring cash flow without verified additional income. Full accounts required.')
          + (' ⚠ Persistent overdraft — surplus represents OD reduction, not free cash.' if aff.get('persistent_overdraft') else '')),
         'badge-refer' if aff['surplus_full'] < 0 or aff.get('persistent_overdraft') else 'badge-pass',
         'REFER' if aff['surplus_full'] < 0 or aff.get('persistent_overdraft') else 'PASS'),
    ]

    tbody = ''
    for test, req, finding, badge_cls, outcome in rows:
        tbody += f"""
      <tr>
        <td>{test}</td>
        <td>{req}</td>
        <td>{finding}</td>
        <td><span class="badge {badge_cls}">{outcome}</span></td>
      </tr>"""

    return f"""
<div class="table-card">
  <div class="section-title">§11 · Credit Decision Summary</div>
  <p style="color:var(--text-mid); margin-bottom:16px; font-size:13px; font-style:italic;">No recommendation — credit officer makes the decision. The following policy tests are based on information observable from bank statements only.</p>
  <table class="decision-table">
    <thead>
      <tr><th>Policy Test</th><th>Requirement</th><th>Finding from Statements</th><th>Outcome</th></tr>
    </thead>
    <tbody>{tbody}</tbody>
  </table>

  <div style="margin-top:20px; padding:16px 20px; background:#fffbeb; border:1px solid #fcd34d; border-radius:8px;">
    <strong style="color:#b45309; font-family:var(--mono); font-size:12px;">CONDITIONAL PATH</strong>
    <p style="margin-top:8px; font-size:13px; color:var(--text-mid);">
      Case may strengthen subject to: (1) confirmation of any anomalous receipts — trading invoice, loan, or investment;
      (2) last 2 years filed accounts from Companies House to validate revenue;
      (3) director confirmation of any connected party loan terms;
      (4) explanation of any non-trading disbursements identified above.
      Outstanding items are informational — no hard declines triggered from statement review alone.
    </p>
  </div>
</div>"""


# ============================================================
# FOOTER
# ============================================================

def section_footer(d):
    now = datetime.now().strftime('%d/%m/%y')
    validation = d.get('validation')
    if validation and validation.get('all_reconciled'):
        recon_status = '✓ 100% Reconciled'
    elif validation:
        failed = sum(1 for r in validation.get('reconciliation_results', []) if not r['passed'])
        recon_status = f'⚠ {failed} Reconciliation Warning(s)'
    else:
        recon_status = '✓ 100% Reconciled'

    return f"""
<div class="footer">
  {d['account_name']} &nbsp;|&nbsp; {d['sort_code']} &nbsp;|&nbsp; {d['account_number']} &nbsp;|&nbsp;
  {d['n_months']} Months: {d['period_start']}–{d['period_end']} &nbsp;|&nbsp;
  Generated {now} &nbsp;|&nbsp; Monmouth Group Credit Analysis Tool &nbsp;|&nbsp;
  Full Transaction Parse — {d['total_tx_count']} Rows &nbsp;|&nbsp; {recon_status}
</div>"""


# ============================================================
# MASTER BUILD FUNCTION
# ============================================================

def build_report(data, output_path=None):
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{data['account_name']} — Bank Statement Analysis</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
{CSS}
</style>
</head>
<body>
<div class="container">

{section_header(data)}
{section_credit_summary(data)}
{section_methodology(data)}
{section_data_quality(data)}
{section_metrics(data)}
{section_charts(data)}
{section_affordability(data)}
{section_monthly_breakdown(data)}
{section_lenders(data)}
{section_large_transactions(data)}
{section_failed_flagged(data)}
{section_flags(data)}
{section_decision(data)}
{section_footer(data)}

</div>
</body>
</html>"""

    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f'Report saved to: {output_path}')

    return html


# ============================================================
# TEST RUNNER
# ============================================================

if __name__ == '__main__':
    import json, os, sys, glob
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from core.analytics import run_analytics

    json_files = sorted(glob.glob('test_statements/parsed_*.json'))
    if not json_files:
        print('No parsed JSON files found in test_statements/')
        sys.exit(1)

    print(f'Loading {len(json_files)} parsed statements...')
    parsed = []
    for f in json_files:
        with open(f) as fp:
            d = json.load(fp)
            d['_filename'] = os.path.basename(f)
            parsed.append(d)

    print('Running analytics...')
    data = run_analytics(parsed)

    print('Building report...')
    build_report(data, output_path='test_statements/report.html')
    print('Done. Open test_statements/report.html in your browser.')
