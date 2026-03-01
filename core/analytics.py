import json
import os
from datetime import datetime, timedelta
from collections import defaultdict

# ============================================================
# CONFIGURATION
# ============================================================

ANNUAL_RATE    = 0.60
MONTHLY_RATE   = ANNUAL_RATE / 12   # 0.05
N_MONTHS       = 12
MIN_LOAN       = 10_000
MAX_LOAN       = 50_000
DSCR_BUFFER    = 1.5

GAMBLING_KEYWORDS = [
    'bet365', 'betfair', 'paddy power', 'william hill', 'ladbrokes',
    'coral', 'sky bet', 'betway', 'unibet', '888sport', 'betfred',
    'tombola', 'lottoland', 'camelot', 'national lottery', 'casino',
    'jackpot', 'poker stars', 'bingo', 'grosvenor', 'betvictor'
]

SANCTIONED_COUNTRIES = [
    'russia', 'iran', 'north korea', 'dprk', 'myanmar', 'belarus',
    'syria', 'venezuela', 'cuba', 'sudan', 'eritrea', 'somalia',
    'liberia', 'zimbabwe'
]

MIDDLE_EAST_KEYWORDS = [
    'saudi', 'jeddah', 'riyadh', 'bahrain', 'ziina', 'visitsvisa',
    'dubai', 'abu dhabi', 'uae', 'qatar', 'kuwait', 'oman'
]

# ============================================================
# CATEGORISATION ENGINE
# ============================================================

def categorise(description, money_out, money_in):
    d = description.lower()
    if money_in > 0:
        if 'hmrc' in d and ('vat' in d or 'repay' in d):
            return 'HMRC Refunds (VAT)'
        if any(x in d for x in ['yara', 'axworx', 'swea']):
            return 'Other Trading Receipts'
        if any(x in d for x in ['joene', 'metal monkeys']):
            return 'Connected Party Receipts'
        if 'antrum' in d:
            return 'Director/Connected Party Injections'
        if 'unpaid direct debit' in d or 'unpaid dd' in d:
            return 'Other Trading Receipts'
        return 'Other Trading Receipts'
    if 'iwoca' in d:
        return 'Unsecured Loan Repayments'
    if 'armada' in d or 'premium credit' in d or 'stellantis' in d or 'sme finance' in d:
        return 'Asset Finance Repayments'
    if 'hmrc cumbernauld' in d or ('hmrc' in d and 'pj' in d):
        return 'HMRC PAYE / NIC'
    if 'nest' in d or ('7im' in d and 'sipp' in d):
        return 'Pension'
    if any(x in d for x in ['willow barn', 'south monmouth', 'monmouthshire coun']):
        return 'Rent'
    if any(x in d for x in ['fiona reece', 'daniel spokes']) and any(w in d for w in ['wage', 'paye', 'salary']):
        return 'Wages / Payroll'
    if 'fiona reece' in d:
        return 'Wages / Payroll'
    if any(x in d for x in ['antrum', 'daniel spokes', 'pershing', 'keith nair']):
        return 'Director/Connected Party Payments Out'
    if 'unpaid direct debit' in d or 'unpaid dd' in d:
        return 'Unpaid Item Fees'
    if any(x in d for x in ['xero', '123 telecom', 'l&g insurance', 'gocardless', 'zoom']):
        return 'Bank Charges & Subscriptions'
    return 'Other Outgoings'

CAT_INFLOW = [
    'Other Trading Receipts',
    'HMRC Refunds (VAT)',
    'Director/Connected Party Injections',
    'Connected Party Receipts',
]
CAT_OUTFLOW = [
    'Unsecured Loan Repayments',
    'Asset Finance Repayments',
    'HMRC PAYE / NIC',
    'Pension',
    'Wages / Payroll',
    'Rent',
    'Bank Charges & Subscriptions',
    'Unpaid Item Fees',
    'Director/Connected Party Payments Out',
    'Other Outgoings',
]

# ============================================================
# MERGE & PREPARE TRANSACTIONS
# ============================================================

def merge_statements(parsed_statements):
    seen = set()
    all_txs = []
    for stmt in parsed_statements:
        for tx in stmt.get('transactions', []):
            key = (tx['date'], tx['description'], tx['money_out'], tx['money_in'])
            if key not in seen:
                seen.add(key)
                tx['category'] = categorise(tx['description'], tx['money_out'], tx['money_in'])
                all_txs.append(tx)
    def parse_date(d):
        for fmt in ('%d/%m/%y', '%d/%m/%Y'):
            try:
                return datetime.strptime(d, fmt)
            except ValueError:
                continue
        return datetime.min
    all_txs.sort(key=lambda x: parse_date(x['date']))
    return all_txs


def get_statement_metadata(parsed_statements):
    meta_list = []
    for stmt in parsed_statements:
        m = stmt.get('metadata', {})
        start_str = m.get('statement_start', '')
        end_str   = m.get('statement_end', '')
        for fmt in ('%d/%m/%y', '%d/%m/%Y'):
            try:
                start = datetime.strptime(start_str, fmt)
                end   = datetime.strptime(end_str, fmt)
                meta_list.append({
                    'account_name':    m.get('account_name', ''),
                    'account_number':  m.get('account_number', ''),
                    'sort_code':       m.get('sort_code', ''),
                    'start':           start,
                    'end':             end,
                    'opening_balance': m.get('opening_balance', 0),
                    'closing_balance': m.get('closing_balance', 0),
                    'filename':        stmt.get('_filename', ''),
                })
                break
            except ValueError:
                continue
    meta_list.sort(key=lambda x: x['start'])
    return meta_list


# ============================================================
# MONTHLY BUCKETING
# ============================================================

def assign_month_index(date_str, period_start, n_months):
    for fmt in ('%d/%m/%y', '%d/%m/%Y'):
        try:
            d = datetime.strptime(date_str, fmt)
            months_diff = (d.year - period_start.year) * 12 + (d.month - period_start.month)
            if 0 <= months_diff < n_months:
                return months_diff
            return max(0, min(months_diff, n_months - 1))
        except ValueError:
            continue
    return 0


def build_monthly_buckets(transactions, period_start, n_months):
    monthly = {cat: [0.0] * n_months for cat in CAT_INFLOW + CAT_OUTFLOW}
    monthly_in  = [0.0] * n_months
    monthly_out = [0.0] * n_months
    for tx in transactions:
        idx = assign_month_index(tx['date'], period_start, n_months)
        cat = tx.get('category', 'Other Outgoings')
        if tx['money_in'] > 0:
            if cat in monthly:
                monthly[cat][idx] += tx['money_in']
            monthly_in[idx] += tx['money_in']
        if tx['money_out'] > 0:
            if cat in monthly:
                monthly[cat][idx] += tx['money_out']
            monthly_out[idx] += tx['money_out']
    return monthly, monthly_in, monthly_out


# ============================================================
# DAILY BALANCE SERIES
# ============================================================

def build_daily_series(transactions, opening_balance, period_start, period_end):
    date_bal = {}
    for tx in transactions:
        for fmt in ('%d/%m/%y', '%d/%m/%Y'):
            try:
                d = datetime.strptime(tx['date'], fmt)
                if tx['balance'] > 0:
                    date_bal[d] = tx['balance']
                break
            except ValueError:
                continue
    daily = []
    current = opening_balance
    d = period_start
    while d <= period_end:
        if d in date_bal:
            current = date_bal[d]
        daily.append((d, current))
        d += timedelta(days=1)
    return daily


# ============================================================
# INTRA-MONTH PROFILE
# ============================================================

def build_intramonth_profile(daily_series, meta_list):
    def week_bucket(day):
        if day <= 7:  return 0
        if day <= 14: return 1
        if day <= 21: return 2
        return 3
    daily_map = {d: b for d, b in daily_series}
    intramonth = []
    for meta in meta_list:
        buckets = [[], [], [], []]
        d = meta['start']
        while d <= meta['end']:
            bal = daily_map.get(d)
            if bal is not None:
                buckets[week_bucket(d.day)].append(bal)
            d += timedelta(days=1)
        avg_buckets = [round(sum(b) / len(b)) if b else None for b in buckets]
        intramonth.append(avg_buckets)
    avg_overall = []
    for wk in range(4):
        vals = [intramonth[m][wk] for m in range(len(intramonth)) if intramonth[m][wk] is not None]
        avg_overall.append(round(sum(vals) / len(vals)) if vals else 0)
    return intramonth, avg_overall


# ============================================================
# LOAN AFFORDABILITY
# ============================================================

def pmt_to_principal(monthly_payment, r=MONTHLY_RATE, n=N_MONTHS):
    if monthly_payment <= 0:
        return 0
    pv_factor = (1 - (1 + r) ** (-n)) / r
    return monthly_payment * pv_factor


def principal_to_pmt(principal, r=MONTHLY_RATE, n=N_MONTHS):
    return principal * r / (1 - (1 + r) ** (-n))


def calc_affordability(monthly_in, monthly_out, anomaly_amount=0, anomaly_month_idx=None):
    n = len(monthly_in)
    adj_in = list(monthly_in)
    if anomaly_amount > 0 and anomaly_month_idx is not None:
        adj_in[anomaly_month_idx] = max(0, adj_in[anomaly_month_idx] - anomaly_amount)
    avg_in_full  = sum(adj_in) / n
    avg_out_full = sum(monthly_out) / n
    surplus_full = avg_in_full - avg_out_full
    adj_in_3m  = sum(adj_in[-3:]) / 3
    avg_out_3m = sum(monthly_out[-3:]) / 3
    surplus_3m = adj_in_3m - avg_out_3m
    max_pmt_full = max(0, surplus_full / DSCR_BUFFER)
    max_pmt_3m   = max(0, surplus_3m   / DSCR_BUFFER)
    max_loan_full_dscr = min(MAX_LOAN, pmt_to_principal(max_pmt_full))
    max_loan_3m_dscr   = min(MAX_LOAN, pmt_to_principal(max_pmt_3m))
    max_loan_full_zero = min(MAX_LOAN, pmt_to_principal(max(0, surplus_full)))
    max_loan_3m_zero   = min(MAX_LOAN, pmt_to_principal(max(0, surplus_3m)))
    pmt_10k = principal_to_pmt(10_000)
    pmt_25k = principal_to_pmt(25_000)
    pmt_50k = principal_to_pmt(50_000)
    return {
        'avg_in_full':        round(avg_in_full),
        'avg_out_full':       round(avg_out_full),
        'surplus_full':       round(surplus_full),
        'avg_in_3m':          round(adj_in_3m),
        'avg_out_3m':         round(avg_out_3m),
        'surplus_3m':         round(surplus_3m),
        'max_pmt_full':       round(max_pmt_full),
        'max_pmt_3m':         round(max_pmt_3m),
        'max_loan_full_dscr': round(max_loan_full_dscr / 100) * 100,
        'max_loan_3m_dscr':   round(max_loan_3m_dscr   / 100) * 100,
        'max_loan_full_zero': round(max_loan_full_zero  / 100) * 100,
        'max_loan_3m_zero':   round(max_loan_3m_zero    / 100) * 100,
        'pmt_10k':            round(pmt_10k),
        'pmt_25k':            round(pmt_25k),
        'pmt_50k':            round(pmt_50k),
        'annual_rate':        ANNUAL_RATE,
        'monthly_rate':       MONTHLY_RATE,
        'n_months':           N_MONTHS,
    }


# ============================================================
# CREDIT FLAGS
# ============================================================

def check_gambling(transactions):
    hits = [t for t in transactions if any(k in t['description'].lower() for k in GAMBLING_KEYWORDS)]
    return {'found': len(hits) > 0, 'count': len(hits), 'transactions': hits}


def check_sanctions(transactions):
    sanction_hits = []
    middle_east   = []
    for t in transactions:
        d = t['description'].lower()
        for sc in SANCTIONED_COUNTRIES:
            if sc in d:
                sanction_hits.append(t)
        if any(k in d for k in MIDDLE_EAST_KEYWORDS):
            middle_east.append(t)
    return {'sanction_hits': sanction_hits, 'middle_east_txs': middle_east, 'clean': len(sanction_hits) == 0}


def check_salary_consistency(transactions, month_labels):
    n = len(month_labels)
    paye_by_month = [0.0] * n
    for tx in transactions:
        d = tx['description'].lower()
        if 'hmrc cumbernauld' in d or ('hmrc' in d and 'pj' in d):
            for fmt in ('%d/%m/%y', '%d/%m/%Y'):
                try:
                    dt = datetime.strptime(tx['date'], fmt)
                    label = dt.strftime('%b-%y')
                    if label in month_labels:
                        idx = month_labels.index(label)
                        paye_by_month[idx] += tx['money_out']
                    break
                except ValueError:
                    continue
    nonzero = [v for v in paye_by_month if v > 0]
    if len(nonzero) >= 2:
        variance_pct = (max(nonzero) - min(nonzero)) / min(nonzero) * 100
    else:
        variance_pct = 0
    return {
        'paye_by_month': paye_by_month,
        'variance_pct':  round(variance_pct, 1),
        'consistent':    variance_pct < 10,
        'month_labels':  month_labels
    }


def check_low_balance_days(daily_series):
    below_5k = [(d.strftime('%d/%m/%y'), b) for d, b in daily_series if 0 < b < 5000]
    below_2k = [(d.strftime('%d/%m/%y'), b) for d, b in daily_series if 0 < b < 2000]
    return {
        'below_5k_count': len(below_5k),
        'below_2k_count': len(below_2k),
        'below_5k_days':  below_5k,
        'below_2k_days':  below_2k,
        'lowest':         min(daily_series, key=lambda x: x[1]) if daily_series else None
    }


def check_failed_dds(transactions):
    failed = [t for t in transactions if
              'unpaid direct debit' in t['description'].lower() or
              'unpaid dd' in t['description'].lower()]
    return {'count': len(failed), 'transactions': failed}


def find_lenders(transactions):
    lenders = {
        'iwoca':           {'name': 'iwoca',              'product': 'Unsecured / Revolving',      'keywords': ['iwoca']},
        'armada':          {'name': 'Armada Asset Finance','product': 'Asset Finance',              'keywords': ['armada']},
        'premium_credit':  {'name': 'Premium Credit Ltd', 'product': 'Insurance Premium Finance',  'keywords': ['premium credit']},
        'stellantis':      {'name': 'Stellantis FS UK',   'product': 'Vehicle Finance',            'keywords': ['stellantis']},
        'sme_finance':     {'name': 'SME Finance Partner','product': 'Business Finance',           'keywords': ['sme finance']},
    }
    results = {}
    for key, info in lenders.items():
        matched = [t for t in transactions if
                   any(k in t['description'].lower() for k in info['keywords'])
                   and t['money_out'] > 0]
        total = sum(t['money_out'] for t in matched)
        results[key] = {
            'name': info['name'], 'product': info['product'],
            'total': total, 'transactions': matched, 'count': len(matched)
        }
    return results


def find_top_transactions(transactions, n=5):
    top_in  = sorted([t for t in transactions if t['money_in'] > 0], key=lambda x: -x['money_in'])[:n]
    top_out = sorted([t for t in transactions if t['money_out'] > 0], key=lambda x: -x['money_out'])[:n]
    return top_in, top_out


def find_connected_parties(transactions):
    keywords_out = ['antrum', 'daniel spokes', 'pershing', 'keith nair']
    keywords_in  = ['joene', 'metal monkeys', 'antrum']
    out = [t for t in transactions if any(k in t['description'].lower() for k in keywords_out) and t['money_out'] > 0]
    inp = [t for t in transactions if any(k in t['description'].lower() for k in keywords_in)  and t['money_in']  > 0]
    return out, inp


# ============================================================
# MASTER ANALYTICS FUNCTION
# ============================================================

def run_analytics(parsed_statements):
    transactions = merge_statements(parsed_statements)
    meta_list    = get_statement_metadata(parsed_statements)
    if not meta_list:
        return None
    period_start   = meta_list[0]['start']
    period_end     = meta_list[-1]['end']
    opening_bal    = meta_list[0]['opening_balance']
    closing_bal    = meta_list[-1]['closing_balance']
    account_name   = meta_list[0]['account_name']
    account_number = meta_list[0]['account_number']
    sort_code      = meta_list[0]['sort_code']
    month_labels = []
    seen_months = set()
    for meta in meta_list:
        d = meta['start']
        while d <= meta['end']:
            label = d.strftime('%b-%y')
            if label not in seen_months:
                seen_months.add(label)
                month_labels.append(label)
            if d.month == 12:
                d = d.replace(year=d.year + 1, month=1, day=1)
            else:
                d = d.replace(month=d.month + 1, day=1)
    n_months = len(month_labels)
    monthly, monthly_in, monthly_out = build_monthly_buckets(transactions, period_start, n_months)
    closing_bals = [m['closing_balance'] for m in meta_list]
    daily_series = build_daily_series(transactions, opening_bal, period_start, period_end)
    daily_vals   = [b for _, b in daily_series]
    avg_bal_full = round(sum(daily_vals) / len(daily_vals)) if daily_vals else 0
    cutoff = period_end - timedelta(days=90)
    daily_3m = [b for d, b in daily_series if d >= cutoff]
    avg_bal_3m = round(sum(daily_3m) / len(daily_3m)) if daily_3m else 0
    intramonth_data, avg_intramonth = build_intramonth_profile(daily_series, meta_list)
    lenders = find_lenders(transactions)
    avg_monthly_in = sum(monthly_in) / n_months if n_months else 0
    large_inflows  = sorted([t for t in transactions if t['money_in'] > avg_monthly_in * 2],
                             key=lambda x: -x['money_in'])
    anomaly_amount    = 0
    anomaly_month_idx = None
    if large_inflows:
        biggest = large_inflows[0]
        anomaly_amount = biggest['money_in']
        for fmt in ('%d/%m/%y', '%d/%m/%Y'):
            try:
                dt = datetime.strptime(biggest['date'], fmt)
                label = dt.strftime('%b-%y')
                if label in month_labels:
                    anomaly_month_idx = month_labels.index(label)
                break
            except ValueError:
                continue
    affordability = calc_affordability(
        monthly_in, monthly_out,
        anomaly_amount=anomaly_amount,
        anomaly_month_idx=anomaly_month_idx
    )
    gambling      = check_gambling(transactions)
    sanctions     = check_sanctions(transactions)
    salary        = check_salary_consistency(transactions, month_labels)
    low_balance   = check_low_balance_days(daily_series)
    failed_dds    = check_failed_dds(transactions)
    top_in, top_out = find_top_transactions(transactions)
    connected_out, connected_in = find_connected_parties(transactions)
    existing_debt_service = (
        lenders['iwoca']['total'] / n_months +
        lenders['armada']['total'] / n_months +
        lenders['premium_credit']['total'] / n_months +
        lenders['stellantis']['total'] / n_months
    )
    return {
        'account_name': account_name, 'account_number': account_number,
        'sort_code': sort_code,
        'period_start': period_start.strftime('%d/%m/%y'),
        'period_end': period_end.strftime('%d/%m/%y'),
        'opening_bal': opening_bal, 'closing_bal': closing_bal,
        'n_months': n_months, 'month_labels': month_labels,
        'meta_list': meta_list,
        'transactions': transactions, 'total_tx_count': len(transactions),
        'monthly': monthly, 'monthly_in': monthly_in, 'monthly_out': monthly_out,
        'closing_bals': closing_bals,
        'daily_series': [(d.strftime('%d/%m/%y'), b) for d, b in daily_series],
        'avg_bal_full': avg_bal_full, 'avg_bal_3m': avg_bal_3m,
        'intramonth_data': intramonth_data, 'avg_intramonth': avg_intramonth,
        'lenders': lenders, 'existing_debt_svc': round(existing_debt_service),
        'anomaly_amount': anomaly_amount,
        'anomaly_tx': large_inflows[0] if large_inflows else None,
        'anomaly_month_idx': anomaly_month_idx,
        'affordability': affordability,
        'gambling': gambling, 'sanctions': sanctions,
        'salary': salary, 'low_balance': low_balance,
        'failed_dds': failed_dds,
        'top_in': top_in, 'top_out': top_out,
        'connected_out': connected_out, 'connected_in': connected_in,
    }
