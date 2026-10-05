"""Generates fictional sample invoices (different layouts) for the demo.

All companies, numbers and addresses are invented.
Run:  python tools/make_sample_invoices.py
"""
import io
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "invoices"
TRUTH = ROOT / "tests" / "expected"
OUT.mkdir(exist_ok=True)
TRUTH.mkdir(parents=True, exist_ok=True)


def money(v, sym="$"):
    return f"{sym}{v:,.2f}"


def save_truth(name, data):
    (TRUTH / f"{name}.json").write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------- 1. Classic table, US date, sales tax
def invoice_northwind():
    name = "northwind_INV-10482"
    items = [("Sparkling Water 12x500ml", 40, 6.75), ("Orange Juice 1L (case of 6)", 25, 11.20),
             ("Cola 24-pack cans", 18, 14.90), ("Iced Tea Lemon 6x1.5L", 12, 9.80)]
    sub = sum(q * p for _, q, p in items)
    tax = round(sub * 0.0825, 2)
    total = round(sub + tax, 2)
    c = canvas.Canvas(str(OUT / f"{name}.pdf"), pagesize=LETTER)
    w, h = LETTER
    c.setFillColor(colors.HexColor("#1f4e79")); c.rect(0, h - 70, w, 70, fill=1, stroke=0)
    c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 20); c.drawString(40, h - 45, "Northwind Beverage Supply")
    c.setFont("Helvetica", 9); c.drawString(40, h - 60, "2210 Lakeview Ave, Springfield, IL 62704 (fictional)")
    c.setFillColor(colors.black); c.setFont("Helvetica-Bold", 16); c.drawRightString(w - 40, h - 105, "INVOICE")
    c.setFont("Helvetica", 10)
    c.drawRightString(w - 40, h - 122, "Invoice #: INV-10482")
    c.drawRightString(w - 40, h - 136, "Date: 09/14/2026")
    c.drawRightString(w - 40, h - 150, "Due: 10/14/2026")
    c.drawString(40, h - 122, "Bill To: Delta Distribution LLC"); c.drawString(40, h - 136, "Account 55-201")
    y = h - 190
    c.setFont("Helvetica-Bold", 10)
    for x, t in [(40, "Description"), (330, "Qty"), (400, "Unit Price"), (500, "Amount")]:
        c.drawString(x, y, t)
    c.line(40, y - 5, w - 40, y - 5); c.setFont("Helvetica", 10)
    for d, q, p in items:
        y -= 20
        c.drawString(40, y, d); c.drawString(330, y, str(q)); c.drawString(400, y, money(p)); c.drawString(500, y, money(q * p))
    y -= 30
    for label, val, bold in [("Subtotal", sub, False), ("Sales Tax (8.25%)", tax, False), ("TOTAL DUE", total, True)]:
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 11 if bold else 10)
        c.drawRightString(470, y, label); c.drawRightString(w - 40, y, money(val)); y -= 18
    c.save()
    save_truth(name, {"vendor": "Northwind Beverage Supply", "invoice_number": "INV-10482", "date": "2026-09-14",
                      "currency": "USD", "subtotal": round(sub, 2), "tax": tax, "shipping": 0, "discount": 0,
                      "total": total, "expected_status": "OK",
                      "line_items": [{"description": d, "quantity": q, "unit_price": p, "amount": round(q * p, 2)} for d, q, p in items]})


# ---------------------------------------------------------------- 2. Free text list, shipping and discount
def invoice_blueridge():
    name = "blueridge_BR-2026-0931"
    items = [("Kraft paper bags, medium", 500, 0.18), ("Paper napkins (pack of 250)", 30, 3.40), ("Receipt rolls 80mm", 50, 1.25)]
    sub = sum(q * p for _, q, p in items)
    ship, disc = 24.00, 15.00
    total = round(sub + ship - disc, 2)
    c = canvas.Canvas(str(OUT / f"{name}.pdf"), pagesize=LETTER)
    w, h = LETTER
    c.setFont("Times-Bold", 22); c.drawCentredString(w / 2, h - 60, "BLUE RIDGE PAPER CO.")
    c.setFont("Times-Italic", 10); c.drawCentredString(w / 2, h - 75, "Quality paper goods since 1998 (fictional company)")
    c.setFont("Times-Roman", 11)
    lines = ["Statement / Invoice No. BR-2026-0931", "Issued on September 22, 2026", "Customer: Delta Distribution LLC", "",
             "Items shipped:"]
    lines += [f"   {q} x {d} @ {money(p)} each = {money(q * p)}" for d, q, p in items]
    lines += ["", f"Merchandise: {money(sub)}", f"Freight: {money(ship)}", f"Loyalty discount: -{money(disc)}",
              f"Amount payable: {money(total)}", "", "Payment terms: Net 30. Thank you for your business!"]
    y = h - 120
    for ln in lines:
        c.drawString(60, y, ln); y -= 17
    c.save()
    save_truth(name, {"vendor": "Blue Ridge Paper Co.", "invoice_number": "BR-2026-0931", "date": "2026-09-22",
                      "currency": "USD", "subtotal": round(sub, 2), "tax": 0, "shipping": ship, "discount": disc,
                      "total": total, "expected_status": "OK",
                      "line_items": [{"description": d, "quantity": q, "unit_price": p, "amount": round(q * p, 2)} for d, q, p in items]})


# ---------------------------------------------------------------- 3. Two-column header, ISO date, WRONG TOTAL
def invoice_harbor():
    name = "harbor_HC-7781"
    items = [("Floor cleaner 5L", 10, 18.50), ("Disinfectant spray 500ml", 40, 4.25), ("Microfiber cloths (10 pack)", 15, 4.50)]
    sub = sum(q * p for _, q, p in items)          # 422.50
    wrong_total = 432.50                            # deliberate error: +10.00
    c = canvas.Canvas(str(OUT / f"{name}.pdf"), pagesize=A4)
    w, h = A4
    c.setFont("Helvetica-Bold", 14); c.drawString(30 * mm, h - 25 * mm, "Harbor Cleaning Products")
    c.setFont("Helvetica", 9)
    c.drawString(30 * mm, h - 31 * mm, "Pier 9 Industrial Park, Portland, OR (fictional)")
    c.setStrokeColor(colors.grey); c.rect(120 * mm, h - 50 * mm, 65 * mm, 28 * mm)
    c.setFont("Helvetica", 9)
    c.drawString(123 * mm, h - 28 * mm, "Document: HC-7781")
    c.drawString(123 * mm, h - 34 * mm, "Issue date: 2026-09-30")
    c.drawString(123 * mm, h - 40 * mm, "Order ref: PO-3392")
    c.drawString(123 * mm, h - 46 * mm, "Currency: USD")
    y = h - 70 * mm
    c.setFillColor(colors.HexColor("#eeeeee")); c.rect(30 * mm, y - 2 * mm, 155 * mm, 7 * mm, fill=1, stroke=0)
    c.setFillColor(colors.black); c.setFont("Helvetica-Bold", 9)
    for x, t in [(32, "Item"), (110, "Units"), (130, "Price/unit"), (160, "Line total")]:
        c.drawString(x * mm, y, t)
    c.setFont("Helvetica", 9)
    for d, q, p in items:
        y -= 8 * mm
        c.drawString(32 * mm, y, d); c.drawString(110 * mm, y, str(q))
        c.drawString(130 * mm, y, f"{p:.2f}"); c.drawString(160 * mm, y, f"{q * p:.2f}")
    y -= 14 * mm
    c.setFont("Helvetica-Bold", 11); c.drawString(130 * mm, y, "Invoice total:"); c.drawString(160 * mm, y, f"{wrong_total:.2f}")
    c.save()
    save_truth(name, {"vendor": "Harbor Cleaning Products", "invoice_number": "HC-7781", "date": "2026-09-30",
                      "currency": "USD", "subtotal": None, "tax": 0, "shipping": 0, "discount": 0,
                      "total": wrong_total, "expected_status": "REVIEW",
                      "line_items": [{"description": d, "quantity": q, "unit_price": p, "amount": round(q * p, 2)} for d, q, p in items]})


# ---------------------------------------------------------------- 4. European formats (dd.mm.yyyy, decimal comma)
def invoice_sunrise():
    name = "sunrise_SS-0045"
    items = [("Salted crackers 200g", 60, 1.10), ("Chocolate wafers 150g", 48, 1.45), ("Mixed nuts 500g", 20, 6.90)]
    sub = sum(q * p for _, q, p in items)
    total = round(sub, 2)
    eu = lambda v: f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    c = canvas.Canvas(str(OUT / f"{name}.pdf"), pagesize=A4)
    w, h = A4
    c.setFont("Courier-Bold", 13); c.drawString(25 * mm, h - 25 * mm, "SUNRISE SNACKS LTD  -  INVOICE")
    c.setFont("Courier", 10)
    for i, ln in enumerate(["Invoice no.: SS-0045", "Date: 05.10.2026", "Client: Delta Distribution LLC",
                            "Prices in EUR", "-" * 64]):
        c.drawString(25 * mm, h - (35 + i * 6) * mm, ln)
    y = h - 70 * mm
    c.drawString(25 * mm, y, f"{'Product':<28}{'Qty':>6}{'Price':>12}{'Amount':>14}")
    for d, q, p in items:
        y -= 6 * mm
        c.drawString(25 * mm, y, f"{d:<28}{q:>6}{eu(p):>12}{eu(q * p):>14}")
    y -= 10 * mm
    c.drawString(25 * mm, y, f"{'TOTAL EUR':<46}{eu(total):>14}")
    c.save()
    save_truth(name, {"vendor": "Sunrise Snacks Ltd", "invoice_number": "SS-0045", "date": "2026-10-05",
                      "currency": "EUR", "subtotal": round(sub, 2), "tax": 0, "shipping": 0, "discount": 0,
                      "total": total, "expected_status": "OK",
                      "line_items": [{"description": d, "quantity": q, "unit_price": p, "amount": round(q * p, 2)} for d, q, p in items]})


# ---------------------------------------------------------------- 5. Line item where qty x price != amount
def invoice_metro():
    name = "metro_MP-55210"
    items = [("Corrugated boxes 40x30x30", 200, 0.95, 190.00),
             ("Stretch film roll 500mm", 12, 13.50, 180.00),      # deliberate error: should be 162.00
             ("Packing tape 48mm x 100m", 36, 2.10, 75.60)]
    total = round(sum(a for *_, a in items), 2)                   # total matches the (wrong) amounts
    c = canvas.Canvas(str(OUT / f"{name}.pdf"), pagesize=LETTER)
    w, h = LETTER
    c.setFont("Helvetica-Bold", 18); c.drawString(40, h - 50, "METRO PACKAGING")
    c.setFont("Helvetica", 9); c.drawString(40, h - 63, "Supplier of packaging materials - fictional company")
    c.setFont("Helvetica", 10)
    c.drawString(380, h - 50, "Invoice No: MP-55210"); c.drawString(380, h - 64, "Invoice Date: Oct 1, 2026")
    y = h - 110
    c.setFont("Helvetica-Bold", 10)
    for x, t in [(40, "Qty"), (90, "Item"), (360, "Each"), (470, "Total")]:
        c.drawString(x, y, t)
    c.setFont("Helvetica", 10)
    for d, q, p, a in items:
        y -= 18
        c.drawString(40, y, str(q)); c.drawString(90, y, d); c.drawString(360, y, money(p)); c.drawString(470, y, money(a))
    y -= 28
    c.setFont("Helvetica-Bold", 11); c.drawString(360, y, "Balance Due"); c.drawString(470, y, money(total))
    c.save()
    save_truth(name, {"vendor": "Metro Packaging", "invoice_number": "MP-55210", "date": "2026-10-01",
                      "currency": "USD", "subtotal": None, "tax": 0, "shipping": 0, "discount": 0,
                      "total": total, "expected_status": "REVIEW",
                      "line_items": [{"description": d, "quantity": q, "unit_price": p, "amount": a} for d, q, p, a in items]})


# ---------------------------------------------------------------- 6. Scanned invoice (image only, no text layer)
def invoice_scanned():
    from PIL import Image, ImageDraw, ImageFont
    name = "scanned_greenfield"
    img = Image.new("RGB", (1240, 1754), "white")
    d = ImageDraw.Draw(img)
    try:
        f = ImageFont.truetype("DejaVuSans.ttf", 34)
    except OSError:
        f = ImageFont.load_default()
    for i, t in enumerate(["GREENFIELD FARMS (fictional)", "Invoice GF-118", "Date: 09/28/2026",
                           "20 x Apples crate @ $12.00 = $240.00", "TOTAL: $240.00"]):
        d.text((120, 150 + i * 70), t, fill="black", font=f)
    buf = io.BytesIO(); img.save(buf, format="PNG"); buf.seek(0)
    from reportlab.lib.utils import ImageReader
    c = canvas.Canvas(str(OUT / f"{name}.pdf"), pagesize=A4)
    c.drawImage(ImageReader(buf), 0, 0, width=A4[0], height=A4[1])
    c.save()
    save_truth(name, {"expected_status": "REVIEW", "note": "image-only PDF, needs OCR"})


if __name__ == "__main__":
    for fn in [invoice_northwind, invoice_blueridge, invoice_harbor, invoice_sunrise, invoice_metro, invoice_scanned]:
        fn()
    print("Sample invoices created in", OUT)
