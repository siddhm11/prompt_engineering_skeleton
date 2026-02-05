
import time
from fastapi import APIRouter, Depends
from ..models.schemas import PromptRequest, TrackRequest
from ..core.security import verify_jwt
from ..core.database import MongoDB, in_memory_users
from ..services.memory_service import MemoryService
from ..services.llm_service import get_groq_client

router = APIRouter()

SOTA_SYSTEM_PROMPT = """
You are a Principal Prompt Architect. Your goal is not to "fix" the user's prompt, but to translate their raw intent into a "SOTA" executable specification for an LLM.

### THE PHILOSOPHY (The 7 Rules)
1. **Clarity**: Eliminate ambiguity.
2. **Context**: Inject User Tech Stack [{tech_stack}] & Preferences [{preferences}].
3. **Tasks**: Break complex goals into a step-by-step "Chain of Thought".
4. **Format**: Explicitly define the output format (JSON, Markdown, etc.).
5. **Examples**: Request few-shot examples if abstract.
6. **Role**: Assign a HYPER-SPECIFIC persona (e.g., "Senior Geo-Spatial Data Engineer").
7. **Constraints**: Define Negative Constraints (what NOT to do).

### YOUR PROTOCOL
1. **Analyze**: Identify the user's core intent.
2. **Architect**: Construct a prompt using the **CO-STAR+** framework:
   - [ROLE]: Act as {{Specific Expert Role}}...
   - [CONTEXT]: User context is {tech_stack}...
   - [TASK]: Your specific objective is...
   - [STRATEGY]: Before writing code, outline your step-by-step reasoning...
   - [CONSTRAINTS]: Do NOT use...
   - [OUTPUT]: Provide the answer in {{Specific Format}}...

### INSTRUCTIONS
- Return ONLY the final refined prompt.
- Do NOT provide explanations.
- If the prompt is a question TO YOU (like "what is this?"), answer it as a helper.
"""

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
    
    # 1. GET USER CONTEXT
    user_data = None
    if MongoDB.users_col is not None:
        user_data = MongoDB.users_col.find_one({"user_id": request.user_id})
    if user_data is None:
        user_data = in_memory_users.get(request.user_id, {})

    ts_raw = user_data.get("tech_stack", ["General Python", "Data Science"])
    tech_stack = ", ".join(ts_raw) if isinstance(ts_raw, list) else str(ts_raw)
    preferences = user_data.get("preferences", "Clean, modular code with docstrings.")
    
    # 2. RETRIEVE MEMORY
    past_context, max_similarity = MemoryService.retrieve_context(request.user_id, request.prompt)
    
    # 3. RECENT HISTORY
    recent_prompts = MemoryService.get_recent_prompts(request.user_id)
    recent_history_str = "\n".join([f"- {p}" for p in recent_prompts]) if recent_prompts else "No recent history."

    # 4. CONSTRUCT PROMPT
    formatted_system = SOTA_SYSTEM_PROMPT.format(
        tech_stack=tech_stack,
        preferences=preferences
    )

    user_message = f"""
    ### 1. RECENT ACTIVITY (Immediate Context)
    {recent_history_str}

    ### 2. LONG-TERM MEMORY & PAST STRATEGIES
    {past_context}

    ### 3. RAW USER INPUT
    "{request.prompt}"

    ### 4. TASK
    Apply the 7 Rules. Transform the raw input into a SOTA prompt.
    """

    enhanced_prompt = request.prompt
    try:
        client = get_groq_client()
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": formatted_system},
                {"role": "user", "content": user_message}
            ],
            model="openai/gpt-oss-120b",
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
        score=max_similarity,
        latency=process_time,
    )

    # 6. MEMORIZE (if unique)
    if max_similarity < 0.90:
        MemoryService.memorize_strategy(request.user_id, request.prompt, enhanced_prompt)
    else:
        print(f"♻️ Redundancy detected (Score {max_similarity:.2f}). Skipping save.")

    return {
        "original": request.prompt,
        "enhanced": enhanced_prompt,
        "log_id": log_id,
        "latency": process_time
    }
