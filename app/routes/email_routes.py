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
# Request models
# -------------------------------------------------------------------
class SendCertificatesRequest(BaseModel):
    templateFile: str = Field(..., description="Template filename (PDF)")
    csvFile: str = Field(..., description="CSV filename with recipient data")
    mapping: dict = Field(..., description="Placeholder-to-column mapping")
    emailColumn: str = Field(..., description="Column containing email addresses")
    eventName: str = Field(..., description="Event name for email subject/body")
    accessToken: str = Field(..., description="Google OAuth2 access token")

class PreviewEmailRequest(BaseModel):
    mapping: dict
    emailColumn: str
    eventName: str

# -------------------------------------------------------------------
# Security: validate uploaded filenames
# -------------------------------------------------------------------
def validate_filename(filename: str) -> str:
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    return filename

# -------------------------------------------------------------------
# Beautiful HTML Email Generator
# -------------------------------------------------------------------
def generate_email_content(row: pd.Series, mappings: dict, event_name: str):
    """Generates professional HTML email with dynamic content"""
    
    # Extract name for greeting (prioritize "Name" field)
    name = "Recipient"
    for ph, col in mappings.items():
        if ph.lower() == "name":
            name = str(row.get(col, "Recipient"))
            break
    
    subject = f"Your {event_name} Certificate"
    
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{ 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
                line-height: 1.6; 
                color: #333; 
                max-width: 600px; 
                margin: 0 auto; 
                padding: 20px; 
                background: #f8fafc;
            }}
            .header {{ 
                text-align: center; 
                padding: 30px 20px; 
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                color: white; 
                border-radius: 16px; 
                margin-bottom: 30px; 
                box-shadow: 0 10px 25px rgba(102, 126, 234, 0.3);
            }}
            .greeting {{ 
                font-size: 28px; 
                font-weight: 700; 
                margin-bottom: 8px; 
            }}
            .content {{ 
                background: white; 
                padding: 40px; 
                border-radius: 16px; 
                border: 1px solid #e2e8f0; 
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
            }}
            .certificate-notice {{ 
                background: linear-gradient(135deg, #10b981 0%, #059669 100%); 
                color: white; 
                padding: 24px; 
                border-radius: 12px; 
                text-align: center; 
                font-weight: 600; 
                margin: 30px 0; 
                box-shadow: 0 4px 15px rgba(16, 185, 129, 0.2);
            }}
            .highlight {{ 
                background: #fef3c7; 
                padding: 20px; 
                border-radius: 12px; 
                border-left: 5px solid #f59e0b; 
                margin: 24px 0; 
            }}
            .footer {{ 
                text-align: center; 
                margin-top: 40px; 
                padding-top: 30px; 
                border-top: 1px solid #e2e8f0; 
                color: #64748b; 
                font-size: 14px; 
            }}
            .event-name {{ color: #1e40af; font-weight: 600; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1 class="greeting"> Congratulations, {name}!</h1>
            <p style="margin: 0; opacity: 0.9; font-size: 18px;">Your certificate is ready</p>
        </div>
        
        <div class="content">
            <p style="font-size: 18px; margin-bottom: 24px; color: #1e293b; line-height: 1.7;">
                We're thrilled to present your personalized certificate for the
                <strong class="event-name">{event_name}</strong>.
            </p>
            
            <div class="certificate-notice">
                📎 <strong>Your Official Certificate</strong><br>
                <span style="font-size: 14px; opacity: 0.9;">is attached to this email</span>
            </div>
            
            <div class="highlight">
                <strong>💡 Important:</strong> Please download and save your certificate 
                as it contains your official record of achievement.
            </div>
            
            <p style="margin-bottom: 0; color: #475569; font-size: 16px; line-height: 1.7;">
                Thank you for your participation and outstanding achievement!
            </p>
        </div>
        
        <div class="footer">
            <p style="margin: 0 0 12px 0;">Best regards</p>
            <p style="margin: 0; font-weight: 600; color: #1e40af; font-size: 16px;">
                Certificate Wizard Team
            </p>
        </div>
    </body>
    </html>
    """
    
    return subject, html_body

# -------------------------------------------------------------------
# Email Preview API
# -------------------------------------------------------------------
@router.post("/preview-email")
def preview_email(request: PreviewEmailRequest):
    """Preview email content for frontend"""
    subject = f"Your {request.eventName} Certificate"
    
    return {
        "subject": subject,
        "bodyPreview": f"Dear [Name],\n\nCongratulations on completing the {request.eventName}!\n\nYour certificate is attached."
    }

# -------------------------------------------------------------------
# Gmail API sender (HTML support)
# -------------------------------------------------------------------
def send_email_gmail_api(creds: Credentials, recipient: str, subject: str, html_body: str, pdf_path: str):
    """Send HTML email with PDF attachment via Gmail API"""
    service = build("gmail", "v1", credentials=creds)
    
    msg = MIMEMultipart('alternative')
    msg['to'] = recipient
    msg['subject'] = subject
    
    # HTML body
    msg.attach(MIMEText(html_body, 'html'))
    
    # Attach PDF
    with open(pdf_path, "rb") as f:
        attach = MIMEApplication(f.read(), _subtype="pdf")
        attach.add_header("Content-Disposition", "attachment", filename=os.path.basename(pdf_path))
        msg.attach(attach)
    
    # Encode for Gmail API
    raw_msg = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw_msg}).execute()

# -------------------------------------------------------------------
# Main send certificates route
# -------------------------------------------------------------------
@router.post("/send-certificates")
def send_certificates(request: SendCertificatesRequest):
    """Generate and send personalized certificates via Gmail API"""
    template_file = validate_filename(request.templateFile)
    csv_file = validate_filename(request.csvFile)
    template_path = f"app/static/templates/{template_file}"
    csv_path = f"app/static/csv/{csv_file}"

    if not os.path.exists(template_path) or not os.path.exists(csv_path):
        raise HTTPException(status_code=400, detail="Template or CSV not found")

    df = pd.read_csv(csv_path)
    sent_count = 0
    failed = []

    # Use OAuth access token
    creds = Credentials(token=request.accessToken)

    for idx, row in df.iterrows():
        recipient = row.get(request.emailColumn)
        if pd.isna(recipient) or not str(recipient).strip():
            failed.append(f"Row {idx+1}: Missing email")
            continue

        # Generate personalized PDF
        output_file = os.path.join(OUTPUT_DIR, f"certificate_{idx+1}.pdf")
        try:
            replace_placeholders_in_pdf(template_path, output_file, request.mapping, row)
        except Exception as e:
            failed.append(f"Row {idx+1}: PDF generation failed - {str(e)}")
            continue

        # Send email
        try:
            subject, html_body = generate_email_content(row, request.mapping, request.eventName)
            send_email_gmail_api(creds, str(recipient).strip(), subject, html_body, output_file)
            sent_count += 1
        except Exception as e:
            print(f"[ERROR] Email failed for {recipient}: {e}")
            failed.append(f"Row {idx+1}: Email failed - {str(e)}")

    # Cleanup generated files
    for file in os.listdir(OUTPUT_DIR):
        os.remove(os.path.join(OUTPUT_DIR, file))

    success_msg = f"✅ Successfully sent {sent_count} certificates for '{request.eventName}'!"
    
    return JSONResponse({
        "message": success_msg,
        "details": {
            "event": request.eventName,
            "sent": sent_count,
            "failed": len(failed)
        },
        "failed_details": failed if failed else None
    })