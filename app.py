from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dateutil import parser as date_parser
import re

app = FastAPI(title="Invoice Extraction API")

# -----------------------------
# Enable CORS
# -----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Request Model
# -----------------------------
class InvoiceRequest(BaseModel):
    invoice_text: str


# -----------------------------
# Helper Functions
# -----------------------------
def parse_amount(value):
    if not value:
        return None

    value = value.replace(",", "")
    value = re.sub(r"[^\d.]", "", value)

    try:
        return float(value)
    except:
        return None


def extract(patterns, text):
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if m:
            return m.group(1).strip()
    return None


def parse_date(text):

    patterns = [
        r"Date\s*[:\-]\s*(.+)",
        r"Issued\s*[:\-]\s*(.+)",
        r"Invoice Date\s*[:\-]\s*(.+)"
    ]

    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            raw = m.group(1).strip()

            raw = raw.split("\n")[0].strip()

            try:
                return date_parser.parse(raw, dayfirst=True).strftime("%Y-%m-%d")
            except:
                pass

    return None


def detect_currency(text):

    if re.search(r"\bINR\b|Rs\.?|₹", text, re.IGNORECASE):
        return "INR"

    if re.search(r"\bUSD\b|\$", text):
        return "USD"

    if re.search(r"\bEUR\b|€", text):
        return "EUR"

    return None


# -----------------------------
# API
# -----------------------------
@app.get("/")
def root():
    return {
        "message": "Invoice Extraction API Running"
    }


@app.post("/extract")
def extract_invoice(req: InvoiceRequest):

    text = req.invoice_text

    invoice_no = extract([
        r"Invoice\s*No\.?\s*[:\-]\s*([A-Za-z0-9\-\/]+)",
        r"Invoice\s*#\s*[:\-]\s*([A-Za-z0-9\-\/]+)",
        r"Ref\s*[:\-]\s*([A-Za-z0-9\-\/]+)"
    ], text)

    vendor = extract([
        r"Vendor\s*[:\-]\s*(.+)",
        r"Supplier\s*[:\-]\s*(.+)",
        r"Seller\s*[:\-]\s*(.+)"
    ], text)

    if vendor:
        vendor = vendor.split("\n")[0].strip()

    amount = extract([
        r"Subtotal\s*[:.\- ]*\s*(?:Rs\.?|₹|\$|USD|INR)?\s*([\d,]+\.\d+)",
        r"Sub\s*Total\s*[:.\- ]*\s*(?:Rs\.?|₹|\$|USD|INR)?\s*([\d,]+\.\d+)"
    ], text)

    tax = extract([
        r"(?:GST|CGST|SGST|IGST|Tax).*?(?:Rs\.?|₹|\$|USD|INR)?\s*([\d,]+\.\d+)"
    ], text)

    result = {
        "invoice_no": invoice_no,
        "date": parse_date(text),
        "vendor": vendor,
        "amount": parse_amount(amount),
        "tax": parse_amount(tax),
        "currency": detect_currency(text)
    }

    # Always return all six keys
    for key in [
        "invoice_no",
        "date",
        "vendor",
        "amount",
        "tax",
        "currency"
    ]:
        if key not in result:
            result[key] = None

    return result