#!/usr/bin/env python3
"""
Monmouth Group — Underwriting Summary Generator
================================================
Pulls live data from the Companies House API and generates a formatted
PDF underwriting summary report.

Usage:
    python ch_report.py "COMPANY NAME"
    python ch_report.py --number 08584514

Requirements:
    pip install requests reportlab pypdf anthropic
"""

import argparse
import base64
import json
import os
import re
import sys
import textwrap
from datetime import date, datetime
from io import BytesIO

import requests
from reportlab.graphics.shapes import Circle, Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
    TableStyle,
)

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION — edit these
# ─────────────────────────────────────────────────────────────────────────────
CH_API_KEY    = os.environ.get("CH_API_KEY", "268d083f-9f2c-419e-84b6-56757026669c")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")   # optional — for AI analysis
SERP_API_KEY  = os.environ.get("SERP_API_KEY", "2dee65bc8e92a45f5c0a3ba4dd38c525c3b43afad310b9b349bd7844d3235072")
CH_BASE       = "https://api.company-information.service.gov.uk"
CH_DOC_BASE   = "https://document-api-public-live.ch.gov.uk"
OUTPUT_DIR    = os.path.expanduser("~/monmouth_reports")

# ─────────────────────────────────────────────────────────────────────────────
# COMPANIES HOUSE API CLIENT
# ─────────────────────────────────────────────────────────────────────────────
class CHClient:
    def __init__(self, api_key):
        self.session = requests.Session()
        self.session.auth = (api_key, "")
        self.session.headers.update({"Accept": "application/json"})

    def get(self, path, params=None):
        url = f"{CH_BASE}{path}"
        r = self.session.get(url, params=params, timeout=15)
        r.raise_for_status()
        return r.json()

    def search(self, company_name):
        return self.get("/search/companies", params={"q": company_name, "items_per_page": 5})

    def company(self, number):
        return self.get(f"/company/{number}")

    def officers(self, number):
        return self.get(f"/company/{number}/officers", params={"items_per_page": 100})

    def psc(self, number):
        return self.get(f"/company/{number}/persons-with-significant-control",
                        params={"items_per_page": 100})

    def charges(self, number):
        return self.get(f"/company/{number}/charges", params={"items_per_page": 100})

    def filing_history(self, number, category=None):
        params = {"items_per_page": 100}
        if category:
            params["category"] = category
        return self.get(f"/company/{number}/filing-history", params=params)

    def get_document(self, document_id):
        """Download a document PDF by its filing history document ID."""
        try:
            url = f"{CH_DOC_BASE}/document/{document_id}/content"
            r = self.session.get(url, timeout=15)
            if r.status_code == 200:
                return r.content
            return None
        except Exception:
            return None

    def officer_appointments(self, officer_id):
        return self.get(f"/officers/{officer_id}/appointments",
                        params={"items_per_page": 100})

    def check_disqualification(self, officer_id):
        """Check if an officer is disqualified via Companies House API.
        Returns dict with disqualifications key, or None on error.
        404 = not disqualified (clean). 200 = disqualification record found.
        """
        try:
            url = f"{CH_BASE}/disqualified-officers/natural/{officer_id}"
            r = self.session.get(url, timeout=15)
            if r.status_code == 404:
                # 404 means no disqualification record — person is clean
                return {"disqualifications": []}
            elif r.status_code == 200:
                return r.json()
            else:
                return None
        except Exception:
            return None

    def resolve_ubo(self, company_number, depth=0, visited=None, max_depth=5):
        """
        Recursively walk up the PSC tree to find Ultimate Beneficial Owner(s).
        Returns a list of dicts describing each node in the chain.
        """
        if visited is None:
            visited = set()
        if depth >= max_depth or company_number in visited:
            return []
        visited.add(company_number)

        chain = []
        try:
            psc_data = self.get(f"/company/{company_number}/persons-with-significant-control",
                                params={"items_per_page": 50})
            items = psc_data.get("items", [])
        except Exception:
            return []

        for item in items:
            # Skip ceased PSCs
            if item.get("ceased_on") or item.get("ceased"):
                continue

            kind = item.get("kind", "")
            name = item.get("name", "Unknown")
            natures = item.get("natures_of_control", [])

            if "individual" in kind:
                # Found a real person — end of chain
                dob = item.get("date_of_birth", {})
                chain.append({
                    "kind": "individual",
                    "name": name,
                    "nationality": item.get("nationality", "—"),
                    "dob": f"{dob.get('month','')}/{dob.get('year','')}",
                    "natures_of_control": natures,
                    "company_number": None,
                    "depth": depth,
                })
            elif "corporate-entity" in kind or "legal-entity" in kind:
                # Try to find their CH number
                co_num = item.get("identification", {}).get("registration_number", "")
                place = item.get("identification", {}).get("place_registered", "").lower()
                is_uk = "england" in place or "wales" in place or "uk" in place or "companies house" in place or not place

                node = {
                    "kind": "corporate",
                    "name": name,
                    "company_number": co_num,
                    "natures_of_control": natures,
                    "depth": depth,
                    "place_registered": item.get("identification", {}).get("place_registered", ""),
                    "is_uk": is_uk,
                    "children": [],
                }

                if co_num and is_uk:
                    # Recurse up the tree
                    node["children"] = self.resolve_ubo(co_num, depth + 1, visited, max_depth)
                elif not is_uk or not co_num:
                    node["kind"] = "offshore"

                chain.append(node)

        return chain


# ─────────────────────────────────────────────────────────────────────────────
# ACCOUNTS PDF TEXT EXTRACTION
# ─────────────────────────────────────────────────────────────────────────────
def extract_accounts_text(pdf_bytes):
    """Extract text from accounts PDF using pypdf."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(pdf_bytes))
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text
    except Exception as e:
        return f"[Could not extract text: {e}]"


def parse_financials_from_text(text):
    """
    Parse key financial figures from accounts text using regex patterns.
    Returns a dict of financial data.
    """
    financials = {}

    patterns = {
        "turnover":           r"(?:Turnover|Revenue)\s*[£]?\s*([\d,]+)",
        "gross_profit":       r"Gross\s+(?:profit|surplus)\s*[£]?\s*([\d,]+)",
        "operating_profit":   r"Operating\s+(?:profit|loss)\s*[£]?\s*\(?([\d,]+)\)?",
        "profit_before_tax":  r"Profit\s+(?:before|/\s*\(loss\)\s+before)\s+(?:taxation|tax)\s*[£]?\s*\(?([\d,]+)\)?",
        "profit_after_tax":   r"Profit\s+(?:for|after)\s+(?:the\s+year|tax)\s*[£]?\s*\(?([\d,]+)\)?",
        "total_assets":       r"Total\s+assets\s*[£]?\s*([\d,]+)",
        "net_assets":         r"Net\s+assets\s*[£]?\s*([\d,]+)",
        "total_equity":       r"(?:Total\s+equity|Shareholders['\s]+funds?)\s*[£]?\s*([\d,]+)",
        "cash":               r"Cash\s+(?:and\s+cash\s+equivalents?|at\s+bank)\s*[£]?\s*([\d,]+)",
        "debtors":            r"(?:Trade\s+)?[Dd]ebtors?\s*[£]?\s*([\d,]+)",
        "creditors":          r"(?:Trade\s+)?[Cc]reditors?[^\n]*\s*[£]?\s*([\d,]+)",
        "fixed_assets":       r"(?:Total\s+)?[Ff]ixed\s+assets?\s*[£]?\s*([\d,]+)",
        "current_assets":     r"Total\s+current\s+assets?\s*[£]?\s*([\d,]+)",
        "current_liabilities":r"(?:Creditors|Total\s+current\s+liabilities)[^\n]*due\s+within\s+one\s+year[^\n]*\s*[£]?\s*\(?([\d,]+)\)?",
        "long_term_debt":     r"(?:Creditors|Total)[^\n]*due\s+after\s+(?:more\s+than\s+)?one\s+year[^\n]*\s*[£]?\s*\(?([\d,]+)\)?",
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            val = match.group(1).replace(",", "")
            try:
                financials[key] = int(val)
            except ValueError:
                financials[key] = val

    return financials


def fmt_currency(val):
    """Format integer as £ currency string."""
    if isinstance(val, int):
        if val < 0:
            return f"(£{abs(val):,})"
        return f"£{val:,}"
    return str(val) if val else "—"


# ─────────────────────────────────────────────────────────────────────────────
# AI ANALYSIS (optional — requires Anthropic API key)
# ─────────────────────────────────────────────────────────────────────────────
def ai_analyse_accounts(accounts_text_2, accounts_text_1, company_name, api_key):
    """
    Send accounts text to Claude for intelligent analysis.
    Returns a dict with analysis sections.
    """
    if not api_key or not accounts_text_2:
        return None

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        prompt = f"""You are an experienced commercial finance underwriter at a UK lending business.

I am providing you with the text extracted from the two most recent sets of filed accounts for {company_name}.

MOST RECENT ACCOUNTS:
{accounts_text_2[:6000]}

PREVIOUS YEAR ACCOUNTS:
{accounts_text_1[:4000]}

Please analyse these accounts and provide a structured JSON response with the following fields:

{{
  "most_recent_year": "YYYY",
  "previous_year": "YYYY",
  "pl_summary": {{
    "turnover_current": <integer or null>,
    "turnover_previous": <integer or null>,
    "gross_profit_current": <integer or null>,
    "gross_profit_previous": <integer or null>,
    "gross_margin_current": "<percentage string or null>",
    "operating_profit_current": <integer or null>,
    "operating_profit_previous": <integer or null>,
    "profit_before_tax_current": <integer or null>,
    "profit_before_tax_previous": <integer or null>,
    "ebitda_current": <integer or null>,
    "ebitda_previous": <integer or null>
  }},
  "balance_sheet_summary": {{
    "fixed_assets": <integer or null>,
    "current_assets": <integer or null>,
    "current_liabilities": <integer or null>,
    "long_term_liabilities": <integer or null>,
    "net_assets": <integer or null>,
    "equity": <integer or null>,
    "cash": <integer or null>,
    "debtors": <integer or null>,
    "stock_inventory": <integer or null>
  }},
  "key_ratios": {{
    "current_ratio": "<x.xx>",
    "net_gearing": "<percentage>",
    "interest_cover": "<x.xx or N/A>"
  }},
  "notes_highlights": [
    "<key point from notes to accounts relevant to an underwriter>",
    "<second key point>",
    "<third key point if applicable>"
  ],
  "underwriter_observations": "<2-3 sentence narrative summary of the financial position for an underwriter>",
  "insolvent_balance_sheet": <true or false>,
  "flags": [
    "<any financial red flag or notable risk>",
    "<second flag if applicable>"
  ]
}}

Return ONLY the JSON object, no other text."""

        message = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )

        raw = message.content[0].text.strip()
        raw = re.sub(r"^```json\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        return json.loads(raw)

    except Exception as e:
        print(f"  [AI analysis failed: {e}]")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# CREDIT POLICY CHECKS
# ─────────────────────────────────────────────────────────────────────────────
INELIGIBLE_SICS = {
    "41100", "41201", "41202",  # construction / property development
    "42110", "42120", "42130", "42210", "42220", "42910", "42990",
    "43110", "43120", "43130", "43210", "43220", "43290", "43310",
    "43320", "43330", "43341", "43342", "43390", "43910", "43991", "43999",
    "64110", "64191", "64192", "64201", "64202", "64203", "64204", "64205",
    "64209", "64301", "64302", "64303", "64304", "64305", "64306",
    "64910", "64920", "64991", "64992", "64999",
    "65110", "65120", "65201", "65202", "65300",
    "66110", "66120", "66190", "66210", "66220", "66290", "66300",
    "68100", "68201", "68202", "68209", "68310", "68320",  # property
    "92000",  # gambling
    "47910", "47990",  # some online retail — not ineligible but monitor
}

INELIGIBLE_SIC_KEYWORDS = [
    "gambling", "casino", "betting", "adult", "pornograph",
    "tobacco", "weapon", "ammunition", "palm oil", "oil sand",
    "single use plastic", "forestry", "rubber plantation",
]

def check_credit_policy(company_data, officers_data, charges_data, psc_data):
    """
    Run credit policy checks. Returns list of (status, criterion, finding) tuples.
    status: 'green', 'amber', 'red'
    """
    checks = []
    now = date.today()

    # 1. Incorporation — England & Wales Ltd/Plc
    jurisdiction = company_data.get("jurisdiction", "").lower()
    company_type = company_data.get("type", "").lower()
    if "england" in jurisdiction or "wales" in jurisdiction or jurisdiction == "england-wales":
        if "ltd" in company_type or "plc" in company_type or "private" in company_type:
            checks.append(("green", "Incorporation",
                "Incorporated in England & Wales as a private limited company. ✓ Compliant."))
        else:
            checks.append(("amber", "Incorporation",
                f"Company type is '{company_data.get('type')}' — confirm eligibility as Ltd/Plc."))
    else:
        checks.append(("red", "Incorporation",
            f"Jurisdiction is '{company_data.get('jurisdiction')}' — policy requires England & Wales. Potential ineligibility."))

    # 2. Company status
    status = company_data.get("company_status", "").lower()
    if status == "active":
        checks.append(("green", "Company Status", "Company status is Active. ✓ Compliant."))
    elif status in ("liquidation", "administration", "receivership", "dissolved"):
        checks.append(("red", "Company Status",
            f"Company status is '{status}'. IMMEDIATE DECLINE per credit policy."))
    else:
        checks.append(("amber", "Company Status",
            f"Company status is '{status}' — verify this is acceptable."))

    # 3. Company age — minimum 2 full years
    inc_str = company_data.get("date_of_creation", "")
    if inc_str:
        try:
            inc_date = datetime.strptime(inc_str, "%Y-%m-%d").date()
            age_years = (now - inc_date).days / 365.25
            if age_years >= 2:
                checks.append(("green", "Company Age",
                    f"Incorporated {inc_date.strftime('%d %b %Y')} — {age_years:.1f} years old. ✓ Meets minimum 2-year requirement."))
            else:
                checks.append(("red", "Company Age",
                    f"Incorporated {inc_date.strftime('%d %b %Y')} — only {age_years:.1f} years old. Policy requires minimum 2 full years. INELIGIBLE."))
        except:
            checks.append(("amber", "Company Age", "Could not determine incorporation date — verify manually."))
    else:
        checks.append(("amber", "Company Age", "Incorporation date not available — verify manually."))

    # 4. Statutory filings — accounts overdue?
    accs = company_data.get("accounts", {})
    next_due = accs.get("next_accounts", {}).get("due_on", "")
    overdue = accs.get("next_accounts", {}).get("overdue", False)
    if overdue:
        checks.append(("red", "Accounts Filing",
            f"Accounts are OVERDUE (due {next_due}). Policy requires up-to-date statutory filings."))
    elif next_due:
        checks.append(("green", "Accounts Filing",
            f"Accounts up to date. Next accounts due {next_due}. ✓ Compliant."))
    else:
        checks.append(("amber", "Accounts Filing", "Could not confirm accounts filing status — verify at Companies House."))

    # Confirmation statement overdue?
    cs = company_data.get("confirmation_statement", {})
    cs_overdue = cs.get("overdue", False)
    cs_due = cs.get("next_due", "")
    if cs_overdue:
        checks.append(("red", "Confirmation Statement",
            f"Confirmation statement is OVERDUE (due {cs_due}). Policy requires up-to-date filings."))
    else:
        checks.append(("green", "Confirmation Statement",
            f"Confirmation statement up to date. Next due {cs_due}. ✓ Compliant."))

    # 5. Sector eligibility
    raw_sics = company_data.get("sic_codes", [])
    if raw_sics and isinstance(raw_sics[0], dict):
        sic_codes = [s.get("sic_code", "") for s in raw_sics]
        sic_descs = [s.get("description", "").lower() for s in raw_sics]
    else:
        sic_codes = [str(s) for s in raw_sics]
        sic_descs = []
    ineligible_sic = any(s in INELIGIBLE_SICS for s in sic_codes)
    ineligible_kw  = any(kw in d for kw in INELIGIBLE_SIC_KEYWORDS for d in sic_descs)
    if ineligible_sic or ineligible_kw:
        checks.append(("red", "Sector Eligibility",
            f"SIC code(s) {', '.join(sic_codes)} may fall within an ineligible sector per credit policy (construction, property, financial services, gambling etc). REFER."))
    else:
        checks.append(("green", "Sector Eligibility",
            f"SIC {', '.join(sic_codes)} does not appear in the ineligible sector list. ✓ No ineligibility identified."))

    # 6. Insolvency / CVA (from Companies House — limited view)
    if status in ("liquidation", "administration", "receivership", "voluntary-arrangement"):
        checks.append(("red", "Insolvency / CVA",
            f"INSOLVENCY CONFIRMED AT COMPANIES HOUSE — company status is '{status}'. IMMEDIATE DECLINE per credit policy."))
    else:
        checks.append(("green", "Insolvency / CVA",
            "No insolvency status currently showing at Companies House for this company. "
            "Note: Companies House only reflects formal insolvency proceedings registered with them. "
            "CCJs, personal bankruptcy and some CVAs are NOT visible here. "
            "An Equifax search must be completed on the company and all directors/guarantors "
            "before any credit decision is made."))

    # 7. Director turnover — recent resignations?
    resigned = [o for o in officers_data.get("items", [])
                if o.get("resigned_on") and o.get("officer_role") == "director"]
    recent_resigned = []
    for o in resigned:
        try:
            res_date = datetime.strptime(o["resigned_on"], "%Y-%m-%d").date()
            if (now - res_date).days <= 365:
                recent_resigned.append(o)
        except:
            pass
    if recent_resigned:
        names = ", ".join(o.get("name","") for o in recent_resigned)
        checks.append(("amber", "Director Turnover",
            f"{len(recent_resigned)} director(s) resigned in last 12 months: {names}. Review circumstances."))
    else:
        checks.append(("green", "Director Turnover",
            "No director resignations in the last 12 months. ✓ No concern."))

    # 8. Outstanding charges — security position
    outstanding = [c for c in charges_data.get("items", [])
                   if c.get("status") == "outstanding"]
    n_out = len(outstanding)
    if n_out == 0:
        checks.append(("green", "Existing Charges",
            "No outstanding charges. First-ranking debenture should be available. ✓"))
    elif n_out <= 2:
        chargeholders = ", ".join(
            c.get("persons_entitled", [{}])[0].get("name", "Unknown") if c.get("persons_entitled") else "Unknown"
            for c in outstanding)
        checks.append(("amber", "Existing Charges",
            f"{n_out} outstanding charge(s): {chargeholders}. Monmouth's security position should be assessed."))
    else:
        checks.append(("red", "Existing Charges",
            f"{n_out} outstanding charges registered. Monmouth would rank behind existing chargeholders. "
            "First-ranking debenture unlikely to be available. Full debt schedule required."))

    # 9. PSC confirmed?
    psc_items = psc_data.get("items", [])
    active_psc_items = [p for p in psc_items if not p.get("ceased_on") and not p.get("ceased")]
    if active_psc_items:
        checks.append(("green", "PSC Registered",
            f"{len(active_psc_items)} active PSC(s) registered at Companies House. Verify shareholding percentages match PG requirements (min 10%)."))
    else:
        checks.append(("amber", "PSC Registered",
            "No PSC data returned — verify PSC register directly at Companies House."))

    return checks



# ─────────────────────────────────────────────────────────────────────────────
# OSINT / WEB SEARCH
# ─────────────────────────────────────────────────────────────────────────────
def search_gazette(company_name, company_number):
    """
    Search The Gazette official notices API directly.
    Returns list of relevant notice dicts.
    Free API, no key required.
    """
    import urllib.parse
    findings = []

    # Search by company name
    queries = [
        company_name,
        company_number,
    ]

    for q in queries:
        try:
            params = {
                "term": q,
                "results-page-size": 10,
                "format": "application/json",
            }
            url = "https://api.thegazette.co.uk/gaz2/content?" + urllib.parse.urlencode(params)
            r = requests.get(url, timeout=10, headers={"Accept": "application/json"})
            if r.status_code == 200:
                data = r.json()
                notices = data.get("feed", {}).get("entry", [])
                if isinstance(notices, dict):
                    notices = [notices]
                for notice in notices:
                    title   = notice.get("title", {})
                    title   = title.get("#text", title) if isinstance(title, dict) else str(title)
                    summary = notice.get("summary", {})
                    summary = summary.get("#text", summary) if isinstance(summary, dict) else str(summary)
                    link    = notice.get("id", "")
                    date    = notice.get("published", "")[:10]
                    category = notice.get("category", [{}])
                    if isinstance(category, list):
                        category = category[0].get("@term", "") if category else ""
                    
                    if not title or title == "{}":
                        continue

                    # Check relevance
                    text = (title + " " + summary).lower()
                    co_words = [w for w in company_name.lower().split() if len(w) > 3]
                    relevant = (
                        company_number.lower() in text or
                        sum(1 for w in co_words if w in text) >= max(1, len(co_words) - 1)
                    )

                    if relevant:
                        is_adverse = any(kw in text for kw in [
                            "winding", "liquidat", "insolvenc", "bankrupt",
                            "administrat", "receivership", "struck off", "cva",
                            "voluntary arrangement", "petition"
                        ])
                        findings.append({
                            "category":    "The Gazette (Official Notices)",
                            "title":       title[:120],
                            "snippet":     summary[:300],
                            "link":        link,
                            "source":      "thegazette.co.uk",
                            "date":        date,
                            "confidence":  "high",
                            "conf_symbol": "✓",
                            "is_adverse":  is_adverse,
                        })
        except Exception as e:
            print(f"        Gazette API error: {e}")

    # Deduplicate by title
    seen = set()
    unique = []
    for f in findings:
        if f["title"] not in seen:
            seen.add(f["title"])
            unique.append(f)
    return unique


def run_osint(company_name, company_number, directors, serp_key):
    """
    Run targeted web searches via SerpAPI to surface adverse news,
    financial information and director background relevant to underwriting.
    Returns a list of finding dicts.
    """
    if not serp_key:
        return []

    import urllib.parse

    def serp_search(query, search_type="search"):
        try:
            params = {
                "q": query,
                "api_key": serp_key,
                "num": 5,
                "gl": "uk",
                "hl": "en",
            }
            if search_type == "news":
                params["tbm"] = "nws"
            url = "https://serpapi.com/search?" + urllib.parse.urlencode(params)
            r = requests.get(url, timeout=15)
            r.raise_for_status()
            data = r.json()
            results = data.get("organic_results", []) or data.get("news_results", [])
            return results[:5]
        except Exception as e:
            print(f"        OSINT search failed: {e}")
            return []

    def confidence(result_title, result_snippet, co_name, co_number):
        """Rate confidence that a result relates to the specific company."""
        text = (result_title + " " + result_snippet).lower()
        name_words = [w for w in co_name.lower().split() if len(w) > 3]
        matches = sum(1 for w in name_words if w in text)
        number_match = co_number.lower() in text
        if number_match or matches >= len(name_words):
            return "high", "✓"
        elif matches >= max(1, len(name_words) - 1):
            return "medium", "⚠"
        else:
            return "low", "?"

    def is_relevant(result_title, result_snippet, co_name, co_number):
        """Filter out clearly irrelevant generic results."""
        text = (result_title + " " + result_snippet).lower()
        stopwords = {"limited", "ltd", "the", "and", "for", "with", "from"}
        name_words = [w for w in co_name.lower().split() if len(w) > 3 and w not in stopwords]
        matches = sum(1 for w in name_words if w in text)
        number_match = co_number.lower() in text
        if matches < 1 and not number_match:
            return False
        generic_geo = ["north wales", "blaenau", "ffestiniog", "taj mahal", "unesco", "welsh slate landscape"]
        if any(g in text for g in generic_geo) and not number_match:
            return False
        return True

    findings = []
    co_name_q = f'"{company_name}"'

    searches = [
        (f'{co_name_q} insolvency OR administration OR liquidation OR CVA', "search", "Insolvency / Distress"),
        (f'{co_name_q} fraud OR investigation OR prosecution OR "court judgment"', "search", "Adverse / Legal"),
        (f'{co_name_q} news', "news", "News Coverage"),
        (f'{co_name_q} financial results OR revenue OR profit OR accounts', "search", "Financial Intelligence"),
    ]

    # Add director searches (first 2 directors only)
    for director in directors[:2]:
        name = director.get("name", "").title()
        if name:
            searches.append((
                f'"{name}" director fraud OR disqualified OR insolvency OR investigation',
                "search",
                f"Director: {name}"
            ))

    for query, stype, category in searches:
        print(f"        Searching: {category}...")
        results = serp_search(query, stype)
        for r in results:
            title   = r.get("title", "")
            snippet = r.get("snippet", "") or r.get("description", "")
            link    = r.get("link", "") or r.get("url", "")
            source  = r.get("source", "") or r.get("displayed_link", "")
            date    = r.get("date", "")

            if not title or not snippet:
                continue

            # Filter irrelevant results
            if not is_relevant(title, snippet, company_name, company_number):
                continue

            conf_level, conf_symbol = confidence(title, snippet, company_name, company_number)

            # Skip low confidence results
            if conf_level == "low" and "Director:" not in category:
                continue
            if "Director:" in category and conf_level == "low":
                continue

            findings.append({
                "category":    category,
                "title":       title,
                "snippet":     snippet[:300],
                "link":        link,
                "source":      source,
                "date":        date,
                "confidence":  conf_level,
                "conf_symbol": conf_symbol,
            })

    return findings


def search_iir(director_name, serp_key):
    """
    Search the Individual Insolvency Register for a director.
    Uses SerpAPI to search the government IIR site directly.
    Returns dict with result status and details.
    """
    if not serp_key or not director_name:
        return {"searched": False, "found": False, "details": []}

    import urllib.parse
    try:
        # Search the IIR directly
        query = f'"{director_name}" site:insolvencydirect.bis.gov.uk'
        params = {
            "q": query,
            "api_key": serp_key,
            "num": 5,
            "gl": "uk",
            "hl": "en",
        }
        url = "https://serpapi.com/search?" + urllib.parse.urlencode(params)
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
        results = data.get("organic_results", [])

        details = []
        for res in results:
            title   = res.get("title", "")
            snippet = res.get("snippet", "")
            link    = res.get("link", "")
            text    = (title + " " + snippet).lower()
            name_words = [w for w in director_name.lower().split() if len(w) > 2]
            matches = sum(1 for w in name_words if w in text)
            if matches >= len(name_words) - 1:
                details.append({
                    "title": title,
                    "snippet": snippet[:300],
                    "link": link,
                })
        return {
            "searched": True,
            "found": len(details) > 0,
            "details": details,
        }
    except Exception as e:
        return {"searched": False, "found": False, "details": [], "error": str(e)}


def categorise_findings(findings):
    """Group findings by category and sort adverse ones first."""
    # Strong adverse signals — confirmed negative events
    hard_adverse = [
        "fraud", "investigation", "prosecution", "winding-up", "winding up",
        "compulsory liquidation", "administration order", "cva", "voluntary arrangement",
        "disqualified", "disqualification", "county court judgment", " ccj ",
        "criminal", "arrest", "convicted", "money laundering", "bribery",
        "insolvency petition", "bankruptcy order", "struck off"
    ]
    # Soft signals — generic risk language, not actual adverse events
    soft_only = [
        "liquidation risk", "risk score", "credit score", "credit rating",
        "credit limit", "statistically", "payment trends"
    ]
    for f in findings:
        text = (f["title"] + " " + f["snippet"]).lower()
        has_hard = any(kw in text for kw in hard_adverse)
        has_soft_only = any(kw in text for kw in soft_only) and not has_hard
        f["is_adverse"] = has_hard and not has_soft_only

    return sorted(findings, key=lambda x: (not x["is_adverse"], x["category"]))

# ─────────────────────────────────────────────────────────────────────────────
# PDF DESIGN SYSTEM (same palette as v2)
# ─────────────────────────────────────────────────────────────────────────────
DARK_BLUE  = colors.HexColor("#1B2A4A")
MID_BLUE   = colors.HexColor("#2D5FA6")
LIGHT_BLUE = colors.HexColor("#EAF0FB")
RED        = colors.HexColor("#C0392B")
AMBER      = colors.HexColor("#D4780A")
GREEN      = colors.HexColor("#1A7A3C")
BG_RED     = colors.HexColor("#FDEDEC")
BG_AMBER   = colors.HexColor("#FEF6EC")
BG_GREEN   = colors.HexColor("#EAFAF1")
GREY_LINE  = colors.HexColor("#CCCCCC")
WHITE      = colors.white
TEXT       = colors.HexColor("#1A1A1A")
W, H       = A4
CW         = W - 30 * mm


def sty(name, **kw):
    return ParagraphStyle(name, **{"fontName": "Helvetica", "fontSize": 8.2,
                                    "textColor": TEXT, "leading": 11.5, **kw})

H1    = sty("H1",  fontName="Helvetica-Bold", fontSize=14, textColor=DARK_BLUE, leading=17, spaceAfter=3, spaceBefore=8)
H2    = sty("H2",  fontName="Helvetica-Bold", fontSize=9,  textColor=WHITE, leading=12)
BODY  = sty("BD",  spaceAfter=2)
BOLD  = sty("BLD", fontName="Helvetica-Bold", spaceAfter=2)
LABEL = sty("LB",  fontName="Helvetica-Bold", fontSize=7.5, textColor=DARK_BLUE, leading=10)
SMALL = sty("SM",  fontSize=7.5, leading=10, spaceAfter=1)
FLAG_R = sty("FR", fontName="Helvetica-Bold", fontSize=7.8, textColor=RED,   leading=11, leftIndent=3, spaceAfter=1)
FLAG_A = sty("FA", fontName="Helvetica-Bold", fontSize=7.8, textColor=AMBER, leading=11, leftIndent=3, spaceAfter=1)
FLAG_G = sty("FG", fontName="Helvetica",      fontSize=7.8, textColor=GREEN, leading=11, leftIndent=3, spaceAfter=1)


def sec_hdr(title):
    t = Table([[Paragraph(title, H2)]], colWidths=[CW])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), MID_BLUE),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
    ]))
    return t


def kv_table(rows, c1=55 * mm):
    c2 = CW - c1
    data = [[Paragraph(k, LABEL), Paragraph(str(v), SMALL)] for k, v in rows]
    t = Table(data, colWidths=[c1, c2])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [LIGHT_BLUE, WHITE]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, GREY_LINE),
    ]))
    return t


def data_table(headers, rows):
    ncols = len(headers)
    cw_each = CW / ncols
    hrow = [Paragraph(h, sty("th", fontName="Helvetica-Bold", fontSize=7.5, textColor=WHITE, leading=10))
            for h in headers]
    brows = [[Paragraph(str(c), SMALL) for c in r] for r in rows]
    t = Table([hrow] + brows, colWidths=[cw_each] * ncols)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), DARK_BLUE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [LIGHT_BLUE, WHITE]),
        ("GRID", (0, 0), (-1, -1), 0.3, GREY_LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def flag_box(text, level="red"):
    bg  = {"red": BG_RED,   "amber": BG_AMBER,  "green": BG_GREEN}[level]
    bc  = {"red": RED,      "amber": AMBER,      "green": GREEN}[level]
    st  = {"red": FLAG_R,   "amber": FLAG_A,     "green": FLAG_G}[level]
    pfx = {"red": "⚑ FLAG — ", "amber": "⚠ NOTE — ", "green": "✓ "}[level]
    t = Table([[Paragraph(pfx + text, st)]], colWidths=[CW])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("BOX", (0, 0), (-1, -1), 1, bc),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t


def rag_row(dot_color, label, detail, bg_color):
    import math
    dot_d = Drawing(10, 10)
    dot_d.add(Circle(5, 4, 4, fillColor=dot_color, strokeColor=WHITE, strokeWidth=0.5))
    t = Table(
        [[dot_d, Paragraph(f"<b>{label}</b>", sty("rl", fontName="Helvetica-Bold", fontSize=8, textColor=TEXT, leading=11)),
          Paragraph(detail, SMALL)]],
        colWidths=[8 * mm, 45 * mm, CW - 53 * mm]
    )
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg_color),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, GREY_LINE),
    ]))
    return t


def group_diagram(company_name, company_number, psc_items, group_companies, ubo_chain=None):
    """Build a group structure diagram from PSC and associated company data."""
    dw, dh = CW, 90 * mm
    d = Drawing(dw, dh)

    box_active    = colors.HexColor("#D6E4F7")
    box_applicant = colors.HexColor("#FFF3CD")
    box_individual= colors.HexColor("#F0FFF0")
    box_offshore  = colors.HexColor("#F0E6FF")
    mid_b = MID_BLUE
    appl_c= colors.HexColor("#D4900A")
    ind_c = colors.HexColor("#1A7A3C")
    off_c = colors.HexColor("#7B5EA7")
    grey  = GREY_LINE

    def draw_box(x, y, w, h, lines, sub, fill, stroke, bold=False):
        d.add(Rect(x, y, w, h, fillColor=fill, strokeColor=stroke, strokeWidth=1.2, rx=3, ry=3))
        fn = "Helvetica-Bold" if bold else "Helvetica"
        total_lines = len(lines) + (1 if sub else 0)
        line_h = 8
        start_y = y + h / 2 + (total_lines * line_h / 2) - line_h
        for i, ln in enumerate(lines):
            d.add(String(x + w / 2, start_y - i * line_h, ln,
                         fontName=fn, fontSize=6.5, fillColor=TEXT, textAnchor="middle"))
        if sub:
            d.add(String(x + w / 2, start_y - len(lines) * line_h + 2, sub,
                         fontName="Helvetica", fontSize=5.5,
                         fillColor=colors.HexColor("#555555"), textAnchor="middle"))

    def arrow(x1, y1, x2, y2, col=grey):
        import math
        d.add(Line(x1, y1, x2, y2, strokeColor=col, strokeWidth=0.8))
        angle = math.atan2(y2 - y1, x2 - x1)
        aw = 4
        d.add(Polygon([
            x2, y2,
            x2 - aw * math.cos(angle - 0.4), y2 - aw * math.sin(angle - 0.4),
            x2 - aw * math.cos(angle + 0.4), y2 - aw * math.sin(angle + 0.4),
        ], fillColor=col, strokeColor=col, strokeWidth=0))

    bw, bh = 50 * mm, 10 * mm
    cx = dw / 2
    r1 = dh - 14 * mm
    r2 = dh - 30 * mm
    r3 = dh - 48 * mm
    r4 = dh - 68 * mm

    # Build UBO chain rows from resolved data if available
    def flatten_chain(nodes, result=None):
        if result is None: result = []
        for node in nodes:
            result.append(node)
            if node.get("children"):
                flatten_chain(node["children"], result)
        return result

    flat_chain = flatten_chain(ubo_chain) if ubo_chain else []
    ubo_individuals = [n for n in flat_chain if n.get("kind") == "individual"]
    ubo_corporates  = [n for n in flat_chain if n.get("kind") in ("corporate", "offshore")]

    # Row 1 — UBO individuals (or fallback to PSC register)
    psc_individuals = [p for p in psc_items if "individual" in p.get("kind", "")]
    psc_corporate   = [p for p in psc_items if "corporate" in p.get("kind", "")]

    if ubo_individuals:
        n = min(len(ubo_individuals), 3)
        for i, ubo in enumerate(ubo_individuals[:3]):
            name = ubo.get("name", "Unknown")
            nob  = ubo.get("natures_of_control", [])
            shares = ""
            for nb in nob:
                if "75-to-100" in nb: shares = ">75%"
                elif "50-to-75" in nb: shares = "50-75%"
                elif "25-to-50" in nb: shares = "25-50%"
            x = cx - (n * (bw + 4*mm))/2 + i * (bw + 4*mm)
            draw_box(x, r1, bw, bh, [name[:30]],
                     f"UBO — {shares}" if shares else "UBO (Individual)",
                     box_individual, ind_c, bold=True)
    elif psc_individuals:
        for i, psc in enumerate(psc_individuals[:2]):
            name = psc.get("name", "Unknown PSC")
            nob  = psc.get("natures_of_control", [])
            shares = ""
            for n in nob:
                if "75-to-100" in n: shares = ">75%"
                elif "50-to-75" in n: shares = "50-75%"
                elif "25-to-50" in n: shares = "25-50%"
            x = cx - bw/2 + (i - len(psc_individuals)/2 + 0.5) * (bw + 5*mm)
            draw_box(x, r1, bw, bh, [name[:30]], f"PSC — {shares}"[:40],
                     box_individual, ind_c, bold=True)
    else:
        draw_box(cx - bw/2, r1, bw, bh, ["Beneficial Owner / PSC"],
                 "See PSC register — UBO unconfirmed",
                 box_individual, ind_c, bold=True)

    # Row 2 — Corporate PSC / intermediate holding companies
    corp_nodes = ubo_corporates if ubo_corporates else psc_corporate
    if corp_nodes:
        n = min(len(corp_nodes), 3)
        for i, node in enumerate(corp_nodes[:3]):
            name = node.get("name", "Corporate PSC") if isinstance(node, dict) else node.get("name","")
            co_num_node = node.get("company_number","") if isinstance(node, dict) else ""
            kind = node.get("kind","corporate") if isinstance(node, dict) else "corporate"
            sub = "Offshore Entity" if kind == "offshore" else f"Co. {co_num_node}" if co_num_node else "Corporate PSC"
            fill = box_offshore if kind == "offshore" else box_active
            stroke = off_c if kind == "offshore" else mid_b
            x = cx - (n * (bw + 4*mm))/2 + i * (bw + 4*mm)
            draw_box(x, r2, bw, bh, [name[:28]], sub, fill, stroke)
            arrow(cx, r1, x + bw/2, r2 + bh)

    # Applicant box
    app_row = r3 if corp_nodes else r2
    app_x = cx - bw/2
    draw_box(app_x, app_row, bw + 5*mm, bh,
             [company_name[:32]], f"APPLICANT | Co. {company_number} | Active",
             box_applicant, appl_c, bold=True)

    if corp_nodes:
        arrow(cx, r2, app_x + (bw + 5*mm)/2, app_row + bh)
    else:
        arrow(cx, r1, app_x + (bw + 5*mm)/2, app_row + bh)

    # Row 4 — Group siblings / subsidiaries
    if group_companies:
        n = min(len(group_companies), 5)
        spacing = (dw - 16*mm) / n
        sub_bw = spacing - 3*mm
        for i, gc in enumerate(group_companies[:n]):
            sx = 8*mm + i * spacing
            status_str = gc.get("company_status", "unknown").title()
            draw_box(sx, r4, sub_bw, bh,
                     [gc["company_name"][:22]],
                     f"Co. {gc['company_number']} | {status_str}",
                     box_active if status_str.lower() == "active" else colors.HexColor("#F5F5F5"),
                     mid_b if status_str.lower() == "active" else grey)
            arrow(app_x + (bw + 5*mm) * (0.2 + 0.15*i), app_row,
                  sx + sub_bw/2, r4 + bh)

    # Legend
    ly, lx = 3*mm, 8*mm
    for fill, stroke, lbl in [
        (box_applicant, appl_c, "Applicant"),
        (box_individual, ind_c, "Individual PSC / UBO"),
        (box_active, mid_b, "Active UK company"),
        (box_offshore, off_c, "Offshore entity"),
    ]:
        d.add(Rect(lx, ly, 8, 8, fillColor=fill, strokeColor=stroke, strokeWidth=0.8, rx=1))
        d.add(String(lx + 11, ly + 1, lbl, fontName="Helvetica", fontSize=6, fillColor=TEXT))
        lx += 42*mm

    return d


def header_footer(c, doc):
    c.saveState()
    c.setFillColor(DARK_BLUE)
    c.rect(0, H - 26 * mm, W, 26 * mm, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(15 * mm, H - 14 * mm, "MONMOUTH GROUP")
    c.setFont("Helvetica", 9)
    c.drawString(15 * mm, H - 21 * mm, "Underwriting Summary — Company Review")
    c.setFont("Helvetica", 8)
    c.drawRightString(W - 15 * mm, H - 14 * mm, "CONFIDENTIAL")
    c.drawRightString(W - 15 * mm, H - 21 * mm, f"Generated: {date.today().strftime('%d %B %Y')}")
    c.setFillColor(DARK_BLUE)
    c.rect(0, 0, W, 11 * mm, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica", 7)
    c.drawString(15 * mm, 4 * mm,
        "Internal use only. Sourced from Companies House API (live data). "
        "CCJ/insolvency status must be confirmed via credit bureau search.")
    c.drawRightString(W - 15 * mm, 4 * mm, f"Page {doc.page}")
    c.restoreState()


# ─────────────────────────────────────────────────────────────────────────────
# REPORT BUILDER
# ─────────────────────────────────────────────────────────────────────────────
def build_report(company_number, api_key=CH_API_KEY, anthropic_key=ANTHROPIC_KEY):
    ch = CHClient(api_key)
    sp = lambda n=2: Spacer(1, n * mm)

    print(f"\n{'='*60}")
    print(f"  Monmouth Group — Underwriting Report Generator")
    print(f"{'='*60}")
    print(f"  Company: {company_number}")
    print(f"  API Key: {api_key[:8]}...")
    print()

    # ── Fetch all data ────────────────────────────────────────────────────
    print("  [1/7] Fetching company profile...")
    company = ch.company(company_number)
    company_name = company.get("company_name", "Unknown")
    print(f"        Found: {company_name}")

    print("  [2/7] Fetching officers...")
    officers = ch.officers(company_number)

    print("  [3/7] Fetching PSC register...")
    psc = ch.psc(company_number)

    print("  [4/7] Fetching charges...")
    charges = ch.charges(company_number)

    print("  [5/7] Fetching filing history...")
    filings = ch.filing_history(company_number)

    # Find the two most recent sets of accounts
    account_filings = [f for f in filings.get("items", [])
                       if f.get("category") == "accounts" and "full" in f.get("description", "").lower()]
    # Fall back to any accounts if no "full" found
    if not account_filings:
        account_filings = [f for f in filings.get("items", [])
                           if f.get("category") == "accounts"]

    accounts_text = ["", ""]
    accounts_periods = ["", ""]
    accounts_financials = [{}, {}]
    ai_analysis = None

    print("  [6/7] Downloading accounts PDFs...")
    for i, filing in enumerate(account_filings[:2]):
        doc_id = filing.get("links", {}).get("document_metadata", "")
        # Extract the document ID from the URL if present
        if "/" in doc_id:
            doc_id = doc_id.rstrip("/").split("/")[-1]
        period = filing.get("description", "")
        accounts_periods[i] = period
        print(f"        Accounts {i+1}: {period}")
        if doc_id:
            pdf_bytes = ch.get_document(doc_id)
            if pdf_bytes:
                print(f"        ✓ Downloaded ({len(pdf_bytes):,} bytes)")
                accounts_text[i] = extract_accounts_text(pdf_bytes)
                accounts_financials[i] = parse_financials_from_text(accounts_text[i])
            else:
                print(f"        ✗ Could not download PDF")

    # AI analysis if we have accounts text and an Anthropic key
    if anthropic_key and accounts_text[0]:
        print("  [7/7] Running AI financial analysis...")
        ai_analysis = ai_analyse_accounts(
            accounts_text[0], accounts_text[1], company_name, anthropic_key)
        if ai_analysis:
            print("        ✓ AI analysis complete")
    else:
        print("  [7/7] Skipping AI analysis (no Anthropic key or accounts text)")

    # Resolve UBO chain
    print("  [UBO] Resolving ultimate beneficial ownership chain...")
    ubo_chain = ch.resolve_ubo(company_number)
    if ubo_chain:
        print(f"        Found {len(ubo_chain)} top-level PSC node(s)")
    else:
        print("        No UBO chain resolved")

    # Run credit policy checks
    policy_checks = check_credit_policy(company, officers, charges, psc)

    # ── OSINT searches ────────────────────────────────────────────────────────
    print("  [OSINT] Running web searches...")
    active_dirs_list = [o for o in officers.get("items", []) if not o.get("resigned_on") and o.get("officer_role") == "director"]
    osint_findings = run_osint(company_name, company_number, active_dirs_list, SERP_API_KEY)
    print("        Running Gazette API search...")
    gazette_findings = search_gazette(company_name, company_number)
    print(f"        {len(gazette_findings)} Gazette notice(s) found")
    osint_findings = osint_findings + gazette_findings
    osint_findings = categorise_findings(osint_findings)
    print(f"        {len(osint_findings)} total OSINT findings")

    # ── Fetch officer appointments for associated company check ───────────
    director_appointments = {}
    active_officers = [o for o in officers.get("items", [])
                       if not o.get("resigned_on") and o.get("officer_role") == "director"]
    for officer in active_officers[:2]:  # Check first 2 directors to limit API calls
        officer_id = officer.get("links", {}).get("officer", {}).get("appointments", "")
        if officer_id and "/" in officer_id:
            officer_id = officer_id.strip("/").split("/")[-2]
        if officer_id:
            try:
                appts = ch.officer_appointments(officer_id)
                director_appointments[officer.get("name", "")] = appts.get("items", [])
            except:
                pass

    # ── Director checks: disqualification + IIR ─────────────────────────
    print("  [DIR] Checking director disqualifications and insolvency register...")
    director_checks = {}
    all_active_directors = [o for o in officers.get("items", [])
                            if not o.get("resigned_on") and o.get("officer_role") == "director"]

    def get_officer_id(officer):
        """Extract officer ID from links, trying multiple paths."""
        links = officer.get("links", {})
        # Try appointments link: /officers/{id}/appointments
        appt_link = links.get("officer", {}).get("appointments", "")
        if appt_link and "/" in appt_link:
            parts = appt_link.strip("/").split("/")
            if len(parts) >= 2:
                return parts[-2]
        # Try self link: /officers/{id}
        self_link = links.get("self", "")
        if self_link and "/" in self_link:
            return self_link.strip("/").split("/")[-1]
        return ""

    def check_person(name, officer_id):
        """Run disqualification and IIR checks for a person."""
        disq_result = None
        if officer_id:
            disq_result = ch.check_disqualification(officer_id)
        iir_result = search_iir(name, SERP_API_KEY)
        disq_status = "DISQUALIFIED" if (disq_result and disq_result.get("disqualifications")) else ("error" if disq_result is None else "clear")
        iir_status = "FOUND" if iir_result.get("found") else ("not searched" if not iir_result.get("searched") else "clear")
        print(f"        {name}: disqualification={disq_status}, IIR={iir_status}")
        return {"disqualification": disq_result, "iir": iir_result, "role": "Director"}

    for officer in all_active_directors:
        name = officer.get("name", "").title()
        officer_id = get_officer_id(officer)
        director_checks[name] = check_person(name, officer_id)

    # ── PSC checks — run on individual PSCs who are not already directors ──
    psc_names_checked = set(director_checks.keys())
    active_pscs_list = [p for p in psc.get("items", []) if not p.get("ceased_on") and not p.get("ceased")]
    for p in active_pscs_list:
        if "individual" not in p.get("kind", ""):
            continue
        psc_name = p.get("name", "").title()
        if psc_name in psc_names_checked:
            continue
        print(f"        Checking PSC: {psc_name}")
        # PSCs don't have officer links so we search by name only
        iir_result = search_iir(psc_name, SERP_API_KEY)
        # Try disqualification search by name via CH search
        disq_result = None
        try:
            search_res = ch.get("/search/disqualified-officers", params={"q": psc_name, "items_per_page": 5})
            items = search_res.get("items", [])
            # Check for strong name match
            for item in items:
                if item.get("name", "").lower() == psc_name.lower():
                    officer_id = item.get("links", {}).get("self", "").strip("/").split("/")[-1]
                    if officer_id:
                        disq_result = ch.check_disqualification(officer_id)
                    break
            if disq_result is None:
                disq_result = {"disqualifications": []} if items else None
        except Exception as e:
            print(f"        PSC disq search error: {e}")
        
        director_checks[psc_name] = {
            "disqualification": disq_result,
            "iir": iir_result,
            "role": "PSC",
        }
        psc_names_checked.add(psc_name)

    # ── Build PDF ─────────────────────────────────────────────────────────
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    safe_name = re.sub(r"[^\w\s-]", "", company_name).strip().replace(" ", "_")
    output_path = os.path.join(OUTPUT_DIR, f"{safe_name}_{date.today().isoformat()}.pdf")

    doc = SimpleDocTemplate(output_path, pagesize=A4,
        topMargin=33*mm, bottomMargin=16*mm, leftMargin=15*mm, rightMargin=15*mm)
    story = []

    # ── Banner ────────────────────────────────────────────────────────────
    story.append(sp(3))
    banner = Table([[
        Paragraph(company_name, sty("bn", fontName="Helvetica-Bold", fontSize=13, textColor=DARK_BLUE, leading=16)),
        Paragraph(f"Co. No. {company_number}",
                  sty("bn2", fontName="Helvetica", fontSize=9, textColor=MID_BLUE, leading=12, alignment=TA_RIGHT))
    ]], colWidths=[130 * mm, CW - 130 * mm])
    banner.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("LINEBELOW", (0, 0), (-1, 0), 2, MID_BLUE),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
    ]))
    story.append(banner)
    story.append(sp(3))

    # ── SECTION 1 — Company Information ──────────────────────────────────
    story.append(sec_hdr("1 — COMPANY INFORMATION"))
    story.append(sp(1.5))

    raw_sics = company.get("sic_codes", [])
    sic_str = "  |  ".join(str(s) for s in raw_sics) if raw_sics else "—" 

    reg_addr = company.get("registered_office_address", {})
    addr_parts = [reg_addr.get(k, "") for k in
                  ["address_line_1","address_line_2","locality","region","postal_code","country"]
                  if reg_addr.get(k)]
    addr_str = ", ".join(addr_parts)

    accs_info = company.get("accounts", {})
    last_acc  = accs_info.get("last_accounts", {})
    next_acc  = accs_info.get("next_accounts", {})
    cs_info   = company.get("confirmation_statement", {})

    inc_str = company.get("date_of_creation", "")
    age_str = ""
    if inc_str:
        try:
            inc_date = datetime.strptime(inc_str, "%Y-%m-%d").date()
            age_years = (date.today() - inc_date).days / 365.25
            age_str = f"  |  Age: {age_years:.1f} years"
        except:
            pass

    story.append(kv_table([
        ("Registered Name",    company_name),
        ("Company Number",     company_number),
        ("Registered Address", addr_str or "—"),
        ("Company Status",     company.get("company_status", "—").title()),
        ("Company Type",       company.get("type", "—").replace("-", " ").title()),
        ("Incorporated",       f"{inc_str}{age_str}"),
        ("SIC Code(s)",        sic_str),
        ("Last Accounts",      f"{last_acc.get('made_up_to','')} ({last_acc.get('type','').upper()})"),
        ("Next Accounts Due",  f"{next_acc.get('due_on','')}  {'⚠ OVERDUE' if next_acc.get('overdue') else ''}"),
        ("Confirmation Stmt",  f"Last: {cs_info.get('last_made_up_to','')}  |  Next due: {cs_info.get('next_due','')}  "
                               f"{'⚠ OVERDUE' if cs_info.get('overdue') else ''}"),
    ]))
    story.append(sp(3))

    # ── SECTION 2 — Directors ─────────────────────────────────────────────
    story.append(sec_hdr("2 — DIRECTORS & OFFICERS"))
    story.append(sp(1.5))

    all_officers = officers.get("items", [])
    active_dirs = [o for o in all_officers if not o.get("resigned_on")]
    resigned_dirs = [o for o in all_officers if o.get("resigned_on")]

    story.append(Paragraph(
        f"Active Officers: {len(active_dirs)}  |  Resigned: {len(resigned_dirs)}", BOLD))
    story.append(sp(1))

    def fmt_dob(dob):
        if not dob: return "—"
        return f"{dob.get('month','')}/{dob.get('year','')}"

    active_rows = []
    for o in active_dirs:
        active_rows.append([
            o.get("name", "—").title(),
            o.get("officer_role", "—").replace("-", " ").title(),
            fmt_dob(o.get("date_of_birth")),
            o.get("appointed_on", "—"),
            o.get("nationality", "—"),
        ])
    if active_rows:
        story.append(data_table(["Name", "Role", "DOB (m/y)", "Appointed", "Nationality"], active_rows))

    if resigned_dirs:
        story.append(sp(2))
        story.append(Paragraph("Previous Directors:", BOLD))
        story.append(sp(1))
        res_rows = [[
            o.get("name", "—").title(),
            o.get("officer_role", "—").replace("-", " ").title(),
            o.get("appointed_on", "—"),
            o.get("resigned_on", "—"),
        ] for o in resigned_dirs]
        story.append(data_table(["Name", "Role", "Appointed", "Resigned"], res_rows))

    story.append(sp(3))

    # ── SECTION 3 — PSC ───────────────────────────────────────────────────
    story.append(sec_hdr("3 — PERSONS WITH SIGNIFICANT CONTROL (PSC)"))
    story.append(sp(1.5))

    psc_items = psc.get("items", [])
    active_pscs  = [p for p in psc_items if not p.get("ceased_on") and not p.get("ceased")]
    ceased_pscs  = [p for p in psc_items if p.get("ceased_on") or p.get("ceased")]

    def psc_row(p):
        kind = p.get("kind", "")
        nats = ", ".join(p.get("natures_of_control", []))
        shares = ""
        for n in p.get("natures_of_control", []):
            if "75-to-100" in n: shares = ">75%"
            elif "50-to-75" in n: shares = "50-75%"
            elif "25-to-50" in n: shares = "25-50%"
        if "individual" in kind:
            return [p.get("name", "—").title(), "Individual",
                    fmt_dob(p.get("date_of_birth")),
                    p.get("nationality", "—"), shares or nats[:40]]
        elif "corporate" in kind:
            return [p.get("name", "—").title(), "Corporate Entity", "—", "—", shares or nats[:40]]
        else:
            return [p.get("name", "—"), kind, "—", "—", "—"]

    if active_pscs:
        story.append(data_table(
            ["Name", "Type", "DOB (m/y)", "Nationality", "Nature of Control"],
            [psc_row(p) for p in active_pscs]
        ))
    else:
        story.append(flag_box("No active PSCs registered. Verify PSC register at Companies House.", "amber"))

    if ceased_pscs:
        story.append(sp(1.5))
        story.append(Paragraph("Previous / Ceased PSCs", BOLD))
        story.append(sp(0.5))
        ceased_rows = []
        for p in ceased_pscs:
            row = psc_row(p)
            row.append(str(p.get("ceased_on", "ceased")))
            ceased_rows.append(row)
        story.append(data_table(
            ["Name", "Type", "DOB (m/y)", "Nationality", "Nature of Control", "Ceased"],
            ceased_rows
        ))
    
    if not psc_items:
        story.append(flag_box("No PSC data returned from API — verify PSC register at Companies House.", "amber"))

    story.append(sp(3))

    # ── SECTION 3B — Director & PSC Checks ───────────────────────────────
    story.append(sec_hdr("3B — DIRECTOR & PSC CHECKS (DISQUALIFICATION & INSOLVENCY)"))
    story.append(sp(1.5))
    story.append(flag_box(
        "Disqualification data sourced from Companies House register (live). "
        "Individual Insolvency Register (IIR) covers bankruptcy, IVAs and Debt Relief Orders. "
        "All findings must be manually verified.",
        "amber"
    ))
    story.append(sp(2))

    if director_checks:
        for dir_name, checks_data in director_checks.items():
            role = checks_data.get("role", "Director")
            story.append(Paragraph(f"{dir_name} ({role})", BOLD))
            story.append(sp(1))

            disq = checks_data.get("disqualification")
            if disq and disq.get("disqualifications"):
                disq_list = disq["disqualifications"]
                story.append(flag_box(
                    f"DISQUALIFIED — {len(disq_list)} disqualification(s) on Companies House register. "
                    "This person is prohibited from acting as a director.",
                    "red"
                ))
                story.append(sp(1))
                disq_rows = []
                for d in disq_list:
                    disq_rows.append([
                        d.get("disqualification_type", "—").replace("-", " ").title(),
                        d.get("disqualified_from", "—"),
                        d.get("disqualified_until", "—"),
                        d.get("court_name", "—"),
                        ", ".join(d.get("company_names", []))[:40] or "—",
                    ])
                story.append(data_table(
                    ["Type", "From", "Until", "Court", "Associated Companies"],
                    disq_rows
                ))
            elif disq is not None and "disqualifications" in disq:
                story.append(flag_box(
                    f"No disqualification found for {dir_name} on Companies House register. ✓",
                    "green"
                ))
            else:
                story.append(flag_box(
                    f"Could not retrieve disqualification data for {dir_name} — verify manually at Companies House.",
                    "amber"
                ))

            story.append(sp(1))

            iir = checks_data.get("iir", {})
            if not iir.get("searched"):
                story.append(flag_box(
                    f"IIR search not completed for {dir_name}. Check manually at insolvencydirect.bis.gov.uk",
                    "amber"
                ))
            elif iir.get("found"):
                story.append(flag_box(
                    f"POSSIBLE MATCH on Individual Insolvency Register for {dir_name}. "
                    "Verify manually — covers bankruptcy, IVAs and Debt Relief Orders.",
                    "red"
                ))
                for detail in iir.get("details", []):
                    text = (
                        f"<b>{detail['title']}</b><br/>"
                        f"{detail['snippet']}<br/>"
                        f"<font color='#2D5FA6'><u>{detail['link'][:80]}</u></font>"
                    )
                    t = Table([[Paragraph(text, sty("iir", fontSize=7.5, leading=11))]],
                              colWidths=[CW])
                    t.setStyle(TableStyle([
                        ("BACKGROUND", (0,0), (-1,-1), BG_RED),
                        ("LINEBEFORE", (0,0), (0,-1), 3, RED),
                        ("TOPPADDING", (0,0), (-1,-1), 5),
                        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
                        ("LEFTPADDING", (0,0), (-1,-1), 8),
                        ("RIGHTPADDING", (0,0), (-1,-1), 6),
                    ]))
                    story.append(t)
            else:
                story.append(flag_box(
                    f"No records found for {dir_name} on the Individual Insolvency Register. ✓",
                    "green"
                ))
            story.append(sp(2))
    else:
        story.append(flag_box(
            "No director check data available — verify disqualification and insolvency status manually.",
            "amber"
        ))

    story.append(sp(3))

    # ── SECTION 4 — Associated Directorships ─────────────────────────────
    story.append(sec_hdr("4 — ASSOCIATED DIRECTORSHIPS"))
    story.append(sp(1.5))

    if director_appointments:
        for director_name, appts in director_appointments.items():
            story.append(Paragraph(f"{director_name.title()} — {len(appts)} appointment(s) on record:", BOLD))
            story.append(sp(1))
            appt_rows = []
            liquidations = []
            for a in appts:
                co_name   = a.get("appointed_to", {}).get("company_name", "—")
                co_number = a.get("appointed_to", {}).get("company_number", "—")
                co_status = a.get("appointed_to", {}).get("company_status", "—").title()
                role      = a.get("officer_role", "—").replace("-", " ").title()
                appt_date = a.get("appointed_on", "—")
                res_date  = a.get("resigned_on", "—")
                appt_rows.append([co_name[:35], co_number, co_status, role, appt_date, res_date])
                if co_status.lower() in ("liquidation", "administration", "receivership"):
                    liquidations.append(co_name)
            story.append(data_table(
                ["Company", "Co. No.", "Status", "Role", "Appointed", "Resigned"],
                appt_rows[:20]  # cap at 20 rows
            ))
            if liquidations:
                story.append(sp(1))
                story.append(flag_box(
                    f"Director {director_name.title()} has been associated with the following "
                    f"companies currently in insolvency proceedings: {', '.join(liquidations)}. "
                    "Underwriter must review circumstances.", "red"))
            story.append(sp(2))
    else:
        story.append(Paragraph("Director appointment data not retrieved — check Companies House manually.", SMALL))

    story.append(PageBreak())

    # ── SECTION 5 — Group Structure ───────────────────────────────────────
    story.append(sec_hdr("5 — CORPORATE GROUP STRUCTURE"))
    story.append(sp(2))

    # Build group companies list from director appointments
    group_companies = []
    if director_appointments:
        seen = set()
        for appts in director_appointments.values():
            for a in appts:
                co_num = a.get("appointed_to", {}).get("company_number", "")
                co_name = a.get("appointed_to", {}).get("company_name", "")
                co_status = a.get("appointed_to", {}).get("company_status", "")
                if co_num and co_num != company_number and co_num not in seen:
                    seen.add(co_num)
                    group_companies.append({
                        "company_number": co_num,
                        "company_name": co_name,
                        "company_status": co_status,
                    })

    # Filter to active PSCs only for diagram
    psc_items_active = [p for p in psc.get("items", []) if not p.get("ceased_on") and not p.get("ceased")]
    story.append(group_diagram(company_name, company_number, psc_items_active, group_companies[:6], ubo_chain))
    story.append(sp(2))
    story.append(Paragraph(
        "Note: Diagram based on live Companies House PSC register and director appointment data. "
        "Shareholding percentages shown are as filed. Formal confirmation of group structure "
        "should be obtained from the applicant.", SMALL))
    story.append(sp(3))

    # ── SECTION 6 — Charges ───────────────────────────────────────────────
    story.append(sec_hdr("6 — CHARGES REGISTER"))
    story.append(sp(1.5))

    charge_items = charges.get("items", [])
    outstanding_charges = [c for c in charge_items if c.get("status") == "outstanding"]
    satisfied_charges   = [c for c in charge_items if c.get("status") != "outstanding"]

    story.append(Paragraph(
        f"{len(outstanding_charges)} outstanding  |  {len(satisfied_charges)} satisfied  |  "
        f"{charges.get('total_count', len(charge_items))} total", BOLD))
    story.append(sp(1))

    charge_rows = []
    for c in charge_items:
        entitled = c.get("persons_entitled", [])
        chargeholder = entitled[0].get("name", "—") if entitled else "—"
        created  = c.get("created_on", "—")
        delivered = c.get("delivered_on", "—")
        status   = c.get("status", "—").upper()
        satisfied_on = c.get("satisfied_on", "")
        status_str = f"{status}" + (f" {satisfied_on}" if satisfied_on else "")
        charge_rows.append([chargeholder[:40], created, delivered, status_str])

    if charge_rows:
        story.append(data_table(["Chargeholder", "Created", "Delivered", "Status"], charge_rows))

    story.append(sp(1.5))
    if len(outstanding_charges) == 0:
        story.append(flag_box("No outstanding charges. First-ranking debenture should be achievable. ✓", "green"))
    elif len(outstanding_charges) <= 2:
        story.append(flag_box(
            f"{len(outstanding_charges)} outstanding charge(s). Monmouth's security position should be "
            "assessed against existing chargeholders.", "amber"))
    else:
        # Check for recent registrations
        recent = []
        one_year_ago = date.today().replace(year=date.today().year - 1)
        for c in outstanding_charges:
            try:
                cd = datetime.strptime(c.get("created_on",""), "%Y-%m-%d").date()
                if cd >= one_year_ago:
                    recent.append(c)
            except:
                pass
        recent_note = f" {len(recent)} of these were registered in the last 12 months." if recent else ""
        story.append(flag_box(
            f"{len(outstanding_charges)} outstanding charges.{recent_note} Monmouth would rank behind "
            "all existing chargeholders. First-ranking debenture is unlikely to be available without "
            "consent from existing charge holders. Full debt schedule required from applicant.", "red"))

    story.append(sp(3))

    # ── SECTION 7 — Credit Policy Compliance ─────────────────────────────
    story.append(sec_hdr("7 — CREDIT POLICY COMPLIANCE"))
    story.append(sp(1.5))

    # Header row
    hdr_row = Table([[
        Paragraph("", LABEL),
        Paragraph("Policy Criterion", LABEL),
        Paragraph("Finding", LABEL),
    ]], colWidths=[8*mm, 45*mm, CW - 53*mm])
    hdr_row.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT_BLUE),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, GREY_LINE),
    ]))
    story.append(hdr_row)

    for status, criterion, finding in policy_checks:
        dot_col = GREEN if status == "green" else (AMBER if status == "amber" else RED)
        bg      = BG_GREEN if status == "green" else (BG_AMBER if status == "amber" else BG_RED)
        story.append(rag_row(dot_col, criterion, finding, bg))

    story.append(sp(3))

    # Financials section removed — reviewer to obtain accounts directly from Companies House

    # ── SECTION 9 — OSINT ────────────────────────────────────────────────────
    # ── Helper to render a finding row ──────────────────────────────────────
    def render_finding(finding):
        conf     = finding["conf_symbol"]
        is_adv   = finding["is_adverse"]
        title    = finding["title"][:100]
        snippet  = finding["snippet"][:250]
        source   = finding.get("source","")
        date_str = finding.get("date","")
        link     = finding.get("link","")
        level    = "red" if (is_adv and finding["confidence"] == "high") else                    "amber" if is_adv else "green"
        date_part   = f"  ·  {date_str}" if date_str else ""
        source_part = f"  ·  {source}" if source else ""
        text = (
            f"<b>{conf} {title}</b>{date_part}{source_part}<br/>"
            f"{snippet}<br/>"
            f"<font color='#2D5FA6'><u>{link[:80]}</u></font>"
        )
        t = Table([[Paragraph(text, sty("osint", fontSize=7.5, leading=11, spaceAfter=1))]],
                  colWidths=[CW])
        bc = RED if level == "red" else (AMBER if level == "amber" else GREEN)
        bg = BG_RED if level == "red" else (BG_AMBER if level == "amber" else BG_GREEN)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), bg),
            ("LINEBELOW", (0,0), (-1,-1), 0.5, GREY_LINE),
            ("LINEBEFORE", (0,0), (0,-1), 3, bc),
            ("TOPPADDING", (0,0), (-1,-1), 5),
            ("BOTTOMPADDING", (0,0), (-1,-1), 5),
            ("LEFTPADDING", (0,0), (-1,-1), 8),
            ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ]))
        return t

    # ── SECTION 8A — The Gazette ──────────────────────────────────────────
    story.append(sec_hdr("8 — THE GAZETTE (OFFICIAL NOTICES)"))
    story.append(sp(1.5))
    gazette_only = [f for f in osint_findings if f.get("category") == "The Gazette (Official Notices)"]
    gazette_adverse = [f for f in gazette_only if f["is_adverse"]]

    if gazette_adverse:
        story.append(flag_box(
            f"OFFICIAL NOTICE(S) FOUND — {len(gazette_adverse)} adverse notice(s) identified in The Gazette. "
            "These are official UK government records. Review immediately.",
            "red"
        ))
    elif gazette_only:
        story.append(flag_box(
            f"{len(gazette_only)} Gazette notice(s) found for this company. None identified as adverse. "
            "Review notices below to confirm.", "amber"
        ))
    else:
        story.append(flag_box(
            "No notices found in The Gazette for this company or registration number. "
            "No winding-up petitions, insolvency orders, CVAs or struck-off notices identified "
            "in the official UK Government register. ✓", "green"
        ))

    if gazette_only:
        story.append(sp(1.5))
        for finding in gazette_only:
            story.append(render_finding(finding))
    story.append(sp(3))

    # ── SECTION 8B — Open Source Intelligence ────────────────────────────
    story.append(sec_hdr("9 — OPEN SOURCE INTELLIGENCE (OSINT)"))
    story.append(sp(1.5))
    story.append(flag_box(
        "Results sourced from Google (SerpAPI). All findings must be manually verified. "
        "Confidence: ✓ High — strong name/number match;  ⚠ Medium — verify same entity.",
        "amber"
    ))
    story.append(sp(2))

    web_findings = [f for f in osint_findings if f.get("category") != "The Gazette (Official Notices)"]

    if web_findings:
        adverse_high = [f for f in web_findings if f["is_adverse"] and f["confidence"] == "high"]
        adverse_med  = [f for f in web_findings if f["is_adverse"] and f["confidence"] == "medium"]
        total = len(web_findings)

        if adverse_high:
            story.append(flag_box(
                f"ADVERSE FINDINGS — {len(adverse_high)} high-confidence adverse result(s) identified. "
                f"Total results reviewed: {total}. See flagged items below.",
                "red"
            ))
        elif adverse_med:
            story.append(flag_box(
                f"{len(adverse_med)} possible adverse result(s) — medium confidence, verify same entity. "
                f"Total results: {total}.",
                "amber"
            ))
        else:
            story.append(flag_box(
                f"No adverse findings across {total} result(s). No significant negative news, "
                "legal proceedings or financial distress signals identified. "
                "Manual verification still recommended. ✓",
                "green"
            ))
        story.append(sp(2))

        from itertools import groupby
        web_sorted = sorted(web_findings, key=lambda x: (not x["is_adverse"], x["category"]))
        web_by_cat = sorted(web_sorted, key=lambda x: x["category"])
        for cat, group in groupby(web_by_cat, key=lambda x: x["category"]):
            group_list = list(group)
            story.append(Paragraph(cat, BOLD))
            story.append(sp(1))
            for finding in group_list:
                story.append(render_finding(finding))
            story.append(sp(2))
    else:
        story.append(flag_box(
            "No web search results returned. Check SerpAPI connection.", "amber"
        ))

    story.append(PageBreak())

    # ── SECTION 10 — Summary ───────────────────────────────────────────────
    story.append(sec_hdr("10 — REVIEWER SUMMARY"))


    story.append(sp(1.5))

    # Auto-generate summary based on checks
    red_items   = [c for c in policy_checks if c[0] == "red"]
    amber_items = [c for c in policy_checks if c[0] == "amber"]
    green_items = [c for c in policy_checks if c[0] == "green"]

    summary_lines = [
        f"<b>Policy check results:</b> {len(green_items)} green  |  "
        f"{len(amber_items)} amber  |  {len(red_items)} red<br/><br/>",
    ]

    if red_items:
        summary_lines.append("<b>Items requiring immediate attention (RED):</b><br/>")
        for _, crit, finding in red_items:
            short = finding[:120] + "..." if len(finding) > 120 else finding
            summary_lines.append(f"• <b>{crit}:</b> {short}<br/>")
        summary_lines.append("<br/>")

    if amber_items:
        summary_lines.append("<b>Items requiring verification before approval (AMBER):</b><br/>")
        for _, crit, _ in amber_items:
            summary_lines.append(f"• {crit}<br/>")
        summary_lines.append("<br/>")

    summary_lines.append(
        "<b>Mandatory pre-approval steps (all applications):</b><br/>"
        "① Equifax search on company and all directors/guarantors to confirm no CCJ, CVA or insolvency — "
        "this CANNOT be confirmed from Companies House alone.<br/>"
        "② Minimum 6 months bank statements.<br/>"
        "③ Full schedule of existing debt obligations and monthly repayments.<br/>"
        "④ Personal statement of assets and liabilities from all PG providers.<br/>"
        "⑤ Confirm PSC shareholdings meet PG threshold (minimum 10%).<br/>"
    )

    summary_text = "".join(summary_lines)
    sum_t = Table([[Paragraph(summary_text,
                              sty("sb", fontName="Helvetica", fontSize=8, textColor=TEXT, leading=12))]],
                  colWidths=[CW])
    sum_t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BLUE),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("BOX", (0, 0), (-1, -1), 1, MID_BLUE),
    ]))
    story.append(sum_t)

    # ── Build PDF ─────────────────────────────────────────────────────────
    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
    print(f"\n  ✓ Report saved to: {output_path}\n")
    return output_path


def _movement(current, previous):
    """Calculate movement string between two values."""
    if current is None or previous is None:
        return "—"
    try:
        diff = int(current) - int(previous)
        pct  = (diff / abs(int(previous))) * 100 if previous != 0 else 0
        sign = "+" if diff >= 0 else ""
        return f"{sign}{pct:.1f}%"
    except:
        return "—"


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Monmouth Group — Underwriting Report Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Examples:
          python ch_report.py "Spanish Slate Quarries UK Limited"
          python ch_report.py --number 08584514
          python ch_report.py --number 08584514 --anthropic-key sk-ant-...
          
        Environment variables:
          CH_API_KEY        Companies House API key
          ANTHROPIC_API_KEY Anthropic API key (optional, enables AI financial analysis)
        """)
    )
    parser.add_argument("company", nargs="?", help="Company name to search for")
    parser.add_argument("--number", "-n", help="Companies House company number (skips search)")
    parser.add_argument("--api-key", "-k", help="Companies House API key", default=CH_API_KEY)
    parser.add_argument("--anthropic-key", "-a", help="Anthropic API key for AI analysis",
                        default=ANTHROPIC_KEY)
    args = parser.parse_args()

    if not args.company and not args.number:
        parser.print_help()
        sys.exit(1)

    ch = CHClient(args.api_key)

    # Resolve company number from name if needed
    if args.number:
        company_number = args.number.zfill(8)
    else:
        print(f"\nSearching for: {args.company}")
        results = ch.search(args.company)
        items = results.get("items", [])
        if not items:
            print("No companies found.")
            sys.exit(1)
        print(f"\nFound {len(items)} result(s):")
        for i, item in enumerate(items[:5]):
            print(f"  [{i+1}] {item.get('title','?')}  |  {item.get('company_number','?')}  |  "
                  f"{item.get('company_status','?')}")
        if len(items) == 1:
            company_number = items[0]["company_number"]
        else:
            choice = input("\nSelect [1-5] or enter company number directly: ").strip()
            try:
                idx = int(choice) - 1
                company_number = items[idx]["company_number"]
            except:
                company_number = choice.zfill(8)

    build_report(company_number, api_key=args.api_key, anthropic_key=args.anthropic_key)


if __name__ == "__main__":
    main()
