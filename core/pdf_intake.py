import pdfplumber
import os
import re
from collections import defaultdict

# Minimum characters per page to consider a PDF text-based
MIN_CHARS_PER_PAGE = 300


def check_pdf_quality(pdf_path):
    """
    Check whether a PDF is text-based or image/scan based.
    """
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


# ── Lloyds detection & extraction ──────────────────────────────────

def _needs_char_grouping(pdf):
    """Detect Lloyds-style PDFs with overlapping text objects."""
    try:
        text = pdf.pages[0].extract_text() or ''
        garble_markers = ['CDolumn', 'escription', 'TFype', 'TBype', 'TSype', 'TDype']
        return sum(1 for m in garble_markers if m in text) >= 2
    except Exception:
        return False


def _extract_text_by_char_position(pdf):
    """Extract text by y-position grouping (fixes Lloyds interleaving)."""
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


# ── Starling detection & extraction ────────────────────────────────

def _is_starling(pdf):
    """Detect Starling Bank PDFs."""
    try:
        text = pdf.pages[0].extract_text() or ''
        return 'starlingbank.com' in text.lower() or 'STARLING' in text
    except Exception:
        return False


def _find_starling_column_boundary(page):
    """
    Find the x-position boundary between IN and OUT columns
    from the header row. Returns the boundary x value or None.
    """
    chars_by_y = defaultdict(list)
    for c in page.chars:
        chars_by_y[round(c['top'])].append(c)

    for y in sorted(chars_by_y.keys()):
        row_chars = sorted(chars_by_y[y], key=lambda c: c['x0'])
        row_text = ''.join(c['text'] for c in row_chars)
        if 'TRANSACTION' in row_text and 'IN' in row_text and 'OUT' in row_text:
            in_x = out_x = None
            for j, c in enumerate(row_chars):
                # Find 'IN' header (after TRANSACTION area, x > 350)
                if c['text'] == 'I' and j + 1 < len(row_chars) and row_chars[j + 1]['text'] == 'N' and c['x0'] > 350:
                    if in_x is None:
                        in_x = c['x0']
                # Find 'OUT' header
                if c['text'] == 'O' and j + 2 < len(row_chars) and row_chars[j + 1]['text'] == 'U' and row_chars[j + 2]['text'] == 'T' and c['x0'] > 350:
                    out_x = c['x0']
            if in_x and out_x:
                return (in_x + out_x) / 2, out_x
    return None


def _extract_starling_text(pdf):
    """
    Extract Starling PDFs with column-aware amount tagging.
    
    Tags each £amount with [IN] or [OUT] based on its x-position
    relative to the column headers, so the LLM parser can correctly
    assign money_in vs money_out.
    """
    # Find column boundary from first page with header
    col_info = None
    for page in pdf.pages:
        col_info = _find_starling_column_boundary(page)
        if col_info:
            break

    if not col_info:
        # Fallback to standard extraction
        full_text = ''
        for i, page in enumerate(pdf.pages):
            full_text += f'\n--- PAGE {i+1} ---\n{page.extract_text() or ""}'
        return full_text

    boundary, out_x = col_info

    full_text = ''
    for i, page in enumerate(pdf.pages):
        # Find header row y-position on this page so we only tag transaction rows
        header_y = None
        chars_by_y_hdr = defaultdict(list)
        for c in page.chars:
            chars_by_y_hdr[round(c['top'])].append(c)
        for y_h in sorted(chars_by_y_hdr.keys()):
            row_text = ''.join(ch['text'] for ch in sorted(chars_by_y_hdr[y_h], key=lambda ch: ch['x0']))
            if 'TRANSACTION' in row_text and 'IN' in row_text and 'OUT' in row_text:
                header_y = y_h
                break

        # Map each £ sign to its column based on x-position
        # Only tag £ signs that are below the header row (skip summary/header area)
        pound_info = {}  # y -> list of (x, column)
        for c in page.chars:
            if c['text'] == '£':
                y = round(c['top'])
                x = c['x0']
                # Skip any £ signs above or at the header row (summary area)
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

        # Extract text line by line using character positions
        chars_by_y = defaultdict(list)
        for c in page.chars:
            chars_by_y[round(c['top'])].append(c)

        lines = []
        for y in sorted(chars_by_y.keys()):
            row = sorted(chars_by_y[y], key=lambda c: c['x0'])
            line_text = ''.join(c['text'] for c in row).strip()
            if not line_text:
                continue

            # Tag £ amounts with their column
            if y in pound_info and '£' in line_text:
                cols = sorted(pound_info[y], key=lambda t: t[0])
                # Process amounts left to right
                tagged = line_text
                offset = 0
                for x_pos, col in cols:
                    if col in ('IN', 'OUT'):
                        # Find the next £ in the remaining string
                        search_start = 0
                        for _ in range(cols.index((x_pos, col)) + 1):
                            idx = tagged.find('£', search_start)
                            if idx >= 0:
                                search_start = idx + 1
                        idx = tagged.find('£', 0)
                        # Simple approach: find nth £ sign
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


# ── Main extraction function ───────────────────────────────────────

def extract_text(pdf_path):
    """
    Extract all text from a text-based PDF.
    
    Automatically detects bank-specific PDF formats:
    - Lloyds: character-level y-position grouping (fixes interleaving)
    - Starling: column-aware extraction (tags IN/OUT amounts)
    - All others: standard pdfplumber extract_text()
    """
    with pdfplumber.open(pdf_path) as pdf:
        if _needs_char_grouping(pdf):
            return _extract_text_by_char_position(pdf)
        if _is_starling(pdf):
            return _extract_starling_text(pdf)
        full_text = ''
        for i, page in enumerate(pdf.pages):
            full_text += f'\n--- PAGE {i+1} ---\n{page.extract_text() or ""}'
        return full_text
