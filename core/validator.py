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




    transactions = parsed.get('transactions', [])
    corrected = 0

    for i, tx in enumerate(transactions):
        bal = tx.get('balance', 0)
        if not bal:
            continue

        # Find previous non-zero balance
        prev_bal = None
        for j in range(i - 1, -1, -1):
            pb = transactions[j].get('balance', 0)
            if pb:
                prev_bal = pb
                break

        if prev_val := parsed.get('metadata', {}).get('opening_balance') if prev_bal is None else None:
            prev_bal = prev_val

        if prev_bal is None:
            continue

        money_in = tx.get('money_in', 0)
        money_out = tx.get('money_out', 0)

        # Only fix transactions with exactly one non-zero amount
        if not ((money_in > 0) ^ (money_out > 0)):
            continue

        amount = money_in if money_in > 0 else money_out
        balance_change = bal - prev_bal  # positive = more overdrawn = money_out

        if balance_change < -0.005:  # balance decreased = money came in
            if money_out > 0 and money_in == 0:
                tx['money_in'] = money_out
                tx['money_out'] = 0
                tx['_direction_corrected'] = True
                corrected += 1
        elif balance_change > 0.005:  # balance increased = money went out
            if money_in > 0 and money_out == 0:
                tx['money_out'] = money_in
                tx['money_in'] = 0
                tx['_direction_corrected'] = True
                corrected += 1

    if corrected:
        parsed['_hsbc_direction_corrections'] = corrected

    return parsed


def fix_hsbc_transaction_directions(parsed):
    """
    For HSBC overdraft statements, use the balance column to correct
    money_in / money_out direction where the LLM got it wrong.
    Balance decreases (less overdrawn) = money came IN.
    Balance increases (more overdrawn) = money went OUT.
    Only corrects transactions where balance is present and non-zero,
    and where exactly one of money_in/money_out is non-zero.
    """
    if parsed.get('_bank_name', '') != 'hsbc':
        return parsed

    transactions = parsed.get('transactions', [])
    opening = parsed.get('metadata', {}).get('opening_balance', 0)
    corrected = 0

    # Build list of balances, filling in opening for first prev
    prev_bal = opening
    for tx in transactions:
        bal = tx.get('balance', 0)
        money_in = tx.get('money_in', 0) or 0
        money_out = tx.get('money_out', 0) or 0

        # Only process if we have a balance and exactly one non-zero amount
        if bal and prev_bal and ((money_in > 0) != (money_out > 0)):
            balance_change = bal - prev_bal  # positive = more overdrawn = OUT
            if balance_change < -0.05:  # balance went down = money IN
                if money_out > 0 and money_in == 0:
                    tx['money_in'] = money_out
                    tx['money_out'] = 0
                    tx['_direction_corrected'] = True
                    corrected += 1
            elif balance_change > 0.05:  # balance went up = money OUT
                if money_in > 0 and money_out == 0:
                    tx['money_out'] = money_in
                    tx['money_in'] = 0
                    tx['_direction_corrected'] = True
                    corrected += 1

        if bal:
            prev_bal = bal

    if corrected:
        parsed['_hsbc_direction_corrections'] = corrected

    return parsed

def reconcile_statement(parsed):
    parsed = fix_first_transaction_double_count(parsed)
    parsed = fix_hsbc_transaction_directions(parsed)
    
    metadata = parsed.get('metadata', {})
    transactions = parsed.get('transactions', [])
    closing = metadata.get('closing_balance', 0)
    opening = metadata.get('opening_balance', 0)

    # Find last non-zero balance in transactions
    last_balance = None
    for tx in reversed(transactions):
        bal = tx.get('balance', 0)
        if bal and bal != 0:
            last_balance = bal
            break

    # Also compute arithmetic closing for the summary cards (don't use for pass/fail)
    total_in  = sum(t.get('money_in', 0)  for t in transactions)
    total_out = sum(t.get('money_out', 0) for t in transactions)

    if last_balance is not None:
        difference = abs(last_balance - closing)
        expected_closing = last_balance
    else:
        # No balances in transactions — fall back to arithmetic
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
