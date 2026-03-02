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

CRITICAL RULES:
- Include EVERY transaction, do not skip any
- Do NOT include "BROUGHT FORWARD" lines as transactions — these appear at the top of each page and are NOT transactions
- Do NOT include the opening balance line as a transaction
- Money values must be numbers, not strings (no £ signs)
- If a value is missing or unclear, use 0

COLUMN TAGS: Some bank statements have amounts prefixed with [IN] or [OUT] tags
(e.g. '[IN]£500.00' or '[OUT]£200.00'). If these tags are present, use them to determine
money_in vs money_out: [IN] means money_in, [OUT] means money_out. Any untagged £ amount
on the same line is the end-of-day balance. If no [IN]/[OUT] tags are present, determine
money_in vs money_out from the column position as normal.

REFUNDS: Some transactions show a credit/refund on a line that would normally be a debit.
Look for the word "REFUND" in the description. If a card transaction or similar has "REFUND"
in its description, it is money_in (credit), NOT money_out.

FOREIGN CURRENCY TRANSACTIONS: Some transactions show a foreign amount, exchange rate, and
a non-sterling transaction fee. For example:
  "WINCHER ORDER 367241 STOCKHOLM SE EUR 89.00 VRATE 1.1323 N-S TRN FEE 2.16"
with an amount of 80.76. The actual GBP amount charged/credited is what appears in the
Withdrawn or Paid In column — use THAT number (e.g. 80.76), not the foreign currency amount.

MULTI-LINE DESCRIPTIONS: Transaction descriptions may span multiple lines. A continuation
line belongs to the SAME transaction as the line above it — do not create a separate
transaction for continuation lines. The amount and balance appear on the first line.

BANK CHARGES: Lines like "Charges 31OCT A/C 25863010" with an amount are real transactions
(money_out). Include them.

ONLINE TRANSACTIONS THAT ARE CREDITS: "OnLine Transaction" entries where money appears in
the "Paid In" column are credits (money_in). Check which column the amount is in carefully.

QUEST J M / similar entries with amount in Paid In: If the amount appears in the Paid In
column, it is money_in, regardless of whether it says "OnLine Transaction" or "Automated Credit".

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
        max_tokens=34000,
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
