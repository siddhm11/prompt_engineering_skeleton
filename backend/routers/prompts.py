
import time
from bson import ObjectId
from fastapi import APIRouter, Depends
from ..models.schemas import TrackRequest, EnhanceRequest, FeedbackRequest
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

    # ── 4. SIMILARITY SEARCH ON SAVED PROMPTS ──
    similar_saved = MemoryService.search_saved_prompts(
        user_id=user_id,
        query_text=request.prompt,
        limit=3,
        exclude_ids=selected_ids,
    )
    similarity_context_parts = []
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
            model="openai/gpt-oss-120b",
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

    # ── 9. MEMORIZE (if unique) ──
    if max_similarity < 0.90:
        MemoryService.memorize_strategy(user_id, request.prompt, enhanced_prompt)

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
