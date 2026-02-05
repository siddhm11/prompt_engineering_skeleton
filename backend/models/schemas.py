
from typing import List, Optional
from pydantic import BaseModel

class UserProfile(BaseModel):
    user_id: str
    email: Optional[str] = None
    tech_stack: List[str]  # e.g., ["React", "Python", "AWS"]
    preferences: str       # e.g., "Clean code, no comments"

class PromptRequest(BaseModel):
    user_id: str
    prompt: str
    platform: Optional[str] = "unknown"

class TrackRequest(BaseModel):
    user_id: str
    prompt: str
    platform: Optional[str] = "unknown"

class OTPRequest(BaseModel):
    email: str

class OTPVerify(BaseModel):
    email: str
    code: str
