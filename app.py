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
def clean_number(value_str):
    """Converts a string like '2,199.00' to a float 2199.00"""
    if not value_str:
        return None
    try:
        return float(value_str.replace(",", ""))
    except ValueError:
        return None

def extract_invoice_no(text):
    # Matches 'Invoice No: INV-123', 'Invoice # INV-123', 'Ref: 123'
    pattern = r"(?:Invoice\s*No\.?|Invoice\s*#|Invoice|Ref\.?)\s*[:\-]?\s*([A-Za-z0-9\-\/]+)"
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(1).strip() if match else None

def extract_date(text):
    # Matches 'Date: 15 March 2026', 'Issued: 2026-03-15', etc.
    pattern = r"(?:Date|Issued|Invoice Date)\s*[:\-]?\s*([A-Za-z0-9\s/\.,-]+)"
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        raw_date = match.group(1).strip()
        try:
            # fuzzy=True helps ignore trailing noise
            parsed_date = date_parser.parse(raw_date, fuzzy=True, dayfirst=True)
            return parsed_date.strftime("%Y-%m-%d")
        except:
            return None
    return None

def extract_vendor(text):
    # Matches 'Vendor: TechParts Pvt Ltd'
    pattern = r"(?:Vendor|Supplier|Seller|Billed By)\s*[:\-]?\s*(.+)"
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None

def extract_amount(text):
    # Find the line containing 'Subtotal' or 'Amount'
    for line in text.split("\n"):
        if re.search(r"\b(Subtotal|Sub-total|Sub Total)\b", line, re.IGNORECASE):
            # Extract all numbers on this line (handles formats like 'Rs. 2,199.00')
            numbers = re.findall(r"[\d,]+(?:\.\d+)?", line)
            if numbers:
                return clean_number(numbers[-1]) # The actual amount is usually the last number
    return None

def extract_tax(text):
    # Find the line containing 'GST', 'Tax', or 'VAT'
    for line in text.split("\n"):
        if re.search(r"\b(GST|CGST|SGST|IGST|Tax|VAT)\b", line, re.IGNORECASE):
            # Extract all numbers on this line. 
            # E.g., for "GST (18%): Rs. 395.82", it finds ['18', '395.82']
            numbers = re.findall(r"[\d,]+(?:\.\d+)?", line)
            if numbers:
                return clean_number(numbers[-1]) # The tax amount is usually the last number
    return None

def detect_currency(text):
    if re.search(r"\b(INR|Rs\.?|₹)\b", text, re.IGNORECASE):
        return "INR"
    if re.search(r"\b(USD|\$)\b", text, re.IGNORECASE):
        return "USD"
    if re.search(r"\b(EUR|€)\b", text, re.IGNORECASE):
        return "EUR"
    return None

# -----------------------------
# API Endpoints
# -----------------------------
@app.get("/")
def root():
    return {"message": "Invoice Extraction API Running"}


@app.post("/extract")
def extract_invoice(req: InvoiceRequest):
    text = req.invoice_text

    # Extract all fields
    result = {
        "invoice_no": extract_invoice_no(text),
        "date": extract_date(text),
        "vendor": extract_vendor(text),
        "amount": extract_amount(text),
        "tax": extract_tax(text),
        "currency": detect_currency(text)
    }

    # Ensure missing fields are strictly None (null in JSON)
    for key in ["invoice_no", "date", "vendor", "amount", "tax", "currency"]:
        if key not in result or result[key] == "":
            result[key] = None

    return result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
