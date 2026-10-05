"""Tests that run WITHOUT an API key: the AI is replaced by a fake that returns
the known data of each sample invoice (tests/expected/*.json).

    python tests/test_extractor.py
"""
import csv
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import invoice_extractor as ie  # noqa: E402

EXPECTED = ROOT / "tests" / "expected"
failures = 0


def check(cond, msg):
    global failures
    print(("PASS " if cond else "FAIL ") + msg)
    failures += 0 if cond else 1


def truth(name):
    return json.loads((EXPECTED / f"{name}.json").read_text(encoding="utf-8"))


def as_ai_answer(t):
    """Converts a truth file into the exact format the AI must return."""
    return {"vendor_name": t["vendor"], "invoice_number": t["invoice_number"], "invoice_date": t["date"],
            "currency": t["currency"], "line_items": t["line_items"], "subtotal": t["subtotal"],
            "tax": t["tax"] or None, "shipping": t["shipping"] or None, "discount": t["discount"] or None,
            "total": t["total"]}


def fake_ai_for(pdf_text):
    """Fake AI: finds which sample invoice this is and returns its known data."""
    for f in EXPECTED.glob("*.json"):
        t = json.loads(f.read_text(encoding="utf-8"))
        if "invoice_number" in t and t["invoice_number"] in pdf_text:
            return as_ai_answer(t)
    raise RuntimeError("unknown invoice")


def run_in_tmp(ai_func):
    tmp = Path(tempfile.mkdtemp())
    shutil.copytree(ROOT / "invoices", tmp / "invoices")
    s, l = ie.run(ai_func=ai_func, invoice_dir=tmp / "invoices", output_dir=tmp / "output")
    return tmp, {x["file"]: x for x in s}, l


# ---------------------------------------------------------------- 1. Full run with correct AI answers
tmp, res, lines = run_in_tmp(fake_ai_for)
for f in EXPECTED.glob("*.json"):
    exp = json.loads(f.read_text(encoding="utf-8"))["expected_status"]
    got = res[f.stem + ".pdf"]["status"]
    check(got == exp, f"{f.stem}: status {got} (expected {exp})")

check("difference +10.00" in res["harbor_HC-7781.pdf"]["issues"], "harbor: total mismatch of +10.00 detected")
check("Line 2" in res["metro_MP-55210.pdf"]["issues"] and "162.00" in res["metro_MP-55210.pdf"]["issues"],
      "metro: wrong line (12 x 13.50 = 162.00, printed 180.00) detected")
check("OCR" in res["scanned_greenfield.pdf"]["issues"], "scanned PDF flagged as needing OCR")
check(res["blueridge_BR-2026-0931.pdf"]["calculated_total"] == "263.50", "blueridge: shipping and discount applied")
check(res["sunrise_SS-0045.pdf"]["status"] == "OK", "sunrise: European number format (273,60) accepted")

rows = list(csv.DictReader((tmp / "output" / "line_items.csv").open(encoding="utf-8-sig")))
check(len(rows) == 16, f"line_items.csv has one row per item ({len(rows)})")
check(sum(1 for r in rows if r["line_check"] != "OK") == 1, "exactly one line marked with a problem")
summary_rows = list(csv.DictReader((tmp / "output" / "invoices_summary.csv").open(encoding="utf-8-sig")))
check(len(summary_rows) == 6, "invoices_summary.csv has one row per PDF")
check((tmp / "output" / "run_log.txt").exists(), "run log written")

# ---------------------------------------------------------------- 2. AI invents values (hallucination)
def lying_ai(text):
    a = fake_ai_for(text)
    if a["invoice_number"] == "INV-10482":
        a["invoice_number"] = "INV-99999"     # not in the document
        a["total"] = 1000.00                  # not in the document
    return a

_, res2, _ = run_in_tmp(lying_ai)
iss = res2["northwind_INV-10482.pdf"]["issues"]
check(res2["northwind_INV-10482.pdf"]["status"] == "REVIEW", "invented values -> REVIEW")
check("INV-99999" in iss and "not found" in iss, "invented invoice number detected")
check("Total 1000.00 not found" in iss, "invented total detected")

# AI "fixes" a wrong total by calculating it (should have copied 432.50)
def calculating_ai(text):
    a = fake_ai_for(text)
    if a["invoice_number"] == "HC-7781":
        a["total"] = 422.50
    return a

_, res3, _ = run_in_tmp(calculating_ai)
check("Total 422.50 not found" in res3["harbor_HC-7781.pdf"]["issues"],
      "AI that calculates the total instead of copying it is caught")

# ---------------------------------------------------------------- 3. API failure on one file
def flaky_ai(text):
    if "SS-0045" in text:
        raise RuntimeError("HTTP 429: rate limit")
    return fake_ai_for(text)

_, res4, _ = run_in_tmp(flaky_ai)
check(res4["sunrise_SS-0045.pdf"]["status"] == "ERROR", "API error marks the file as ERROR")
check(res4["northwind_INV-10482.pdf"]["status"] == "OK", "other files still processed after an error")

# ---------------------------------------------------------------- 4. Parsing the raw API response
ok = ie.parse_ai_response({"output": [{"type": "reasoning"}, {"type": "message", "content": [
    {"type": "output_text", "text": json.dumps({"total": 1})}]}]})
check(ok == {"total": 1}, "parses Responses API output")
try:
    ie.parse_ai_response({"output": [{"type": "message", "content": [{"type": "refusal", "refusal": "no"}]}]})
    check(False, "refusal raises an error")
except RuntimeError:
    check(True, "refusal raises an error")

# ---------------------------------------------------------------- 5. HTTP call: request format and retries
def FakeResp(code, data=None):
    return code, json.dumps(data or {})

calls = []
def fake_post(url, headers, body, timeout=90):
    calls.append(body)
    return responses.pop(0)

real_post, real_sleep = ie.http_post_json, ie.time.sleep
ie.http_post_json, ie.time.sleep = fake_post, lambda s: None
try:
    good = {"output": [{"type": "message", "content": [{"type": "output_text", "text": '{"total": 5}'}]}]}
    responses = [FakeResp(429), FakeResp(200, good)]
    check(ie.call_ai("text", "sk-test", "m") == {"total": 5}, "retries after HTTP 429 and succeeds")
    body = calls[-1]
    check(body["text"]["format"]["type"] == "json_schema" and body["text"]["format"]["strict"] is True,
          "request uses strict structured output")
    calls.clear(); responses = [FakeResp(401)]
    try:
        ie.call_ai("text", "sk-bad", "m"); check(False, "401 raises")
    except RuntimeError:
        check(len(calls) == 1, "HTTP 401 is not retried")
finally:
    ie.http_post_json, ie.time.sleep = real_post, real_sleep

# ---------------------------------------------------------------- 6. Number formats
check(ie.appears_in("Total: 1.234,56 EUR", 1234.56), "finds 1.234,56")
check(ie.appears_in("TOTAL $1,234.56", 1234.56), "finds $1,234.56")
check(not ie.appears_in("TOTAL $1,234.56", 1243.56), "does not match a different number")

print("\nALL TESTS PASSED" if failures == 0 else f"\n{failures} TEST(S) FAILED")
sys.exit(1 if failures else 0)
