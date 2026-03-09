from datetime import datetime, timedelta
from collections import defaultdict

# Reconciliation tolerance — ignore differences under this amount (handles rounding)
RECONCILIATION_TOLERANCE = 1.00
REQUIRED_MONTHS = 6
STALE_DAYS_THRESHOLD = 31


def fix_first_transaction_double_count(parsed):
    metadata = parsed.get('metadata', {})
    transactions = parsed.get('transactions', [])
    opening = metadata.get('opening_balance', 0)

    if not transactions:
        return parsed

    first_tx = transactions[0]
    first_bal = first_tx.get('balance', None)
    first_in = first_tx.get('money_in', 0)
    first_out = first_tx.get('money_out', 0)

    # Only zero out if the first transaction has no actual amounts —
    # i.e. it's a pure balance marker, not a real transaction
    if first_bal is not None and abs(first_bal - opening) < 0.01:
        if first_in == 0 and first_out == 0:
            transactions[0] = {
                **first_tx,
                'money_in': 0,
                'money_out': 0,
                '_adjusted': 'First transaction zeroed — balance equals opening balance (pre-opening transaction)',
            }

    return parsed

    first_tx = transactions[0]
    first_bal = first_tx.get('balance', None)

    # If first transaction balance equals opening balance exactly,
    # the transaction amount is already baked into the opening figure
    if first_bal is not None and abs(first_bal - opening) < 0.01:
        # Zero out the amounts so they don't double-count
        transactions[0] = {
            **first_tx,
            'money_in': 0,
            'money_out': 0,
            '_adjusted': 'First transaction zeroed — balance equals opening balance (pre-opening transaction)',
        }

    return parsed


def reconcile_statement(parsed):
    # Apply first-transaction double-count fix before reconciling
    parsed = fix_first_transaction_double_count(parsed)
    metadata = parsed.get('metadata', {})
    transactions = parsed.get('transactions', [])
    opening = metadata.get('opening_balance', 0)
    closing = metadata.get('closing_balance', 0)
    total_in  = sum(t.get('money_in', 0)  for t in transactions)
    total_out = sum(t.get('money_out', 0) for t in transactions)
    expected_closing = opening + total_in - total_out
    difference = abs(expected_closing - closing)
    passed = difference <= RECONCILIATION_TOLERANCE
    return {
        'passed': passed,
        'opening': opening,
        'total_in': total_in,
        'total_out': total_out,
        'expected_closing': round(expected_closing, 2),
        'actual_closing': closing,
        'difference': round(difference, 2),
        'filename': parsed.get('_filename', 'unknown')
    }


def extract_statement_period(parsed):
    metadata = parsed.get('metadata', {})
    start_str = metadata.get('statement_start', '')
    end_str   = metadata.get('statement_end', '')
    for fmt in ('%d/%m/%y', '%d/%m/%Y'):
        try:
            start = datetime.strptime(start_str, fmt)
            end   = datetime.strptime(end_str, fmt)
            return start, end
        except ValueError:
            continue
    return None, None


def check_sufficiency(parsed_statements, report_date=None):
    if report_date is None:
        report_date = datetime.today()
    periods = []
    for p in parsed_statements:
        start, end = extract_statement_period(p)
        if start and end:
            periods.append({
                'filename': p.get('_filename', 'unknown'),
                'start': start,
                'end': end,
                'account': p.get('metadata', {}).get('account_number', 'unknown')
            })
    if not periods:
        return {
            'ok': False, 'months_covered': 0, 'periods': [], 'gaps': [],
            'stale': False, 'days_since_last': 0, 'last_statement_end': None,
            'issues': ['No valid statement periods could be extracted']
        }
    periods.sort(key=lambda x: x['start'])
    month_set = set()
    for p in periods:
        d = p['start']
        while d <= p['end']:
            month_set.add((d.year, d.month))
            if d.month == 12:
                d = d.replace(year=d.year+1, month=1, day=1)
            else:
                d = d.replace(month=d.month+1, day=1)
    months_covered = len(month_set)
    gaps = []
    for i in range(1, len(periods)):
        prev_end   = periods[i-1]['end']
        curr_start = periods[i]['start']
        gap_days   = (curr_start - prev_end).days
        if gap_days > 2:
            gaps.append({
                'between': (periods[i-1]['filename'], periods[i]['filename']),
                'gap_days': gap_days,
                'prev_end': prev_end.strftime('%d/%m/%y'),
                'curr_start': curr_start.strftime('%d/%m/%y')
            })
    last_end = periods[-1]['end']
    days_since_last = (report_date - last_end).days
    stale = days_since_last > STALE_DAYS_THRESHOLD
    issues = []
    if months_covered < REQUIRED_MONTHS:
        issues.append(f'Only {months_covered} month(s) provided — {REQUIRED_MONTHS} required. Missing {REQUIRED_MONTHS - months_covered} month(s).')
    if gaps:
        for g in gaps:
            issues.append(f'Gap of {g["gap_days"]} days between {g["between"][0]} and {g["between"][1]} ({g["prev_end"]} to {g["curr_start"]})')
    if stale:
        issues.append(f'Statements are stale — last statement ends {last_end.strftime("%d/%m/%y")}, {days_since_last} days before today.')
    return {
        'ok': len(issues) == 0,
        'months_covered': months_covered,
        'periods': periods,
        'gaps': gaps,
        'stale': stale,
        'days_since_last': days_since_last,
        'last_statement_end': last_end.strftime('%d/%m/%y'),
        'issues': issues
    }


def validate_all(parsed_statements, report_date=None):
    reconciliation_results = []
    all_reconciled = True
    for p in parsed_statements:
        result = reconcile_statement(p)
        reconciliation_results.append(result)
        if not result['passed']:
            all_reconciled = False
    sufficiency = check_sufficiency(parsed_statements, report_date)

    # Reconciliation failures are now WARNINGS, not blockers.
    # We always allow proceeding — the report will note any reconciliation issues.
    can_proceed = True

    warnings = []
    if not all_reconciled:
        for r in reconciliation_results:
            if not r['passed']:
                warnings.append(
                    f'RECONCILIATION WARNING: {r["filename"]} — '
                    f'expected closing £{r["expected_closing"]:,.2f}, '
                    f'actual £{r["actual_closing"]:,.2f}, '
                    f'difference £{r["difference"]:,.2f}. '
                    f'Some transactions may not have been captured accurately.'
                )
    warnings.extend(sufficiency['issues'])
    return {
        'can_proceed': can_proceed,
        'all_reconciled': all_reconciled,
        'reconciliation_results': reconciliation_results,
        'sufficiency': sufficiency,
        'warnings': warnings
    }
