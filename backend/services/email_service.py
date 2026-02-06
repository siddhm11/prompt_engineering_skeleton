
import requests
from ..core.config import settings

def send_email_sendgrid(to_email: str, subject: str, content: str):
    """Sends authentic email via SendGrid if Key is present."""
    if not settings.SENDGRID_API_KEY:
        print(f"⚠️ No SendGrid Key. Simulating email to {to_email}")
        return False
        
    url = "https://api.sendgrid.com/v3/mail/send"
    headers = {
        "Authorization": f"Bearer {settings.SENDGRID_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": "aminyahouse2000@gmail.com", "name": "Prompt Memory"},
        "subject": subject,
        "content": [{"type": "text/plain", "value": content}]
    }
    
    try:
        res = requests.post(url, headers=headers, json=data)
        if res.status_code >= 400:
            print(f"❌ SendGrid Error: {res.text}")
        else:
            print(f"✅ Email sent to {to_email}")
    except Exception as e:
        print(f"❌ Email Failed: {e}")
