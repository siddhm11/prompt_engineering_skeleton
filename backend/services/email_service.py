
import requests
from ..core.config import settings

def send_email_sendgrid(to_email: str, subject: str, content: str):
    """Sends styled email via SendGrid if Key is present."""
    if not settings.SENDGRID_API_KEY:
        print(f"⚠️ No SendGrid Key. Simulating email to {to_email}")
        return False

    # Build a clean HTML email
    html_content = f"""
    <div style="font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 420px; margin: 0 auto; padding: 40px 0;">
      <div style="background: #ffffff; border: 1px solid #e2e2e5; border-radius: 12px; padding: 32px; text-align: center;">
        <div style="font-size: 20px; font-weight: 600; color: #2a8a7a; margin-bottom: 6px;">⊕ Prompt Memory</div>
        <p style="font-size: 14px; color: #6b6b76; margin: 0 0 24px;">Your login verification code</p>
        <div style="background: #f7f7f8; border: 1px solid #e2e2e5; border-radius: 10px; padding: 20px; margin: 0 auto 20px; display: inline-block; min-width: 200px;">
          <div style="font-size: 32px; font-weight: 700; letter-spacing: 8px; color: #1a1a1e; font-family: monospace;">{content.split(': ')[1].split(chr(10))[0] if ': ' in content else content}</div>
        </div>
        <p style="font-size: 12px; color: #9d9da8; margin: 0;">This code expires in 5 minutes.<br>If you didn't request this, you can safely ignore it.</p>
      </div>
    </div>
    """

    url = "https://api.sendgrid.com/v3/mail/send"
    headers = {
        "Authorization": f"Bearer {settings.SENDGRID_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": "aminyahouse2000@gmail.com", "name": "Prompt Memory"},
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": content},
            {"type": "text/html", "value": html_content}
        ]
    }

    try:
        res = requests.post(url, headers=headers, json=data)
        print(f"📧 SendGrid response: status={res.status_code}, body={res.text}")
        if res.status_code >= 400:
            print(f"❌ SendGrid Error: {res.status_code} — {res.text}")
        else:
            print(f"✅ Email sent to {to_email} (status {res.status_code})")
    except Exception as e:
        print(f"❌ Email Failed: {e}")
