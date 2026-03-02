import pdfplumber
import os
from collections import defaultdict

# Minimum characters per page to consider a PDF text-based
MIN_CHARS_PER_PAGE = 300

def check_pdf_quality(pdf_path):
    """
    Check whether a PDF is text-based or image/scan based.
    Returns a dict with:
        - is_text_based: bool
        - page_count: int
        - avg_chars_per_page: float
        - reason: str (explanation if rejected)
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            page_count = len(pdf.pages)
            
            if page_count == 0:
                return {
                    'is_text_based': False,
                    'page_count': 0,
                    'avg_chars_per_page': 0,
                    'reason': 'PDF has no pages'
                }
            
            total_chars = 0
            for page in pdf.pages:
                text = page.extract_text() or ''
                total_chars += len(text)
            
            avg_chars = total_chars / page_count
            
            if avg_chars < MIN_CHARS_PER_PAGE:
                return {
                    'is_text_based': False,
                    'page_count': page_count,
                    'avg_chars_per_page': round(avg_chars),
                    'reason': f'Average {round(avg_chars)} characters per page — likely a scanned image. Minimum required: {MIN_CHARS_PER_PAGE}. Please provide native digital statements downloaded from online banking.'
                }
            
            return {
                'is_text_based': True,
                'page_count': page_count,
                'avg_chars_per_page': round(avg_chars),
                'reason': 'OK'
            }
    
    except Exception as e:
        return {
            'is_text_based': False,
            'page_count': 0,
            'avg_chars_per_page': 0,
            'reason': f'Could not open PDF: {str(e)}'
        }


def _needs_char_grouping(pdf):
    """
    Detect whether a PDF has overlapping text objects that cause
    pdfplumber's extract_text() to interleave characters.
    
    This is common with Lloyds Bank PDFs where the description and
    reference number on the next line overlap in x-coordinates,
    causing garbled output like 'DC 1 escription 0 A 0 P 0 I 0 T...'
    
    Detection: check if the first page's extract_text() contains
    garbled column headers like 'CDolumn' or 'escription' without
    a preceding 'D' (which would indicate interleaving).
    """
    try:
        page = pdf.pages[0]
        text = page.extract_text() or ''
        # Lloyds interleaving signature: column headers get mangled
        garble_markers = ['CDolumn', 'escription', 'TFype', 'TBype', 'TSype', 'TDype']
        hits = sum(1 for m in garble_markers if m in text)
        return hits >= 2
    except Exception:
        return False


def _extract_text_by_char_position(pdf):
    """
    Extract text from a PDF by grouping characters by their y-position.
    
    This avoids the interleaving problem where pdfplumber's default
    extract_text() merges characters from overlapping text objects
    (e.g. a description line and a reference number line that share
    the same x-coordinate range but different y-coordinates).
    
    Groups characters into rows using a 2px y-tolerance, then
    reconstructs each row left-to-right.
    """
    full_text = ''
    for i, page in enumerate(pdf.pages):
        chars = page.chars
        if not chars:
            text = page.extract_text() or ''
            full_text += f'\n--- PAGE {i+1} ---\n{text}'
            continue
        
        rows = defaultdict(list)
        for c in chars:
            y_key = round(c['top'] / 2) * 2  # snap to 2px grid
            rows[y_key].append(c)
        
        lines = []
        for y in sorted(rows.keys()):
            chars_in_row = sorted(rows[y], key=lambda c: c['x0'])
            text = ''.join(c['text'] for c in chars_in_row).strip()
            # Skip dot-only lines (PDF artifacts)
            if text and not all(c == '.' for c in text):
                lines.append(text)
        
        full_text += f'\n--- PAGE {i+1} ---\n' + '\n'.join(lines)
    
    return full_text


def extract_text(pdf_path):
    """
    Extract all text from a text-based PDF.
    Returns a single string with all pages concatenated.
    
    Automatically detects Lloyds-style PDFs with overlapping text objects
    and uses character-level y-position grouping to avoid garbled output.
    Falls back to standard extract_text() for all other banks.
    """
    with pdfplumber.open(pdf_path) as pdf:
        if _needs_char_grouping(pdf):
            return _extract_text_by_char_position(pdf)
        
        # Standard extraction for well-behaved PDFs
        full_text = ''
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ''
            full_text += f'\n--- PAGE {i+1} ---\n{text}'
        return full_text
