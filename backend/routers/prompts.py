
import time
from fastapi import APIRouter, Depends
from ..models.schemas import PromptRequest, TrackRequest
from ..core.security import verify_jwt
from ..core.database import MongoDB, in_memory_users
from ..services.memory_service import MemoryService
from ..services.llm_service import get_groq_client

router = APIRouter()

# --- PROMPTS ---

CLASSIFICATION_PROMPT = """
You are a request classifier. Determine if the user's request is "SIMPLE" or "COMPLEX".

Definitions:
- SIMPLE: Factual questions, definitions, basic explanations, or short/simple queries (e.g., "what is bitcoin", "capital of india", "who is elon musk").
- COMPLEX: Requests for code, creative writing, problem-solving, multi-step tasks, or detailed guides (e.g., "write a python script", "create a marketing plan", "debug this error").

Output ONLY the word "SIMPLE" or "COMPLEX". Do not add any punctuation or explanation.
"""

SIMPLE_SYSTEM_PROMPT = """
You are a helpful assistant improving a user's prompt. 
The user asks a simple question or fact. 
Your goal is to refine their prompt to ensure they get a clear, concise, and direct answer from an LLM.

Guidelines:
1.  **Clarity**: Fix any grammatical errors or ambiguity.
2.  **Conciseness**: Keep the prompt short. Do NOT add unnecessary context or roles.
3.  **Directness**: Ensure the prompt asks exactly what the user intends.

Return ONLY the refined prompt. Do NOT explain your changes.
"""

COMPLEX_SYSTEM_PROMPT = """
You are an expert Prompt Engineer. 
The user has a complex request (code, creative work, reasoning). 
Your goal is to rewrite their prompt into a highly effective, structured instruction for an LLM using the CO-STAR framework.

### CO-STAR Framework:
1.  **Context**: Include relevant user background (Tech Stack: {tech_stack}, Preferences: {preferences}).
2.  **Objective**: Clearly state the task.
3.  **Style**: Specify the desired tone and style.
4.  **Tone**: Professional, concise, tech-focused.
5.  **Audience**: Who is this for?
6.  **Response**: Define the output format (e.g., specific code format, markdown structure).

### INSTRUCTIONS:
-   **Structure**: Use Markdown headers and bullet points for readability.
-   **Clarity**: Be explicit about constraints (what NOT to do).
-   **Output**: Return ONLY the refined prompt. Do NOT provide explanations.
"""

# --- ENDPOINTS ---

@router.post("/track")
def track_prompt(request: TrackRequest, user_id: str = Depends(verify_jwt)):
    """Silently learns from user prompts."""
    request.user_id = user_id
    
    # 0. Log to Short-Term
    MemoryService.log_prompt(
        user_id=request.user_id,
        original=request.prompt,
        source="passive_tracker"
    )

    # 1. Redundancy Check
    _, max_similarity = MemoryService.retrieve_context(request.user_id, request.prompt)
    
    if max_similarity > 0.95:
        return {"status": "skipped", "reason": "redundant"}

    # 2. Vectorize
    MemoryService.memorize_strategy(request.user_id, request.prompt, request.prompt)
    return {"status": "memorized"}

@router.post("/enhance")
def enhance_prompt(request: PromptRequest, user_id: str = Depends(verify_jwt)):
    request.user_id = user_id
    start_time = time.time()
    client = get_groq_client()
    
    # 1. GET USER CONTEXT
    user_data = None
    if MongoDB.users_col is not None:
        user_data = MongoDB.users_col.find_one({"user_id": request.user_id})
    if user_data is None:
        user_data = in_memory_users.get(request.user_id, {})

    ts_raw = user_data.get("tech_stack", ["General Python", "Data Science"])
    tech_stack = ", ".join(ts_raw) if isinstance(ts_raw, list) else str(ts_raw)
    preferences = user_data.get("preferences", "Clean, modular code with docstrings.")
    
    # 2. CLASSIFY INTENT
    classification = "COMPLEX" # Default
    try:
        class_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": CLASSIFICATION_PROMPT},
                {"role": "user", "content": request.prompt}
            ],
            model="llama-3.1-8b-instant", # Use a fast model for classification
            temperature=0.0, 
            max_tokens=10
        )
        classification = class_completion.choices[0].message.content.strip().upper()
        # Fallback if model is chatty
        if "SIMPLE" in classification: classification = "SIMPLE"
        elif "COMPLEX" in classification: classification = "COMPLEX"
        else: classification = "COMPLEX"
    except Exception as e:
        print(f"⚠️ Classification failed: {e}")

    print(f"🔍 Intent Classified as: {classification}")

    # 3. SELECT SYSTEM PROMPT & CONSTRUCT MESSAGE
    system_prompt = ""
    user_message_content = ""

    if classification == "SIMPLE":
        system_prompt = SIMPLE_SYSTEM_PROMPT
        user_message_content = request.prompt
    else:
        # Complex Path
        system_prompt = COMPLEX_SYSTEM_PROMPT.format(
            tech_stack=tech_stack,
            preferences=preferences
        )
        # Retrieve Memory only for Complex queries to save tokens/latency on simple ones
        past_context, _ = MemoryService.retrieve_context(request.user_id, request.prompt)
        recent_prompts = MemoryService.get_recent_prompts(request.user_id)
        recent_history_str = "\n".join([f"- {p}" for p in recent_prompts]) if recent_prompts else "No recent history."
        
        user_message_content = f"""
        ### CONTEXT & MEMORY
        Recent Activity:
        {recent_history_str}

        Long-Term Memory:
        {past_context}

        ### USER RAW INPUT
        "{request.prompt}"
        """

    # 4. GENERATE ENHANCED PROMPT
    enhanced_prompt = request.prompt
    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message_content}
            ],
            model="openai/gpt-oss-120b" if classification == "COMPLEX" else "llama-3.1-8b-instant", # Use larger model only for complex
            temperature=0.3, 
        )
        enhanced_prompt = chat_completion.choices[0].message.content
    except Exception as e:
        print(f"❌ Groq API Error: {e}")

    process_time = round(time.time() - start_time, 2) 
    
    # 5. LOG
    log_id = MemoryService.log_prompt(
        user_id=request.user_id,
        original=request.prompt,
        enhanced=enhanced_prompt,
        score=0.0, # Similarity score not relevant here anymore or calculated differently
        latency=process_time,
    )

    # 6. MEMORIZE (only complex strategies)
    if classification == "COMPLEX":
         MemoryService.memorize_strategy(request.user_id, request.prompt, enhanced_prompt)

    return {
        "original": request.prompt,
        "enhanced": enhanced_prompt,
        "log_id": log_id,
        "latency": process_time,
        "classification": classification
    }
