"""
Bank statement parser — sends PDF text to Claude API for structured extraction.
When used from the Streamlit app, the API client is created in the page, not here.
This module exposes PARSE_PROMPT for use by the Streamlit page and provides
parse_statement() for standalone/CLI usage.
"""

import json
import os

PARSE_PROMPT = """You are a bank statement parser. Extract every transaction from the bank statement text below and return them as a JSON array.

Each transaction must have these exact fields:
- date: string in DD/MM/YY format
- description: string (full transaction description as it appears)
- money_out: number (0 if no outgoing amount)
- money_in: number (0 if no incoming amount)  
- balance: number (running balance after transaction, 0 if not shown)

Also extract the statement metadata:
- account_name: string
- account_number: string
- sort_code: string
- statement_start: string (DD/MM/YY)
- statement_end: string (DD/MM/YY)
- opening_balance: number
- closing_balance: number

Return a single JSON object with two keys:
- "metadata": the statement metadata object
- "transactions": array of transaction objects

Rules:
- Include every transaction, do not skip any
- Do not include the opening balance line as a transaction
- Money values must be numbers, not strings (no £ signs)
- If a value is missing or unclear, use 0
- Return only valid JSON, no explanation, no markdown, no code blocks

Bank statement text:
{text}"""


def parse_statement(text, filename='unknown', api_key=None):
    """
    Send extracted PDF text to Claude API and get back structured transactions.
    Returns a dict with metadata and transactions list.
    """
    import anthropic

    if api_key:
        client = anthropic.Anthropic(api_key=api_key)
    else:
        client = anthropic.Anthropic()

    prompt = PARSE_PROMPT.format(text=text)

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=16000,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text.strip()

    # Strip markdown code blocks if Claude added them despite instructions
    if raw.startswith('```'):
        raw = raw.split('```')[1]
        if raw.startswith('json'):
            raw = raw[4:]
    raw = raw.strip()

    try:
        parsed = json.loads(raw)
        return parsed
    except json.JSONDecodeError as e:
        print(f'  JSON parse error for {filename}: {e}')
        return None
