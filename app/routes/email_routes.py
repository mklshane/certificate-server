import os
import base64
import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.text import MIMEText
from app.routes.generate_routes import replace_placeholders_in_pdf

# -------------------------------------------------------------------
# Router + setup
# -------------------------------------------------------------------
router = APIRouter()
OUTPUT_DIR = "app/static/generated"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# -------------------------------------------------------------------
# Request model
# -------------------------------------------------------------------
class SendCertificatesRequest(BaseModel):
    templateFile: str = Field(..., description="Template filename (PDF)")
    csvFile: str = Field(..., description="CSV filename with recipient data")
    mapping: dict = Field(..., description="Placeholder-to-column mapping")
    emailColumn: str = Field(..., description="Column containing email addresses")
    accessToken: str = Field(..., description="Google OAuth2 access token")  # ✅ New


# -------------------------------------------------------------------
# Security: validate uploaded filenames
# -------------------------------------------------------------------
def validate_filename(filename: str) -> str:
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    return filename


# -------------------------------------------------------------------
# Email content generator
# -------------------------------------------------------------------
def generate_email_content(template_path: str, row: pd.Series, mappings: dict):
    """
    Generates a dynamic subject and body text based on the data row and mapping.
    """
    subject = "Your Certificate"
    body = "Dear <<Name>>,\n\nPlease find your certificate attached.\n\n"

    for ph, col in mappings.items():
        val = str(row.get(col, "N/A"))
        body += f"{ph}: {val}\n"

    # Replace placeholders like <<Name>> with actual data
    for ph, col in mappings.items():
        val = str(row.get(col, f"[{ph}]"))
        body = body.replace(f"<<{ph}>>", val)

    return subject, body


# -------------------------------------------------------------------
# Gmail API sender
# -------------------------------------------------------------------
def send_email_gmail_api(creds: Credentials, recipient: str, subject: str, body: str, pdf_path: str):
    """
    Uses Gmail API (via user's OAuth token) to send email with PDF attachment.
    """
    service = build("gmail", "v1", credentials=creds)

    msg = MIMEMultipart()
    msg["to"] = recipient
    msg["subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    # Attach certificate
    with open(pdf_path, "rb") as f:
        attach = MIMEApplication(f.read(), _subtype="pdf")
        attach.add_header("Content-Disposition", "attachment", filename=os.path.basename(pdf_path))
        msg.attach(attach)

    # Encode message to base64 for Gmail API
    raw_msg = base64.urlsafe_b64encode(msg.as_bytes()).decode()

    # Send the message
    service.users().messages().send(userId="me", body={"raw": raw_msg}).execute()


# -------------------------------------------------------------------
# Main route: send certificates
# -------------------------------------------------------------------
@router.post("/send-certificates")
def send_certificates(request: SendCertificatesRequest):
    """
    Generates and sends personalized certificates via Gmail API using
    the access token of the logged-in Google user.
    """
    template_file = validate_filename(request.templateFile)
    csv_file = validate_filename(request.csvFile)
    template_path = f"app/static/templates/{template_file}"
    csv_path = f"app/static/csv/{csv_file}"

    if not os.path.exists(template_path) or not os.path.exists(csv_path):
        raise HTTPException(status_code=400, detail="Template or CSV not found")

    df = pd.read_csv(csv_path)
    sent_count = 0
    failed = []

    # ✅ Use the OAuth access token passed from frontend
    creds = Credentials(token=request.accessToken)

    for idx, row in df.iterrows():
        recipient = row.get(request.emailColumn)
        if not recipient:
            failed.append(f"Row {idx+1} missing email")
            continue

        # Generate personalized PDF
        output_file = os.path.join(OUTPUT_DIR, f"certificate_{idx+1}.pdf")
        try:
            replace_placeholders_in_pdf(template_path, output_file, request.mapping, row)
        except Exception as e:
            failed.append(f"Row {idx+1} PDF generation failed: {e}")
            continue

        # Send via Gmail API
        try:
            subject, body = generate_email_content(template_path, row, request.mapping)
            send_email_gmail_api(creds, recipient, subject, body, output_file)
            sent_count += 1
        except Exception as e:
            print(f"[ERROR] Gmail send failed for {recipient}: {e}")
            failed.append(f"Row {idx+1} email failed: {str(e)}")


    return JSONResponse({
        "message": f"Emails sent: {sent_count}, Failed: {len(failed)}",
        "failed_details": failed
    })
