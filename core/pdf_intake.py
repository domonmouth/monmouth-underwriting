import pdfplumber
import os
import re
from collections import defaultdict

# Minimum characters per page to consider a PDF text-based
MIN_CHARS_PER_PAGE = 300


def check_pdf_quality(pdf_path):
    try:
        with pdfplumber.open(pdf_path) as pdf:
            page_count = len(pdf.pages)
            if page_count == 0:
                return {'is_text_based': False, 'page_count': 0, 'avg_chars_per_page': 0, 'reason': 'PDF has no pages'}
            total_chars = sum(len(page.extract_text() or '') for page in pdf.pages)
            avg_chars = total_chars / page_count
            if avg_chars < MIN_CHARS_PER_PAGE:
                return {
                    'is_text_based': False, 'page_count': page_count,
                    'avg_chars_per_page': round(avg_chars),
                    'reason': f'Average {round(avg_chars)} characters per page — likely a scanned image. Minimum required: {MIN_CHARS_PER_PAGE}. Please provide native digital statements downloaded from online banking.'
                }
            return {'is_text_based': True, 'page_count': page_count, 'avg_chars_per_page': round(avg_chars), 'reason': 'OK'}
    except Exception as e:
        return {'is_text_based': False, 'page_count': 0, 'avg_chars_per_page': 0, 'reason': f'Could not open PDF: {str(e)}'}


def _needs_char_grouping(pdf):
    try:
        text = pdf.pages[0].extract_text() or ''
        garble_markers = ['CDolumn', 'escription', 'TFype', 'TBype', 'TSype', 'TDype']
        return sum(1 for m in garble_markers if m in text) >= 2
    except Exception:
        return False


def _extract_text_by_char_position(pdf):
    full_text = ''
    for i, page in enumerate(pdf.pages):
        chars = page.chars
        if not chars:
            full_text += f'\n--- PAGE {i+1} ---\n{page.extract_text() or ""}'
            continue
        rows = defaultdict(list)
        for c in chars:
            rows[round(c['top'] / 2) * 2].append(c)
        lines = []
        for y in sorted(rows.keys()):
            text = ''.join(c['text'] for c in sorted(rows[y], key=lambda c: c['x0'])).strip()
            if text and not all(c == '.' for c in text):
                lines.append(text)
        full_text += f'\n--- PAGE {i+1} ---\n' + '\n'.join(lines)
    return full_text


def _is_starling(pdf):
    try:
        text = pdf.pages[0].extract_text() or ''
        return 'starlingbank.com' in text.lower() or 'STARLING' in text
    except Exception:
        return False


def _find_starling_column_boundary(page):
    chars_by_y = defaultdict(list)
    for c in page.chars:
        chars_by_y[round(c['top'])].append(c)

    for y in sorted(chars_by_y.keys()):
        row_chars = sorted(chars_by_y[y], key=lambda c: c['x0'])
        row_text = ''.join(c['text'] for c in row_chars)
        if 'TRANSACTION' in row_text and 'IN' in row_text and 'OUT' in row_text:
            in_x = out_x = None
            for j, c in enumerate(row_chars):
                if c['text'] == 'I' and j + 1 < len(row_chars) and row_chars[j + 1]['text'] == 'N' and c['x0'] > 350:
                    if in_x is None:
                        in_x = c['x0']
                if c['text'] == 'O' and j + 2 < len(row_chars) and row_chars[j + 1]['text'] == 'U' and row_chars[j + 2]['text'] == 'T' and c['x0'] > 350:
                    out_x = c['x0']
            if in_x and out_x:
                return (in_x + out_x) / 2, out_x
    return None


def _extract_starling_text(pdf):
    col_info = None
    for page in pdf.pages:
        col_info = _find_starling_column_boundary(page)
        if col_info:
            break

    if not col_info:
        full_text = ''
        for i, page in enumerate(pdf.pages):
            full_text += f'\n--- PAGE {i+1} ---\n{page.extract_text() or ""}'
        return full_text

    boundary, out_x = col_info

    full_text = ''
    for i, page in enumerate(pdf.pages):
        header_y = None
        chars_by_y_hdr = defaultdict(list)
        for c in page.chars:
            chars_by_y_hdr[round(c['top'])].append(c)
        for y_h in sorted(chars_by_y_hdr.keys()):
            row_text = ''.join(ch['text'] for ch in sorted(chars_by_y_hdr[y_h], key=lambda ch: ch['x0']))
            if 'TRANSACTION' in row_text and 'IN' in row_text and 'OUT' in row_text:
                header_y = y_h
                break

        pound_info = {}
        for c in page.chars:
            if c['text'] == '£':
                y = round(c['top'])
                x = c['x0']
                if header_y is not None and y <= header_y:
                    continue
                if x < boundary:
                    col = 'IN'
                elif x < out_x + 30:
                    col = 'OUT'
                else:
                    col = 'BAL'
                if y not in pound_info:
                    pound_info[y] = []
                pound_info[y].append((x, col))

        chars_by_y = defaultdict(list)
        for c in page.chars:
            chars_by_y[round(c['top'])].append(c)

        lines = []
        for y in sorted(chars_by_y.keys()):
            row = sorted(chars_by_y[y], key=lambda c: c['x0'])
            line_text = ''.join(c['text'] for c in row).strip()
            if not line_text:
                continue

            if y in pound_info and '£' in line_text:
                cols = sorted(pound_info[y], key=lambda t: t[0])
                tagged = line_text
                for x_pos, col in cols:
                    if col in ('IN', 'OUT'):
                        pound_count = 0
                        target_idx = -1
                        for ci, ch in enumerate(tagged):
                            if ch == '£':
                                if pound_count == cols.index((x_pos, col)):
                                    target_idx = ci
                                    break
                                pound_count += 1
                        if target_idx >= 0:
                            tag = f'[{col}]'
                            tagged = tagged[:target_idx] + tag + tagged[target_idx:]
                line_text = tagged

            lines.append(line_text)

        full_text += f'\n--- PAGE {i+1} ---\n' + '\n'.join(lines)

    return full_text


def _is_hsbc(pdf):
    try:
        text = pdf.pages[0].extract_text() or ''
        return 'hsbc.co.uk' in text.lower() or 'HBUKGB' in text or 'HSBC UK' in text
    except Exception:
        return False


def _clean_hsbc_numbers(text):
    text = re.sub(
        r'(\d{1,3},\d{2})\s(\d\.\d{2})',
        lambda m: m.group(1) + m.group(2),
        text
    )
    return text


def _find_hsbc_column_boundaries(page):
    """
    Find x-positions of Paid out / Paid in headers.
    HSBC concatenates header chars: 'DatePaymenttypeanddetailsPaidoutPaidinBalance'
    Returns (paid_out_x, paid_in_x, header_y) or None.
    """
    chars_by_y = defaultdict(list)
    for c in page.chars:
        chars_by_y[round(c['top'])].append(c)

    for y in sorted(chars_by_y.keys()):
        row_chars = sorted(chars_by_y[y], key=lambda c: c['x0'])
        row_text = ''.join(c['text'] for c in row_chars)
        if 'Paidout' in row_text and 'Paidin' in row_text:
            paid_out_x = None
            paid_in_x = None
            i = 0
            while i < len(row_chars) - 5:
                word7 = ''.join(c['text'] for c in row_chars[i:i+7])
                word6 = ''.join(c['text'] for c in row_chars[i:i+6])
                if word7 == 'Paidout' and paid_out_x is None:
                    paid_out_x = row_chars[i]['x0']
                if word6 == 'Paidin' and paid_out_x is not None and paid_in_x is None:
                    paid_in_x = row_chars[i]['x0']
                i += 1
            if paid_out_x and paid_in_x:
                return paid_out_x, paid_in_x, y
    return None


def _tag_hsbc_row(row_chars, line_text, paid_out_x, out_in_boundary, in_bal_boundary):
    """
    Tag amounts in OUT/IN columns. Finds contiguous digit runs starting
    in the paid_out or paid_in x range and inserts [OUT]/[IN] before them.
    """
    groups = []
    i = 0
    while i < len(row_chars):
        c = row_chars[i]
        if c['text'].isdigit():
            x = c['x0']
            if x >= paid_out_x - 5:
                if x < out_in_boundary:
                    col = 'OUT'
                elif x < in_bal_boundary:
                    col = 'IN'
                else:
                    col = 'BAL'
                if col in ('OUT', 'IN'):
                    j = i
                    while j < len(row_chars) and row_chars[j]['text'] in '0123456789,.':
                        j += 1
                    num_text = ''.join(row_chars[k]['text'] for k in range(i, j))
                    if num_text:
                        groups.append((col, num_text))
                    i = j
                    continue
        i += 1

    if not groups:
        return line_text

    result = line_text
    search_start = 0
    for col, num_text in groups:
        tag = f'[{col}]'
        idx = result.find(num_text, search_start)
        if idx >= 0:
            result = result[:idx] + tag + result[idx:]
            search_start = idx + len(tag) + len(num_text)

    return result


def _extract_hsbc_text(pdf):
    """
    Extract HSBC PDFs with column-aware tagging.
    Numbers in Paid out column -> [OUT], Paid in column -> [IN].
    Falls back to plain extraction if column detection fails.
    """
    col_boundaries = None
    for page in pdf.pages:
        col_boundaries = _find_hsbc_column_boundaries(page)
        if col_boundaries:
            break

    if not col_boundaries:
        full_text = ''
        for i, page in enumerate(pdf.pages):
            full_text += f'\n--- PAGE {i+1} ---\n{page.extract_text() or ""}'
        return _clean_hsbc_numbers(full_text)

    paid_out_x, paid_in_x, _ = col_boundaries
    out_in_boundary = (paid_out_x + paid_in_x) / 2
    col_width = paid_in_x - paid_out_x
    in_bal_boundary = paid_in_x + col_width * 0.8

    full_text = ''
    for i, page in enumerate(pdf.pages):
        # Find header_y on this page
        header_y = None
        chars_by_y_hdr = defaultdict(list)
        for c in page.chars:
            chars_by_y_hdr[round(c['top'])].append(c)
        for y_h in sorted(chars_by_y_hdr.keys()):
            row_text = ''.join(ch['text'] for ch in sorted(chars_by_y_hdr[y_h], key=lambda ch: ch['x0']))
            if 'Paidout' in row_text and 'Paidin' in row_text:
                header_y = y_h
                break

        chars_by_y = defaultdict(list)
        for c in page.chars:
            chars_by_y[round(c['top'])].append(c)

        lines = []
        for y in sorted(chars_by_y.keys()):
            row = sorted(chars_by_y[y], key=lambda c: c['x0'])
            line_text = ''.join(c['text'] for c in row).strip()
            if not line_text:
                continue

            # Only tag rows strictly below the header row
            if header_y is not None and y > header_y:
                line_text = _tag_hsbc_row(row, line_text, paid_out_x, out_in_boundary, in_bal_boundary)

            lines.append(line_text)

        full_text += f'\n--- PAGE {i+1} ---\n' + '\n'.join(lines)

    return _clean_hsbc_numbers(full_text)


def extract_text(pdf_path):
    """
    Extract all text from a text-based PDF.
    Returns (text: str, bank_name: str)
    bank_name: 'lloyds', 'starling', 'hsbc', or 'unknown'
    """
    with pdfplumber.open(pdf_path) as pdf:
        if _needs_char_grouping(pdf):
            return _extract_text_by_char_position(pdf), 'lloyds'
        if _is_starling(pdf):
            return _extract_starling_text(pdf), 'starling'
        if _is_hsbc(pdf):
            return _extract_hsbc_text(pdf), 'hsbc'
        full_text = ''
        for i, page in enumerate(pdf.pages):
            full_text += f'\n--- PAGE {i+1} ---\n{page.extract_text() or ""}'
        return full_text, 'unknown'
