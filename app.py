from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dateutil import parser as date_parser
import re

app = FastAPI(title="IITM Finance Cell - Invoice Extraction API")

# -----------------------------
# Enable CORS for Cloudflare Workers
# -----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Request Schema
# -----------------------------
class InvoiceRequest(BaseModel):
    invoice_text: str

# -----------------------------
# Extraction Logic & Helper Functions
# -----------------------------
def clean_number(value_str):
    if not value_str:
        return None
    try:
        sanitized = value_str.replace(",", "").strip()
        return float(sanitized)
    except ValueError:
        return None

def extract_invoice_no(text):
    # Sequential matching sorted from most specific to least specific
    patterns = [
        r"\bInvoice\s*No\.?\s*[:\-]?\s*([A-Za-z0-9\-\/]+)",
        r"\bInvoice\s*#\s*[:\-]?\s*([A-Za-z0-9\-\/]+)",
        r"\bRef\.?\s*[:\-]?\s*([A-Za-z0-9\-\/]+)",
        r"\bInvoice\s*[:\-]\s*([A-Za-z0-9\-\/]+)",
        r"\bInvoice\s+([A-Za-z0-9\-\/]+)"
    ]
    
    # Blacklist words to prevent catching headers or structural words
    blacklist = {"invoice", "no", "date", "tax", "vendor", "supplier", "client", "to", "bill"}
    
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            val = match.group(1).strip()
            if val.lower() not in blacklist:
                return val
                
    return None

def extract_date(text):
    pattern = r"\b(?:Date|Issued|Invoice Date)\s*[:\-]?\s*(.+)"
    for match in re.finditer(pattern, text, re.IGNORECASE):
        raw_date = match.group(1).split("\n")[0].strip()
        try:
            parsed_date = date_parser.parse(raw_date, fuzzy=True, dayfirst=True)
            return parsed_date.strftime("%Y-%m-%d")
        except:
            continue
    return None

def extract_vendor(text):
    label_match = re.search(r"\b(?:Vendor|Supplier|Seller|Billed By)\s*[:\-]?\s*(.+)", text, re.IGNORECASE)
    if label_match:
        return label_match.group(1).split("\n")[0].strip()
    
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if lines:
        first_line = lines[0]
        if "—" in first_line:
            parts = first_line.split("—")
            candidate = parts[0].strip()
            if candidate.lower() not in ["invoice", "tax invoice"]:
                return candidate
        if "invoice" not in first_line.lower():
            return first_line
        elif len(lines) > 1 and first_line.lower() in ["invoice", "tax invoice"]:
            if not re.search(r"\b(invoice|date|ref|client|bill)\b", lines[1], re.IGNORECASE):
                return lines[1]
                
    return None

def extract_amount(text):
    for line in text.split("\n"):
        if re.search(r"\b(subtotal|sub-total|sub total|net\s+amount)\b", line, re.IGNORECASE):
            numbers = re.findall(r"[\d,]+(?:\.\d+)?", line)
            if numbers:
                return clean_number(numbers[-1])
    return None

def extract_tax(text):
    total_tax = 0.0
    found_tax = False
    for line in text.split("\n"):
        if re.search(r"\b(GST|CGST|SGST|IGST|VAT|Tax)\b", line, re.IGNORECASE) and not re.search(r"\b(taxable|before|invoice)\b", line, re.IGNORECASE):
            numbers = re.findall(r"[\d,]+(?:\.\d+)?", line)
            if numbers:
                val = clean_number(numbers[-1])
                if val is not None:
                    total_tax += val
                    found_tax = True
    return round(total_tax, 2) if found_tax else None

def detect_currency(text):
    text_upper = text.upper()
    if any(x in text_upper for x in ["INR", "RS.", "₹", "RUPEES"]):
        return "INR"
    if any(x in text_upper for x in ["USD", "$", "DOLLAR"]):
        return "USD"
    if any(x in text_upper for x in ["EUR", "€", "EURO"]):
        return "EUR"
    return None

# -----------------------------
# API Endpoint Execution
# -----------------------------
@app.post("/extract")
def extract_invoice(req: InvoiceRequest):
    raw_text = req.invoice_text

    result = {
        "invoice_no": extract_invoice_no(raw_text),
        "date": extract_date(raw_text),
        "vendor": extract_vendor(raw_text),
        "amount": extract_amount(raw_text),
        "tax": extract_tax(raw_text),
        "currency": detect_currency(raw_text)
    }

    # Strict structural formatting validation guarantee
    for key in ["invoice_no", "date", "vendor", "amount", "tax", "currency"]:
        if result.get(key) == "" or result.get(key) is None:
            result[key] = None

    return result
