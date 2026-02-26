
import io
import time
import json
from bson import ObjectId
from fastapi import APIRouter, Depends, UploadFile, File, Form, Query
from ..models.schemas import TrackRequest, EnhanceRequest, FeedbackRequest, SavePromptRequest
from ..core.security import verify_jwt
from ..core.database import MongoDB, in_memory_users, in_memory_saved_prompts
from ..services.memory_service import MemoryService
from ..services.llm_service import get_groq_client

router = APIRouter()

# ══════════════════════════════════════════════════════════════
# SYSTEM PROMPTS — Mode-Aware, Platform-Aware, Intent-Aware
# ══════════════════════════════════════════════════════════════

SYSTEM_PROMPT_BASE = """You are a Prompt Refinement Specialist. You take raw, incomplete human thoughts and transform them into the clearest, most effective prompt possible for an LLM.

### ABSOLUTE RULE
Understand the user's TRUE INTENT first. Read the prompt literally.
- If it's about emotions → refine as an emotional/psychology question.
- If it's about code → refine as a technical spec.
- If it's creative → refine as a creative brief.
- NEVER inject technical context into non-technical prompts.

### CONVERSATION AWARENESS
You may receive the user's recent conversation history. This is CRITICAL context.
- "now add error handling" only makes sense if you know they were discussing React hooks.
- Use conversation history to resolve ambiguity, pronouns ("it", "this", "that"), and implicit references.
- Weave conversation context naturally — don't dump it, integrate it.

### USING SAVED PROMPT CONTEXT
You may receive saved prompts (user-selected or auto-matched). Use them ONLY if topically relevant.
If a saved coding prompt appears but the user is asking about relationships — ignore it completely.

### USER PROFILE (use ONLY for technical prompts)
- Tech stack: [{tech_stack}]
- Preferences: [{preferences}]
"""

MODE_INSTRUCTIONS = {
    "quick": """
### MODE: QUICK
Keep it short and sharp. Minimal enhancement.
- Fix ambiguity and add just enough specificity
- Do NOT add frameworks, roles, or structures
- Output should be 1-3 sentences max
- Think: "What's the clearest way to ask this?"
""",
    "deep": """
### MODE: DEEP
Full structured enhancement. This is the power mode.
- For technical prompts: apply CO-STAR (Role, Context, Task, Strategy, Constraints, Output format)
- For non-technical: add depth, specificity, expert perspective, and structure
- Break complex asks into numbered parts
- Add useful constraints (what to do AND what not to do)
- The output should be comprehensive but natural — not a template
""",
    "creative": """
### MODE: CREATIVE
Loosen constraints. Encourage exploration and originality.
- Invite the LLM to think divergently
- Suggest multiple angles or perspectives
- Use open-ended framing ("explore", "what if", "imagine")
- Don't over-constrain — leave room for surprise
- Keep the tone warm and curious
"""
}

PLATFORM_HINTS = {
    "claude.ai": "The target LLM is Claude. Claude responds well to clear, direct instructions. Use natural prose rather than heavy formatting.",
    "chatgpt.com": "The target LLM is ChatGPT. ChatGPT responds well to markdown structure — use headers, bullet points, and clear formatting.",
    "gemini.google.com": "The target LLM is Gemini. Gemini prefers concise, focused questions with clear intent. Avoid excessive structure.",
    "www.perplexity.ai": "The target LLM is Perplexity (search-focused). Frame prompts as clear research questions with specific information needs.",
    "grok.com": "The target LLM is Grok. Grok appreciates direct, witty, and concise prompts. Keep instructions clear and don't over-formalize.",
    "x.com": "The target LLM is Grok (via X). Grok appreciates direct, witty, and concise prompts. Keep instructions clear and don't over-formalize.",
}

OUTPUT_INSTRUCTION = """
### OUTPUT
- Return ONLY the refined prompt. No explanations, no commentary, no labels.
- The refined prompt should feel like a natural, well-crafted message — not a rigid template.
- Match the user's language (English, Hindi, etc.).
"""


@router.post("/track")
def track_prompt(request: TrackRequest, user_id: str = Depends(verify_jwt)):
    """Silently learns from user prompts."""
    request.user_id = user_id
    
    MemoryService.log_prompt(
        user_id=request.user_id,
        original=request.prompt,
        source="passive_tracker"
    )

    _, max_similarity = MemoryService.retrieve_context(request.user_id, request.prompt)
    
    if max_similarity > 0.95:
        return {"status": "skipped", "reason": "redundant"}

    MemoryService.memorize_strategy(request.user_id, request.prompt, request.prompt)
    return {"status": "memorized"}


@router.post("/enhance")
def enhance_prompt(request: EnhanceRequest, user_id: str = Depends(verify_jwt)):
    """
    The core prompt engineering endpoint — intent-aware, mode-aware, platform-aware.
    
    Context Priority:
      1. Conversation history (what's been discussed on the page)
      2. User-selected saved prompts
      3. Similarity-matched saved prompts
      4. User profile (only if technical)
    """
    start_time = time.time()
    mode = (request.mode or "deep").lower()
    if mode not in MODE_INSTRUCTIONS:
        mode = "deep"
    platform = request.platform or "unknown"
    
    # ── 1. USER PROFILE ──
    user_data = None
    if MongoDB.users_col is not None:
        user_data = MongoDB.users_col.find_one({"user_id": user_id})
    if user_data is None:
        user_data = in_memory_users.get(user_id, {})

    ts_raw = user_data.get("tech_stack", [])
    tech_stack = ", ".join(ts_raw) if isinstance(ts_raw, list) else str(ts_raw)
    preferences = user_data.get("preferences", "")
    
    # ── 2. CONVERSATION CONTEXT ──
    conversation_ctx = ""
    if request.conversation_context and len(request.conversation_context) > 0:
        msgs = request.conversation_context[-6:]  # last 6 messages max
        conversation_ctx = "\n".join([f"- {m}" for m in msgs])
    
    # ── 3. USER-SELECTED SAVED PROMPTS ──
    selected_context_parts = []
    selected_ids = request.selected_prompt_ids or []
    
    for pid in selected_ids:
        doc = _fetch_saved_prompt(pid, user_id)
        if doc:
            label = doc.get("title") or "Saved Prompt"
            selected_context_parts.append(f"[Selected by user] {label}: \"{doc['content']}\"")

    # ── 4. SIMILARITY SEARCH ON SAVED PROMPTS (skip if skip_similarity=True) ──
    similar_saved = []
    similarity_context_parts = []
    if not request.skip_similarity:
        similar_saved = MemoryService.search_saved_prompts(
            user_id=user_id,
            query_text=request.prompt,
            limit=3,
            exclude_ids=selected_ids,
        )
        for item in similar_saved:
            label = item.get("title") or "Saved Prompt"
            similarity_context_parts.append(
                f"[Auto-matched] {label}: \"{item['content']}\""
            )

    # ── 5. BUILD SYSTEM PROMPT ──
    system_parts = [
        SYSTEM_PROMPT_BASE.format(
            tech_stack=tech_stack or "Not specified",
            preferences=preferences or "Not specified"
        ),
        MODE_INSTRUCTIONS[mode],
    ]
    
    # Platform hint
    if platform in PLATFORM_HINTS:
        system_parts.append(f"### PLATFORM\n{PLATFORM_HINTS[platform]}")
    
    system_parts.append(OUTPUT_INSTRUCTION)
    system_prompt = "\n".join(system_parts)

    # ── 6. BUILD USER MESSAGE ──
    user_parts = []
    
    # Conversation context (highest priority — it's the live thread)
    if conversation_ctx:
        user_parts.append(f"### RECENT CONVERSATION (what the user has been discussing)\n{conversation_ctx}")
    
    # Saved prompt context
    if selected_context_parts:
        user_parts.append("### USER-SELECTED CONTEXT\n" + "\n".join(selected_context_parts))
    
    if similarity_context_parts:
        user_parts.append("### RELATED SAVED PROMPTS (use only if relevant)\n" + "\n".join(similarity_context_parts))
    
    # The actual prompt
    user_parts.append(f"### USER'S PROMPT\n\"{request.prompt}\"")
    
    user_parts.append("### TASK\nRefine the user's prompt. Stay true to their intent. Use conversation context to resolve any ambiguity. If saved context is relevant, weave it in. If not, ignore it.")
    
    user_message = "\n\n".join(user_parts)

    # ── 7. CALL LLM ──
    enhanced_prompt = request.prompt
    try:
        client = get_groq_client()
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.2 if mode == "quick" else 0.4 if mode == "creative" else 0.3,
        )
        enhanced_prompt = chat_completion.choices[0].message.content
    except Exception as e:
        print(f"❌ Groq API Error: {e}")

    process_time = round(time.time() - start_time, 2) 
    
    # ── 8. LOG ──
    max_similarity = similar_saved[0]["score"] if similar_saved else 0.0
    log_id = MemoryService.log_prompt(
        user_id=user_id,
        original=request.prompt,
        enhanced=enhanced_prompt,
        score=max_similarity,
        latency=process_time,
    )

    # ── 9. MEMORIZE removed — user must explicitly save via /prompts/save ──

    return {
        "original": request.prompt,
        "enhanced": enhanced_prompt,
        "log_id": log_id,
        "latency": process_time,
        "mode": mode,
        "context_used": {
            "selected": len(selected_context_parts),
            "auto_matched": len(similarity_context_parts),
            "conversation_messages": len(request.conversation_context or []),
        }
    }


@router.post("/enhance/feedback")
def enhance_feedback(request: FeedbackRequest, user_id: str = Depends(verify_jwt)):
    """Store thumbs up/down feedback on an enhanced prompt."""
    feedback_doc = {
        "user_id": user_id,
        "log_id": request.log_id,
        "rating": request.rating,
        "original": request.original,
        "enhanced": request.enhanced,
        "timestamp": time.time(),
    }
    
    if MongoDB.db is not None:
        try:
            # Store in a feedback collection
            MongoDB.db["prompt_feedback"].insert_one(feedback_doc)
        except Exception as e:
            print(f"⚠️ Feedback store error: {e}")
    
    return {"status": "recorded", "rating": request.rating}


@router.post("/voice-enhance")
async def voice_enhance(
    audio: UploadFile = File(...),
    mode: str = Form("deep"),
    platform: str = Form("unknown"),
    conversation_context: str = Form(""),
    selected_prompt_ids: str = Form("[]"),
    user_id: str = Depends(verify_jwt),
):
    """
    Voice-to-Prompt pipeline:
      1. Transcribe audio with Groq Whisper (whisper-large-v3-turbo)
      2. Enhance transcript with LLM (llama-3.3-70b-versatile)
      3. Return both transcription and enhanced prompt
    """
    start_time = time.time()

    # ── 1. READ AUDIO ──
    audio_bytes = await audio.read()
    if len(audio_bytes) < 100:
        return {"error": "Audio too short. Please speak for at least a second."}

    # ── 2. TRANSCRIBE WITH WHISPER ──
    transcribed_text = ""
    try:
        client = get_groq_client()
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = audio.filename or "audio.webm"

        transcription = client.audio.transcriptions.create(
            file=(audio_file.name, audio_file),
            model="whisper-large-v3-turbo",
            language="en",
            response_format="text",
        )
        transcribed_text = transcription.strip() if isinstance(transcription, str) else str(transcription).strip()
    except Exception as e:
        print(f"❌ Whisper transcription error: {e}")
        return {"error": f"Transcription failed: {str(e)}"}

    if len(transcribed_text) < 3:
        return {"error": "Could not understand audio. Try speaking clearly."}

    transcription_time = round(time.time() - start_time, 2)

    # ── 3. ENHANCE THE TRANSCRIPT ──
    # Parse form data
    try:
        ctx_list = json.loads(conversation_context) if conversation_context else []
    except Exception:
        ctx_list = []
    try:
        sel_ids = json.loads(selected_prompt_ids) if selected_prompt_ids else []
    except Exception:
        sel_ids = []

    # Build an EnhanceRequest and reuse the enhance logic
    enhance_req = EnhanceRequest(
        prompt=transcribed_text,
        mode=mode,
        platform=platform,
        conversation_context=ctx_list if ctx_list else None,
        selected_prompt_ids=sel_ids if sel_ids else None,
    )
    enhance_result = enhance_prompt(enhance_req, user_id)

    total_time = round(time.time() - start_time, 2)

    return {
        "transcription": transcribed_text,
        "enhanced": enhance_result.get("enhanced", transcribed_text),
        "original": transcribed_text,
        "mode": mode,
        "transcription_time": transcription_time,
        "total_time": total_time,
        "context_used": enhance_result.get("context_used"),
        "log_id": enhance_result.get("log_id", ""),
    }


def _fetch_saved_prompt(prompt_id: str, user_id: str) -> dict:
    """Helper to get a single saved prompt by ID, owned by user_id."""
    if MongoDB.saved_prompts_col is not None:
        try:
            doc = MongoDB.saved_prompts_col.find_one(
                {"_id": ObjectId(prompt_id), "user_id": user_id}
            )
            return doc
        except Exception:
            return None
    else:
        doc = in_memory_saved_prompts.get(prompt_id)
        if doc and doc.get("user_id") == user_id:
            return doc
        return None


# ══════════════════════════════════════════════════════════════
# PROMPT HISTORY & EXPLICIT SAVE
# ══════════════════════════════════════════════════════════════

@router.get("/prompts/history")
def get_prompt_history(
    q: str = Query("", description="Search query"),
    limit: int = Query(20, ge=1, le=100),
    skip: int = Query(0, ge=0),
    user_id: str = Depends(verify_jwt),
):
    """Search/list user's past saved prompts from MongoDB."""
    results = MemoryService.search_prompt_logs(
        user_id=user_id, query=q, limit=limit, skip=skip
    )
    return {"prompts": results}


@router.post("/prompts/save")
def save_prompt(request: SavePromptRequest, user_id: str = Depends(verify_jwt)):
    """
    Explicitly save a prompt to the database + Qdrant.
    Only called when user clicks 'Save' — no automatic saving.
    """
    # Log to MongoDB
    log_id = MemoryService.log_prompt(
        user_id=user_id,
        original=request.prompt,
        source="user_saved",
    )

    # Memorize to Qdrant for future similarity matching
    MemoryService.memorize_strategy(user_id, request.prompt, request.prompt)

    return {"status": "saved", "log_id": log_id}
