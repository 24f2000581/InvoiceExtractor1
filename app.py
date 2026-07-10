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
    """Converts a formatted string like '1,40,000.00' or '2,199.00' to a float."""
    if not value_str:
        return None
    try:
        # Remove commas and handle spacing
        sanitized = value_str.replace(",", "").strip()
        return float(sanitized)
    except ValueError:
        return None

def extract_invoice_no(text):
    # Matches 'Invoice No: INV-2026-0041', 'Ref: NS/2026/778', 'Invoice #...', etc.
    pattern = r"\b(?:Invoice\s*No\.?|Invoice\s*#|Invoice|Ref\.?)\s*[:\-]?\s*([A-Za-z0-9\-\/]+)"
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(1).strip() if match else None

def extract_date(text):
    # Matches 'Date: 15 March 2026', 'Issued: 2026-01-22', etc.
    pattern = r"\b(?:Date|Issued|Invoice Date)\s*[:\-]?\s*([A-Za-z0-9\s/\.,-]+)"
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        raw_date = match.group(1).strip()
        try:
            # dayfirst=True accurately parses DD/MM/YYYY formats typical in Indian invoices
            parsed_date = date_parser.parse(raw_date, fuzzy=True, dayfirst=True)
            return parsed_date.strftime("%Y-%m-%d")
        except:
            return None
    return None

def extract_vendor(text):
    # Strategy 1: Explicit Vendor/Supplier Labels
    label_match = re.search(r"\b(?:Vendor|Supplier|Seller|Billed By)\s*[:\-]?\s*(.+)", text, re.IGNORECASE)
    if label_match:
        return label_match.group(1).split("\n")[0].strip()
    
    # Strategy 2: Fallback for header styling (e.g., "NovaSoft Solutions — Tax Invoice")
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if lines:
        first_line = lines[0]
        if "—" in first_line:
            parts = first_line.split("—")
            candidate = parts[0].strip()
            if candidate.lower() not in ["invoice", "tax invoice"]:
                return candidate
        
        # Strategy 3: First line text flag normalization
        if "invoice" not in first_line.lower():
            return first_line
        elif len(lines) > 1 and first_line.lower() in ["invoice", "tax invoice"]:
            # If the first line is just an identifier title, the second line is likely the vendor
            if not re.search(r"\b(invoice|date|ref|client|bill)\b", lines[1], re.IGNORECASE):
                return lines[1]
                
    return None

def extract_amount(text):
    # Matches subtotal line items and safely isolates the trailing monetary value
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
        # Matches tax labels while avoiding confusion with subtotal descriptive tags
        if re.search(r"\b(GST|CGST|SGST|IGST|VAT|Tax)\b", line, re.IGNORECASE) and not re.search(r"\b(taxable|before)\b", line, re.IGNORECASE):
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

    # Extract all relevant metadata fields
    result = {
        "invoice_no": extract_invoice_no(raw_text),
        "date": extract_date(raw_text),
        "vendor": extract_vendor(raw_text),
        "amount": extract_amount(raw_text),
        "tax": extract_tax(raw_text),
        "currency": detect_currency(raw_text)
    }

    # Strict structural formatting validation guarantee (Ensures all 6 keys populate null instead of dropping)
    for key in ["invoice_no", "date", "vendor", "amount", "tax", "currency"]:
        if result.get(key) == "" or result.get(key) is None:
            result[key] = None

    return result
