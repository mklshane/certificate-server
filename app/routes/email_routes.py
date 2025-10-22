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
import re

# -------------------------------------------------------------------
# Router + setup
# -------------------------------------------------------------------
router = APIRouter()
OUTPUT_DIR = "app/static/generated"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# -------------------------------------------------------------------
# Request models (UPDATED with email customization)
# -------------------------------------------------------------------
class SendCertificatesRequest(BaseModel):
    templateFile: str = Field(..., description="Template filename (PDF)")
    csvFile: str = Field(..., description="CSV filename with recipient data")
    mapping: dict = Field(..., description="Placeholder-to-column mapping")
    emailColumn: str = Field(..., description="Column containing email addresses")
    eventName: str = Field(..., description="Event name for email subject/body")
    accessToken: str = Field(..., description="Google OAuth2 access token")
    senderName: str = Field(..., description="Account owner name for email signature")
    emailSubject: str = Field(default="", description="Custom email subject")  # NEW
    emailBody: str = Field(default="", description="Custom email body")  # NEW

class PreviewEmailRequest(BaseModel):
    mapping: dict
    emailColumn: str
    eventName: str
    senderName: str = Field(default="Your Name", description="Sender name for preview")
    emailSubject: str = Field(default="", description="Custom email subject")  # NEW
    emailBody: str = Field(default="", description="Custom email body")  # NEW

# -------------------------------------------------------------------
# Security: validate uploaded filenames
# -------------------------------------------------------------------
def validate_filename(filename: str) -> str:
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    return filename

# -------------------------------------------------------------------
# Email Generator with Customization Support
# -------------------------------------------------------------------
def generate_email_content(row: pd.Series, mappings: dict, event_name: str, sender_name: str, 
                          custom_subject: str = "", custom_body: str = ""):
    """Generates email content with support for custom templates and placeholders"""
    
    # Extract name for greeting
    name = "Recipient"
    for ph, col in mappings.items():
        if ph.lower() == "name":
            name = str(row.get(col, "Recipient"))
            break
    
    # Use custom subject or default
    if custom_subject:
        subject = replace_placeholders_in_text(custom_subject, row, mappings)
    else:
        subject = f"Your {event_name} Certificate"
    
    # Use custom body or default
    if custom_body:
        body = replace_placeholders_in_text(custom_body, row, mappings)
        # Ensure signature is included
        if not body.strip().endswith(sender_name):
            body += f"\n\nBest regards,\n{sender_name}"
    else:
        # Default email body
        body = f"""Dear {name},

Congratulations on completing the {event_name}!

Your personalized certificate is attached to this email.

Please download and save it as your official record of achievement.

Thank you for your participation!

Best regards,
{sender_name}"""
    
    return subject, body

def replace_placeholders_in_text(text: str, row: pd.Series, mappings: dict) -> str:
    """Replace placeholders in text with actual values from row data"""
    result = text
    
    # Replace <<placeholder>> patterns
    for placeholder, column_name in mappings.items():
        if column_name and column_name in row:
            value = str(row[column_name])
            result = result.replace(f"<<{placeholder}>>", value)
    
    # Also support {column_name} syntax for flexibility
    for column_name in row.index:
        value = str(row[column_name])
        result = result.replace(f"{{{column_name}}}", value)
    
    return result

# -------------------------------------------------------------------
# Email Preview API (UPDATED)
# -------------------------------------------------------------------
@router.post("/preview-email")
def preview_email(request: PreviewEmailRequest):
    """Preview email content for frontend with customization support"""
    
    # Use custom subject or default
    if request.emailSubject:
        subject = request.emailSubject
        # Replace placeholders with sample values for preview
        for placeholder, column_name in request.mapping.items():
            if column_name:
                subject = subject.replace(f"<<{placeholder}>>", f"[{column_name}]")
    else:
        subject = f"Your {request.eventName} Certificate"
    
    # Use custom body or default
    if request.emailBody:
        body_preview = request.emailBody
        # Replace placeholders with sample values for preview
        for placeholder, column_name in request.mapping.items():
            if column_name:
                body_preview = body_preview.replace(f"<<{placeholder}>>", f"[{column_name}]")
        
        # Ensure signature is included
        if not body_preview.strip().endswith(request.senderName):
            body_preview += f"\n\nBest regards,\n{request.senderName}"
    else:
        body_preview = f"""Dear [Name],

Congratulations on completing the {request.eventName}!

Your personalized certificate is attached to this email.

Please download and save it as your official record of achievement.

Thank you for your participation!

Best regards,
{request.senderName}"""
    
    return {
        "subject": subject,
        "bodyPreview": body_preview
    }

# -------------------------------------------------------------------
# FIXED Gmail API sender (PDF ATTACHMENT GUARANTEED)
# -------------------------------------------------------------------
def send_email_gmail_api(creds: Credentials, recipient: str, subject: str, body: str, pdf_path: str):
    """Send PLAIN TEXT email with PDF attachment via Gmail API"""
    
    # Verify PDF file exists before sending
    if not os.path.exists(pdf_path):
        raise Exception(f"PDF file not found: {pdf_path}")
    
    print(f"Sending email to {recipient} with attachment: {pdf_path}")
    
    service = build("gmail", "v1", credentials=creds)
    
    # Use 'mixed' for attachments (more reliable)
    msg = MIMEMultipart('mixed')
    msg['to'] = recipient
    msg['subject'] = subject
    
    # Plain text body
    text_part = MIMEText(body, 'plain')
    msg.attach(text_part)
    
    # FIXED PDF Attachment
    try:
        with open(pdf_path, "rb") as f:
            pdf_data = f.read()
            print(f"PDF size: {len(pdf_data)} bytes")
        
        attach = MIMEApplication(pdf_data, _subtype="pdf")
        attach.add_header(
            'Content-Disposition', 
            'attachment', 
            filename=os.path.basename(pdf_path)
        )
        msg.attach(attach)
        print(f"PDF attached successfully: {os.path.basename(pdf_path)}")
        
    except Exception as attach_error:
        print(f"PDF attachment failed: {attach_error}")
        raise Exception(f"PDF attachment failed: {attach_error}")
    
    # Encode for Gmail API
    try:
        raw_msg = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        print(f"Message encoded, sending to {recipient}")
        
        result = service.users().messages().send(
            userId="me", 
            body={"raw": raw_msg}
        ).execute()
        
        print(f"Email sent successfully! Message ID: {result.get('id')}")
        
    except Exception as send_error:
        print(f"Gmail API send failed: {send_error}")
        raise Exception(f"Gmail send failed: {send_error}")

# -------------------------------------------------------------------
# Main send certificates route (UPDATED)
# -------------------------------------------------------------------
@router.post("/send-certificates")
def send_certificates(request: SendCertificatesRequest):
    """Generate and send personalized certificates via Gmail API"""
    template_file = validate_filename(request.templateFile)
    csv_file = validate_filename(request.csvFile)
    template_path = f"app/static/templates/{template_file}"
    csv_path = f"app/static/csv/{csv_file}"

    if not os.path.exists(template_path):
        raise HTTPException(status_code=400, detail=f"Template not found: {template_path}")
    if not os.path.exists(csv_path):
        raise HTTPException(status_code=400, detail=f"CSV not found: {csv_path}")

    df = pd.read_csv(csv_path)
    sent_count = 0
    failed = []
    
    print(f"Starting batch: {len(df)} recipients")

    # Use OAuth access token
    try:
        creds = Credentials(token=request.accessToken)
    except Exception as creds_error:
        raise HTTPException(status_code=401, detail=f"Invalid access token: {creds_error}")

    for idx, row in df.iterrows():
        recipient = row.get(request.emailColumn)
        if pd.isna(recipient) or not str(recipient).strip():
            failed.append(f"Row {idx+1}: Missing email")
            continue

        recipient_email = str(recipient).strip()
        output_file = os.path.join(OUTPUT_DIR, f"certificate_{idx+1}.pdf")
        
        print(f"Generating PDF {idx+1}/{len(df)} for {recipient_email}")

        # Generate personalized PDF
        try:
            replace_placeholders_in_pdf(template_path, output_file, request.mapping, row)
            if not os.path.exists(output_file):
                raise Exception("PDF generation failed - file not created")
            print(f"PDF generated: {output_file}")
        except Exception as pdf_error:
            error_msg = f"Row {idx+1}: PDF generation failed - {str(pdf_error)}"
            failed.append(error_msg)
            print(f"{error_msg}")
            continue

        # Send email (UPDATED with customization)
        try:
            subject, body = generate_email_content(
                row, 
                request.mapping, 
                request.eventName, 
                request.senderName,
                request.emailSubject,
                request.emailBody
            )
            send_email_gmail_api(creds, recipient_email, subject, body, output_file)
            sent_count += 1
            print(f"SUCCESS: Email sent to {recipient_email}")
            
            # Only delete SUCCESSFULLY sent files
            if os.path.exists(output_file):
                os.remove(output_file)
                
        except Exception as email_error:
            error_msg = f"Row {idx+1}: Email failed - {str(email_error)}"
            failed.append(error_msg)
            print(f"{error_msg}")
            # Keep failed PDF for debugging
            continue

    # Final cleanup (any remaining files)
    for file in os.listdir(OUTPUT_DIR):
        file_path = os.path.join(OUTPUT_DIR, file)
        if os.path.isfile(file_path):
            os.remove(file_path)

    success_msg = f"Successfully sent {sent_count} certificates for '{request.eventName}'!"
    
    response = {
        "message": success_msg,
        "details": {
            "event": request.eventName,
            "sent": sent_count,
            "failed": len(failed),
            "total": len(df)
        },
        "failed_details": failed if failed else None
    }
    
    print(f"BATCH COMPLETE: {sent_count} sent, {len(failed)} failed")
    return JSONResponse(response)