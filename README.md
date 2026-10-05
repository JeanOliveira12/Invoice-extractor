# Invoice Extractor (PDF → CSV with AI)

A Python tool that reads a folder of PDF invoices from different vendors, extracts the key data with AI, **checks the math with code**, and saves everything to CSV files ready for Excel.

Built for small operations teams: put the PDFs in a folder, double-click `run.bat`, open the results.

## What it extracts

- Vendor name, invoice number, date, currency
- Every line item: description, quantity, unit price, amount
- Subtotal, tax, shipping, discount and total

## How it avoids wrong data

The AI only **reads** the invoice. Everything else is checked by code:

| Check | Example |
|---|---|
| **Line math** | 12 × $13.50 should be $162.00, but the invoice says $180.00 → flagged |
| **Totals** | Lines + tax + shipping − discount should equal the total → difference shown |
| **Values must exist in the PDF** | If the AI returns an invoice number or total that is not printed on the document, it is flagged (catches AI "hallucinations") |
| **No calculated values** | The AI is instructed to copy, never compute. If it "fixes" a wrong total, the check above catches it |
| **Scanned PDFs** | Files with no text layer are flagged as needing OCR instead of producing empty data |
| **Robust batch** | An error in one file (API timeout, corrupt PDF) never stops the others |

The AI answers in a strict JSON schema (OpenAI Structured Outputs), so different vendor layouts always produce the same columns.

## Output

| File | Content |
|---|---|
| `output/invoices_summary.csv` | One row per invoice: all fields, calculated total, difference, **status (OK / REVIEW / ERROR)** and the reason |
| `output/line_items.csv` | One row per line item, with a per-line check |
| `output/run_log.txt` | History of every run |

## Sample invoices

The `invoices/` folder contains 6 fictional invoices with different layouts, created by `tools/make_sample_invoices.py`:

| Invoice | Layout | Expected result |
|---|---|---|
| Northwind Beverage Supply | Classic table, US date, sales tax | OK |
| Blue Ridge Paper Co. | Free-text list, shipping and discount | OK |
| Sunrise Snacks Ltd | European formats (05.10.2026, 1.234,56), EUR | OK |
| Harbor Cleaning Products | Two-column header, ISO date, **total off by $10** | REVIEW |
| Metro Packaging | **One line where qty × price ≠ amount** | REVIEW |
| Greenfield Farms | **Scanned image, no text** | REVIEW (needs OCR) |

## How to run (Windows)

1. Install [Python](https://www.python.org/downloads/) and tick **"Add python.exe to PATH"**.
2. Put the PDF invoices in the `invoices` folder.
3. Double-click **`run.bat`**.
   - First run: it installs what is needed (1–2 minutes) and asks for your OpenAI API key once.
4. The `output` folder opens with the results.

Command line (any OS):

```bash
pip install -r requirements.txt
python invoice_extractor.py
```

## Tests

```bash
python tests/test_extractor.py
```

The tests run **without an API key**: the AI is replaced by a fake that returns known answers, including deliberately wrong ones, to prove the checks catch invented values, calculated totals, line errors, API failures and scanned files.

## Tech

Python · OpenAI Responses API (structured outputs) · pypdf (pure Python, no compiled dependencies) · standard library only for HTTP and CSV

## Cost

Each invoice costs a fraction of a cent with a small model. The model can be changed in `.env` (`OPENAI_MODEL`).
