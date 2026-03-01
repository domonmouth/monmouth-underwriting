import pdfplumber
import os

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


def extract_text(pdf_path):
    """
    Extract all text from a text-based PDF.
    Returns a single string with all pages concatenated.
    """
    full_text = ''
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ''
            full_text += f'\n--- PAGE {i+1} ---\n{text}'
    return full_text
