"""
Invoice Extractor
=================
Reads every PDF in the "invoices" folder, uses AI to extract the invoice data,
checks the math with code, and writes the results to CSV files in "output".

    python invoice_extractor.py            (or double-click run.bat on Windows)

Design principle: the AI only READS the invoice. Every check (line math, totals,
whether the extracted values really appear in the document) is done by code,
so a wrong AI answer is flagged for review instead of silently accepted.
"""
import csv
import json
import os
import re
import sys
import time
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

import urllib.error
import urllib.request

from pypdf import PdfReader   # pure Python: no compiled parts, runs on locked-down Windows PCs

ROOT = Path(__file__).resolve().parent
INVOICE_DIR = ROOT / "invoices"
OUTPUT_DIR = ROOT / "output"
ENV_FILE = ROOT / ".env"

DEFAULT_MODEL = "gpt-6-luna"
API_URL = "https://api.openai.com/v1/responses"
TOLERANCE = Decimal("0.01")          # rounding tolerance for money checks
MAX_CHARS = 60_000                   # safety limit for very long PDFs

# ----------------------------------------------------------------------------- config
def load_env():
    """Minimal .env reader (KEY=value per line), so no extra dependency is needed."""
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def get_api_key():
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if key:
        return key
    print("\nNo OpenAI API key found.")
    print("Create one at https://platform.openai.com/api-keys and paste it below.")
    key = input("OpenAI API key: ").strip()
    if not key:
        sys.exit("No key provided. Exiting.")
    with ENV_FILE.open("a", encoding="utf-8") as f:
        f.write(f"\nOPENAI_API_KEY={key}\n")
    print("Key saved to .env (you will not be asked again).\n")
    return key


# ----------------------------------------------------------------------------- PDF
def extract_text(pdf_path):
    """Extracts text keeping the column layout, so table rows stay on one line."""
    pages = []
    for page in PdfReader(str(pdf_path)).pages:
        raw = page.extract_text(extraction_mode="layout") or ""
        lines = [re.sub(r" {4,}", "   ", ln.rstrip()) for ln in raw.splitlines() if ln.strip()]
        pages.append("\n".join(lines))
    return "\n\n--- page break ---\n\n".join(pages).strip()


# ----------------------------------------------------------------------------- AI
SCHEMA = {
    "type": "object",
    "properties": {
        "vendor_name": {"type": "string"},
        "invoice_number": {"type": "string"},
        "invoice_date": {"type": "string", "description": "YYYY-MM-DD, or empty if not found"},
        "currency": {"type": "string", "description": "ISO code like USD or EUR, or empty"},
        "line_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "quantity": {"type": ["number", "null"]},
                    "unit_price": {"type": ["number", "null"]},
                    "amount": {"type": ["number", "null"]},
                },
                "required": ["description", "quantity", "unit_price", "amount"],
                "additionalProperties": False,
            },
        },
        "subtotal": {"type": ["number", "null"]},
        "tax": {"type": ["number", "null"]},
        "shipping": {"type": ["number", "null"]},
        "discount": {"type": ["number", "null"]},
        "total": {"type": ["number", "null"]},
    },
    "required": ["vendor_name", "invoice_number", "invoice_date", "currency", "line_items",
                 "subtotal", "tax", "shipping", "discount", "total"],
    "additionalProperties": False,
}

INSTRUCTIONS = """You extract data from the text of a supplier invoice.

Rules:
- Copy values exactly as printed. Never calculate, estimate or invent a value.
  If a value is not printed on the invoice, return null (or "" for text fields).
- Do NOT compute the total, subtotal or line amounts yourself. If the invoice does not print them, use null.
- vendor_name is the company that ISSUED the invoice, not the customer ("Bill to").
- Numbers: return plain numbers. Convert formats like "1.234,56" (decimal comma) to 1234.56. No currency symbols.
- discount: return it as a positive number.
- Dates: return YYYY-MM-DD. Dates with dots (05.10.2026) are day.month.year. Dates with slashes in USD invoices are month/day/year.
- currency: ISO code if the invoice shows it or a clear symbol ($ = USD unless stated otherwise, EUR, etc.), otherwise "".
- Include every product/service line in line_items. Do not include subtotal, tax, shipping or total lines as items."""


def call_ai(text, api_key, model, retries=3):
    body = {
        "model": model,
        "instructions": INSTRUCTIONS,
        "input": text[:MAX_CHARS],
        "text": {"format": {"type": "json_schema", "name": "invoice", "strict": True, "schema": SCHEMA}},
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    for attempt in range(1, retries + 1):
        status, payload = http_post_json(API_URL, headers, body)
        if status == 200:
            return parse_ai_response(json.loads(payload))
        err = f"HTTP {status}: {payload[:300]}" if status else f"connection error: {payload}"
        if status in (400, 401, 403, 404):                 # retrying will not help
            raise RuntimeError(err)
        if attempt < retries:
            time.sleep(3 * attempt)
    raise RuntimeError(err)


def http_post_json(url, headers, body, timeout=90):
    """POST with the standard library. Returns (status_code, text); status 0 = no connection."""
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return 0, str(e)


def parse_ai_response(data):
    for block in data.get("output", []):
        for part in block.get("content", []) or []:
            if part.get("type") == "refusal":
                raise RuntimeError("the AI refused to process this document")
            if part.get("type") == "output_text":
                return json.loads(part["text"])
    raise RuntimeError("no text in the AI response")


# ----------------------------------------------------------------------------- checks
def dec(v):
    if v is None or v == "":
        return None
    try:
        return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None


def number_variants(value):
    """Ways a number can be printed: 1234.5 -> '1234.50', '1,234.50', '1.234,50', '1234,50'."""
    d = dec(value)
    if d is None:
        return []
    us = f"{d:,.2f}"
    plain = f"{d:.2f}"
    eu = us.replace(",", "X").replace(".", ",").replace("X", ".")
    out = {us, plain, eu, plain.replace(".", ",")}
    if d == d.to_integral():                       # "15" or "15.00"
        out.add(str(int(d)))
    return out


def appears_in(text, value):
    """True if any printed form of the number appears in the document text."""
    compact = text.replace(" ", "")
    return any(v in text or v in compact for v in number_variants(value))


def validate(inv, text):
    issues = []

    # Required fields
    for field, label in [("vendor_name", "vendor"), ("invoice_number", "invoice number"),
                         ("invoice_date", "date")]:
        if not str(inv.get(field) or "").strip():
            issues.append(f"Missing {label}")
    if inv.get("invoice_date") and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", inv["invoice_date"]):
        issues.append(f"Unexpected date format: {inv['invoice_date']}")
    if not inv.get("line_items"):
        issues.append("No line items found")
    total = dec(inv.get("total"))
    if total is None:
        issues.append("Missing invoice total")

    # Anti-hallucination: extracted values must exist in the document
    num = str(inv.get("invoice_number") or "").strip()
    if num and num.lower() not in text.lower():
        issues.append(f"Invoice number '{num}' not found in the document text")
    if total is not None and not appears_in(text, total):
        issues.append(f"Total {total} not found in the document text")
    vendor = str(inv.get("vendor_name") or "").strip()
    if vendor and vendor.split()[0].lower() not in text.lower():
        issues.append(f"Vendor name '{vendor}' not found in the document text")

    # Line math: quantity x unit price = amount
    line_checks = []
    items_sum = Decimal("0")
    for i, li in enumerate(inv.get("line_items") or [], start=1):
        q, p, a = dec(li.get("quantity")), dec(li.get("unit_price")), dec(li.get("amount"))
        check = "OK"
        if a is None:
            check = "Missing amount"
            issues.append(f"Line {i}: missing amount")
        else:
            items_sum += a
            if q is not None and p is not None:
                expected = (Decimal(str(li["quantity"])) * Decimal(str(li["unit_price"]))).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP)
                if abs(expected - a) > TOLERANCE:
                    check = f"qty x price = {expected}, printed {a}"
                    issues.append(f"Line {i} ({li.get('description', '')[:40]}): {check}")
        line_checks.append(check)

    # Totals: sum of lines (+ tax + shipping - discount) = total
    subtotal = dec(inv.get("subtotal"))
    tax, ship, disc = (dec(inv.get(k)) or Decimal("0") for k in ("tax", "shipping", "discount"))
    if subtotal is not None and abs(subtotal - items_sum) > TOLERANCE:
        issues.append(f"Line items add up to {items_sum}, but subtotal is {subtotal}")
    calculated_total = items_sum + tax + ship - abs(disc)
    difference = None
    if total is not None:
        difference = total - calculated_total
        if abs(difference) > TOLERANCE:
            issues.append(f"Line items + tax + shipping - discount = {calculated_total}, "
                          f"but invoice total is {total} (difference {difference:+})")

    return {
        "status": "OK" if not issues else "REVIEW",
        "issues": issues,
        "line_checks": line_checks,
        "line_items_sum": items_sum,
        "calculated_total": calculated_total,
        "difference": difference,
    }


# ----------------------------------------------------------------------------- run
SUMMARY_COLS = ["file", "status", "vendor_name", "invoice_number", "invoice_date", "currency",
                "subtotal", "tax", "shipping", "discount", "total", "line_items_sum",
                "calculated_total", "difference", "issues"]
LINE_COLS = ["file", "vendor_name", "invoice_number", "invoice_date", "line_no", "description",
             "quantity", "unit_price", "amount", "line_check"]


def fmt(v):
    return "" if v is None else str(v)


def process_invoice(pdf_path, ai_func):
    text = extract_text(pdf_path)
    if len(text) < 20:
        return {"file": pdf_path.name, "status": "REVIEW",
                "issues": "No text found in the PDF (probably scanned): needs OCR or manual entry"}, []
    inv = ai_func(text)
    v = validate(inv, text)
    summary = {
        "file": pdf_path.name, "status": v["status"],
        **{k: fmt(inv.get(k)) for k in ["vendor_name", "invoice_number", "invoice_date", "currency"]},
        **{k: fmt(dec(inv.get(k))) for k in ["subtotal", "tax", "shipping", "discount", "total"]},
        "line_items_sum": fmt(v["line_items_sum"]), "calculated_total": fmt(v["calculated_total"]),
        "difference": fmt(v["difference"]), "issues": " | ".join(v["issues"]),
    }
    lines = [{
        "file": pdf_path.name, "vendor_name": inv.get("vendor_name", ""),
        "invoice_number": inv.get("invoice_number", ""), "invoice_date": inv.get("invoice_date", ""),
        "line_no": i, "description": li.get("description", ""), "quantity": fmt(li.get("quantity")),
        "unit_price": fmt(dec(li.get("unit_price"))), "amount": fmt(dec(li.get("amount"))),
        "line_check": v["line_checks"][i - 1],
    } for i, li in enumerate(inv.get("line_items") or [], start=1)]
    return summary, lines


def write_csv(path, cols, rows):
    # utf-8-sig so Excel opens accents and symbols correctly
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def run(ai_func=None, invoice_dir=INVOICE_DIR, output_dir=OUTPUT_DIR):
    invoice_dir.mkdir(exist_ok=True)
    output_dir.mkdir(exist_ok=True)
    pdfs = sorted(p for p in invoice_dir.iterdir() if p.suffix.lower() == ".pdf")
    if not pdfs:
        print(f"No PDF files found in: {invoice_dir}")
        return [], []

    if ai_func is None:
        load_env()
        key = get_api_key()
        model = os.environ.get("OPENAI_MODEL", DEFAULT_MODEL)
        ai_func = lambda text: call_ai(text, key, model)

    summaries, all_lines, log = [], [], []
    print(f"Processing {len(pdfs)} invoice(s)...\n")
    for n, pdf in enumerate(pdfs, start=1):
        try:
            s, lines = process_invoice(pdf, ai_func)
        except Exception as e:                       # one bad file never stops the batch
            s, lines = {"file": pdf.name, "status": "ERROR", "issues": str(e)[:500]}, []
        summaries.append(s)
        all_lines.extend(lines)
        mark = {"OK": "OK    ", "REVIEW": "REVIEW", "ERROR": "ERROR "}[s["status"]]
        print(f"[{n}/{len(pdfs)}] {mark} {pdf.name}")
        if s["status"] != "OK":
            print(f"          -> {s['issues']}")
        log.append(f"{datetime.now():%Y-%m-%d %H:%M:%S} {s['status']} {pdf.name} {s.get('issues', '')}")

    write_csv(output_dir / "invoices_summary.csv", SUMMARY_COLS, summaries)
    write_csv(output_dir / "line_items.csv", LINE_COLS, all_lines)
    with (output_dir / "run_log.txt").open("a", encoding="utf-8") as f:
        f.write("\n".join(log) + "\n")

    counts = {k: sum(1 for s in summaries if s["status"] == k) for k in ("OK", "REVIEW", "ERROR")}
    print(f"\nDone: {counts['OK']} OK, {counts['REVIEW']} to review, {counts['ERROR']} error(s).")
    print(f"Results saved in: {output_dir}")
    return summaries, all_lines


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\nCancelled.")
