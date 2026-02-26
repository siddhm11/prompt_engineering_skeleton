
import time
import uuid
import httpx
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import HTMLResponse
from ..models.schemas import OTPRequest, OTPVerify
from ..core.config import settings
from ..core.database import MongoDB, in_memory_users
from ..core.security import create_jwt_token
from ..services.email_service import send_email_sendgrid

router = APIRouter()
_otp_store = {}

@router.post("/auth/request-otp")
def request_otp(request: OTPRequest):
    email = request.email.strip().lower()
    
    # ── DEMO BYPASS: ok@gmail.com gets instant login ──
    if email == "ok@gmail.com":
        _otp_store[email] = {"code": "000000", "expires": time.time() + 9999}
        print(f"\n🔓 [DEMO] Bypass login for {email} — code: 000000\n")
        return {"message": "OTP sent."}
    
    # Generate 6-digit code
    import random
    code = f"{random.randint(100000, 999999)}"
    
    _otp_store[email] = {
        "code": code,
        "expires": time.time() + 300 # 5 minutes
    }
    
    email_body = f"Your Prompt Memory Login Code is: {code}\n\nIt expires in 5 minutes."
    send_email_sendgrid(email, "Your Login Code", email_body)

    # Dev Log
    print(f"\n📨 [EMAIL LOG] To: {email} | Code: {code}\n")
    return {"message": "OTP sent."}

@router.post("/auth/verify-otp")
def verify_otp(request: OTPVerify):
    email = request.email.strip().lower()
    code = request.code.strip()
    
    if email not in _otp_store:
        raise HTTPException(status_code=400, detail="No OTP requested for this email.")
        
    stored_data = _otp_store[email]
    
    if time.time() > stored_data["expires"]:
        del _otp_store[email]
        raise HTTPException(status_code=400, detail="OTP expired.")
        
    if stored_data["code"] != code:
        raise HTTPException(status_code=400, detail="Invalid code.")
        
    del _otp_store[email]
    
    # Find or Register
    user_id = None
    if MongoDB.users_col is not None:
        user = MongoDB.users_col.find_one({"email": email})
        if user: user_id = user["user_id"]
    else:
        for uid, profile in in_memory_users.items():
            if profile.get("email") == email:
                user_id = uid
                break
                
    if not user_id:
        user_id = str(uuid.uuid4())
        new_profile = {"user_id": user_id, "email": email, "tech_stack": ["General"], "preferences": "Default"}
        if MongoDB.users_col is not None:
            MongoDB.users_col.insert_one(new_profile)
        else:
            in_memory_users[user_id] = new_profile
            
    token = create_jwt_token(user_id, email)
    return {"token": token, "email": email, "user_id": user_id}

# --- GOOGLE OAUTH ---

@router.get("/auth/google/login")
def google_login():
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Server missing Google Client ID")
        
    redirect_uri = settings.GOOGLE_REDIRECT_URI
    scope = "openid email profile"
    auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"response_type=code&client_id={settings.GOOGLE_CLIENT_ID}&"
        f"redirect_uri={redirect_uri}&scope={scope}&"
        f"access_type=offline&prompt=consent"
    )
    return {"url": auth_url}

@router.get("/auth/google/callback")
async def google_callback(code: str):
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
         raise HTTPException(status_code=500, detail="Server missing Google Secrets")

    token_url = "https://oauth2.googleapis.com/token"
    payload = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": "https://siddhm11-prompt-engine.hf.space/auth/google/callback"
    }
    
    async with httpx.AsyncClient() as client:
        res = await client.post(token_url, data=payload)
        if res.status_code != 200:
            return {"error": "Failed to exchange code", "details": res.text}
        
        tokens = res.json()
        access_token = tokens.get("access_token")
        
        user_res = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        user_info = user_res.json()
        
    email = user_info.get("email")
    if not email:
        return {"error": "No email found in Google Account"}
        
    # Find/Create User
    user_id = None
    if MongoDB.users_col is not None:
        user = MongoDB.users_col.find_one({"email": email})
        if user: user_id = user["user_id"]
    else:
        for uid, profile in in_memory_users.items():
            if profile.get("email") == email:
                user_id = uid
                break
                
    if not user_id:
        user_id = str(uuid.uuid4())
        new_profile = {"user_id": user_id, "email": email, "tech_stack": ["General"], "preferences": "Default"}
        if MongoDB.users_col is not None:
            MongoDB.users_col.insert_one(new_profile)
        else:
            in_memory_users[user_id] = new_profile

    token = create_jwt_token(user_id, email)
    
    html_content = f"""
    <html>
    <body>
    <script>
        if (window.opener) {{
            window.opener.postMessage({{ type: "GOOGLE_AUTH_SUCCESS", token: "{token}", email: "{email}", user_id: "{user_id}" }}, "*");
            window.close();
        }} else {{
            document.write("Login Successful! You can close this tab.");
        }}
    </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)
