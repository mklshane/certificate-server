import os
import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from app.routes.generate_routes import replace_placeholders_in_pdf
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.text import MIMEText
import fitz  # PyMuPDF for template analysis
import logging
from pathlib import Path

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()  # Remove prefix="/api"

OUTPUT_DIR = "app/static/generated"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- Configure your SMTP ---
SMTP_HOST = "smtp.example.com"
SMTP_PORT = 587
SMTP_USER = "your_email@example.com"
SMTP_PASS = "your_email_password"

class SendCertificatesRequest(BaseModel):
    templateFile: str = Field(..., min_length=1, description="Name of the template file")
    csvFile: str = Field(..., min_length=1, description="Name of the CSV file")
    mapping: dict = Field(..., description="Dictionary mapping placeholders to CSV columns")
    emailColumn: str = Field(..., min_length=1, description="CSV column containing email addresses")

def validate_filename(filename: str) -> str:
    """Prevent directory traversal attacks."""
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    return filename

def generate_email_content(template_path: str, row: pd.Series, mappings: dict) -> tuple[str, str]:
    """
    Generate dynamic email subject and body based on template and data.
    """
    doc = fitz.open(template_path)
    text = doc[0].get_text()  # Assuming single-page certificate
    doc.close()

    context_keywords = ["SOCIETY", "CHAPTER", "CERTIFICATE", "EVENT"]
    context = next((word for word in text.split() if any(kw in word.upper() for kw in context_keywords)), "Certificate")

    subject = f"Your {context} Certificate"
    body = f"Dear <<Name>>,\n\nCongratulations! Attached is your {context.lower()} certificate. " \
           f"Please find the details below:\n\n"
    for ph, col in mappings.items():
        val = str(row.get(col, "N/A"))
        body += f"{ph.replace('_', ' ').title()}: {val}\n"
    body += f"\nBest regards,\n{context.split()[0] if context.split() else 'Administrator'} Team"

    for ph, col in mappings.items():
        val = str(row.get(col, f"[{ph}]"))
        body = body.replace(f"<<{ph}>>", val)

    return subject, body

@router.post("/send-certificates")
def send_certificates(request: SendCertificatesRequest):
    logger.info(f"Received request for /send-certificates with payload={request.dict()}")
    template_file = validate_filename(request.templateFile)
    csv_file = validate_filename(request.csvFile)
    template_path = f"app/static/templates/{template_file}"
    csv_path = f"app/static/csv/{csv_file}"

    if not os.path.exists(template_path) or not os.path.exists(csv_path):
        raise HTTPException(status_code=400, detail="Template or CSV not found")

    df = pd.read_csv(csv_path)
    sent_count = 0
    failed = []

    try:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
    except Exception as e:
        logger.error(f"SMTP connection failed: {e}")
        raise HTTPException(status_code=500, detail=f"SMTP connection failed: {e}")

    for index, row in df.iterrows():
        recipient = row.get(request.emailColumn)
        if not recipient:
            failed.append(f"Row {index+1} missing email")
            continue

        output_file = os.path.join(OUTPUT_DIR, f"certificate_{index+1}.pdf")
        try:
            replace_placeholders_in_pdf(template_path, output_file, request.mapping, row)
        except Exception as e:
            failed.append(f"Row {index+1} PDF generation failed: {e}")
            continue

        try:
            msg = MIMEMultipart()
            msg["From"] = SMTP_USER
            msg["To"] = recipient
            msg["Subject"], email_body = generate_email_content(template_path, row, request.mapping)
            msg.attach(MIMEText(email_body, "plain"))

            with open(output_file, "rb") as f:
                pdf_attach = MIMEApplication(f.read(), _subtype="pdf")
                pdf_attach.add_header("Content-Disposition", "attachment", filename=f"certificate_{index+1}.pdf")
                msg.attach(pdf_attach)

            server.send_message(msg)
            sent_count += 1
        except Exception as e:
            failed.append(f"Row {index+1} email failed: {e}")

    server.quit()

    return JSONResponse({
        "message": f"Emails sent: {sent_count}, Failed: {len(failed)}",
        "failed_details": failed
    })