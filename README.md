# monmouth-underwriting

Monmouth Group underwriting report tool

## Tools

### 1. Company Underwriting Report
Search Companies House by name or number. Generates a full PDF underwriting summary.

### 2. Bank Statement Analysis *(NEW)*
Upload Barclays PDF bank statements. AI-powered parsing, reconciliation, credit analytics, and HTML report generation.

## Setup

### Streamlit Secrets
Add these in Streamlit Community Cloud → Settings → Secrets:

```toml
CH_API_KEY = "your-companies-house-api-key"
ANTHROPIC_API_KEY = "sk-ant-your-anthropic-key"
```

### Local Development
```bash
pip install -r requirements.txt
streamlit run app.py
```

## File Structure
```
├── app.py                        # Landing page / navigation
├── ch_report.py                  # Companies House report builder
├── pages/
│   ├── 1_Company_Report.py       # CH search + report generation
│   └── 2_Bank_Analysis.py        # Bank statement analysis tool
├── core/
│   ├── __init__.py
│   ├── pdf_intake.py             # PDF quality check + text extraction
│   ├── parser.py                 # Claude API structured parser
│   ├── validator.py              # Reconciliation + sufficiency checks
│   ├── analytics.py              # Credit analysis engine
│   └── report_builder.py         # HTML report generator
├── Monmouth_Logo_Navy_RGB.png
├── requirements.txt
└── README.md
```
