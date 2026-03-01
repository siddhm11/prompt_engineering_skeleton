
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

# --- Saved Prompts ---

class SavedPromptCreate(BaseModel):
    """Create a saved prompt. Only content is required."""
    content: str
    title: Optional[str] = None
    tags: Optional[List[str]] = None
    platform: Optional[str] = None

class SavedPromptUpdate(BaseModel):
    """Update a saved prompt. All fields optional."""
    content: Optional[str] = None
    title: Optional[str] = None
    tags: Optional[List[str]] = None

# --- Enhanced Enhance Request ---

class EnhanceRequest(BaseModel):
    """
    The main enhance endpoint payload.
    - conversation_context: recent messages from the visible chat (scraped from DOM)
    - mode: 'quick' | 'deep' | 'creative' — controls enhancement intensity
    - selected_prompt_ids: IDs of saved prompts the user explicitly ticked
    """
    prompt: str
    platform: Optional[str] = "unknown"
    mode: Optional[str] = "deep"  # quick | deep | creative
    conversation_context: Optional[List[str]] = None
    selected_prompt_ids: Optional[List[str]] = None

class FeedbackRequest(BaseModel):
    """Thumbs up/down on an enhanced prompt."""
    log_id: str
    rating: str  # "up" | "down"
    original: Optional[str] = None
    enhanced: Optional[str] = None

class RefreshRequest(BaseModel):
    """Token refresh — send current token to get a fresh one."""
    token: str
