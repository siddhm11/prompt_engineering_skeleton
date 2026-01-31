import os
import time
from datetime import datetime
from typing import List, Optional

# Third-party libraries
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, Distance, VectorParams, Filter, FieldCondition, MatchValue# Lazy import: from sentence_transformers import SentenceTransformer
from groq import Groq
from pymongo import MongoClient
from dotenv import load_dotenv

# --- 1. CONFIGURATION & SECRETS ---
# Load environment variables from .env file
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MONGO_URI = os.getenv("MONGO_URI")
QDRANT_URL = os.getenv("QDRANT_URL", ":memory:")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

# Free embedding model: all-MiniLM-L6-v2 (384-dim, Apache 2.0). No API key required.
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# Basic check to ensure keys are present (only warn at startup; fail on /enhance if missing)
if not GROQ_API_KEY:
    print("⚠️ GROQ_API_KEY is missing from .env — /enhance will fail until you add it.")

# --- 2. SETUP CLIENTS ---

# A. FastAPI App
app = FastAPI()

# B. CORS (Critical for Chrome Extension)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods (POST, GET, etc.)
    allow_headers=["*"],
)

# C. MongoDB (User Profiles & Logs) — optional; use in-memory fallback if unavailable
users_col = None
prompts_col = None
_in_memory_users = {}  # fallback when MongoDB is not running

try:
    mongo_client = MongoClient(
        MONGO_URI or "mongodb://localhost:27017",
        serverSelectionTimeoutMS=3000,
    )
    mongo_client.admin.command("ping")
    db = mongo_client["prompt_engine_db"]
    users_col = db["users"]
    prompts_col = db["prompt_logs"]
    print("✅ MongoDB Connected")
except Exception as e:
    print(f"⚠️ MongoDB not available ({e}) — using in-memory fallback for profiles/logs.")

# D. Qdrant (Vector Memory)
qdrant = None
COLLECTION_NAME = "prompt_memory"

def init_qdrant():
    """Lazily initialize Qdrant connection."""
    global qdrant
    if qdrant is None:
        try:
            qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
            
            # 1. Check if collection exists
            try:
                collection_exists = qdrant.collection_exists(COLLECTION_NAME)
            except (AttributeError, Exception):
                try:
                    qdrant.get_collection(COLLECTION_NAME)
                    collection_exists = True
                except:
                    collection_exists = False
            
            # 2. Create collection if it doesn't exist
            if not collection_exists:
                try:
                    qdrant.create_collection(
                        collection_name=COLLECTION_NAME,
                        vectors_config=VectorParams(size=384, distance=Distance.COSINE),
                    )
                    print(f"✅ Created new Qdrant collection: '{COLLECTION_NAME}'")
                except Exception as e:
                    if "409" in str(e) or "already exists" in str(e):
                        pass
                    else:
                        raise

            # --- THE FIX: CREATE PAYLOAD INDEX FOR USER_ID ---
            # This tells Qdrant: "Please optimize searches for 'user_id'"
            try:
                qdrant.create_payload_index(
                    collection_name=COLLECTION_NAME,
                    field_name="user_id",
                    field_schema="keyword"  # 'keyword' is best for exact string matches like IDs
                )
                print("✅ Payload index for 'user_id' ensured.")
            except Exception as e:
                # If index already exists, Qdrant might return an error or ignore it. 
                # We catch it just in case, but usually it's safe.
                print(f"ℹ️ Note on Indexing: {e}")

            print(f"✅ Qdrant Connected ({QDRANT_URL})")
        except Exception as e:
            print(f"❌ Qdrant Connection Failed: {e}")
    return qdrant

# E. AI Models — free local embeddings (MiniLM via sentence-transformers)
print("Embedding: free model (MiniLM) will load on first use")
EMBEDDING_MODEL = None
_embedding_unavailable = False

# Lazy-load Groq client to avoid initialization errors
groq_client = None

def get_groq_client():
    """Lazily initialize Groq client."""
    global groq_client
    if groq_client is None:
        try:
            groq_client = Groq(api_key=GROQ_API_KEY)
        except Exception as e:
            print(f"⚠️ Warning: Groq client initialization failed: {e}")
    return groq_client

# --- 3. DATA MODELS (Pydantic) ---

class UserProfile(BaseModel):
    user_id: str
    tech_stack: List[str]  # e.g., ["React", "Python", "AWS"]
    preferences: str       # e.g., "Clean code, no comments"

class PromptRequest(BaseModel):
    user_id: str
    prompt: str            # Matches 'prompt' sent from your Extension
    platform: Optional[str] = "unknown"

# --- 4. HELPER FUNCTIONS ---

def get_embedding(text: str):
    """Converts text to 384-dim vector using free MiniLM model (sentence-transformers). Returns None if unavailable."""
    global EMBEDDING_MODEL, _embedding_unavailable
    if _embedding_unavailable:
        return None
    if EMBEDDING_MODEL is None:
        try:
            from sentence_transformers import SentenceTransformer
            print("⏳ Loading free embedding model (all-MiniLM-L6-v2)...")
            # Prefer ONNX backend (lighter, CPU-friendly); fallback to default
            try:
                EMBEDDING_MODEL = SentenceTransformer(EMBEDDING_MODEL_NAME, backend="onnx")
                print("✅ Embedding model loaded (ONNX backend)")
            except Exception:
                EMBEDDING_MODEL = SentenceTransformer(EMBEDDING_MODEL_NAME)
                print("✅ Embedding model loaded (default backend)")
        except Exception as e:
            _embedding_unavailable = True
            print(f"⚠️ Embedding unavailable: {e} — install: pip install sentence-transformers (or sentence-transformers[onnx] for CPU)")
            return None
    return EMBEDDING_MODEL.encode(text, convert_to_numpy=True).tolist()

def retrieve_context(user_id: str, query_text: str, limit: int = 3):
    """
    Finds similar past prompts and returns both the text context AND the highest similarity score.
    Returns: (context_str, max_score)
    """
    global qdrant
    qdrant = init_qdrant()
    
    # Default return values if DB is down or empty
    if qdrant is None:
        return "No relevant past context found.", 0.0

    query_vector = get_embedding(query_text)
    if query_vector is None:
        return "No relevant past context found.", 0.0

    # Search with User ID Filter
    results = qdrant.search(
        collection_name=COLLECTION_NAME,
        query_vector=query_vector,
        query_filter=Filter(
            must=[
                FieldCondition(
                    key="user_id",
                    match=MatchValue(value=user_id)
                )
            ]
        ),
        limit=limit
    )
    
    print(f"\n🔍 Searching Memory for User '{user_id}'...")
    
    context_str = ""
    max_score = 0.0  # Track the highest score found
    
    for hit in results:
        # Update max_score if this hit is higher
        if hit.score > max_score:
            max_score = hit.score

        payload = hit.payload
        print(f"   Found candidate (Score: {hit.score:.4f}): {payload.get('original_prompt')}")
        
        # Only add to string if it passes the "relevance" threshold (0.25)
        if hit.score > 0.25:
            context_str += f"- Past Prompt: \"{payload.get('original_prompt')}\"\n"
            context_str += f"- Refined Version: \"{payload.get('refined_prompt')}\"\n\n"
            
    final_context = context_str if context_str else "No relevant past context found."
    
    return final_context, max_score

# --- 5. API ENDPOINTS ---

@app.get("/")
def health_check():
    return {"status": "running", "service": "Context-Aware Prompt Engine"}

@app.post("/users/register")
def register_user(profile: UserProfile):
    """Creates or updates a user profile."""
    if users_col is not None:
        users_col.update_one(
            {"user_id": profile.user_id},
            {"$set": profile.dict()},
            upsert=True,
        )
    else:
        _in_memory_users[profile.user_id] = profile.dict()
    return {"message": f"User {profile.user_id} registered successfully."}

@app.post("/enhance")
def enhance_prompt(request: PromptRequest):
    """
    The Master Logic: 
    1. Identify User (MongoDB)
    2. Retrieve Context & Similarity Score (Qdrant)
    3. Engineer Prompt (Groq + CO-STAR)
    4. Log Interaction (MongoDB)
    5. Learn/Memorize (Qdrant - conditionally)
    """
    start_time = time.time()
    
    print(f"📥 Received prompt from {request.user_id}: {request.prompt[:50]}...")

    # --- PHASE 1: IDENTIFY USER & PREFERENCES ---
    # We fetch the user's specific tech stack (e.g., "Python, React") to tailor the output.
    user_data = None
    if users_col is not None:
        try:
            user_data = users_col.find_one({"user_id": request.user_id})
        except Exception as e:
            print(f"⚠️ MongoDB read failed: {e}")
    
    # Fallback to in-memory if MongoDB failed or is empty
    if user_data is None:
        user_data = _in_memory_users.get(request.user_id)

    # Set defaults if user is brand new
    if not user_data:
        tech_stack = "General Programming"
        preferences = "Follow industry best practices."
    else:
        # specific handling to ensure list conversion works
        ts = user_data.get("tech_stack", [])
        if isinstance(ts, list):
            tech_stack = ", ".join(ts)
        else:
            tech_stack = str(ts)
        preferences = user_data.get("preferences", "Standard best practices")


    # --- PHASE 2: RETRIEVE CONTEXT (SINGLE PASS) ---
    # We retrieve BOTH the text history AND the max similarity score.
    # This score determines if we need to save this prompt later.
    past_context, max_similarity = retrieve_context(request.user_id, request.prompt)


    # --- PHASE 3: CONSTRUCT THE AI SYSTEM PROMPT ---
    # This uses the CO-STAR framework to force the AI to be "Elite".
    system_message = (
        "You are an elite Prompt Engineer and Intent Optimizer.\n"
        "Your goal is to transform the user's raw input into a high-precision LLM prompt.\n\n"
        "### DECISION LOGIC:\n"
        "1. PASS-THROUGH: If input is conversational ('Hi', 'Thanks'), return AS-IS.\n"
        "2. ENGINEER: If input is a request for Code or Reasoning, rewrite it using the **CO-STAR Framework**:\n"
        "   - Context: Define the role (User Profile: " + tech_stack + ").\n"
        "   - Objective: Clear, actionable goal.\n"
        "   - Style: " + preferences + ".\n"
        "   - Tone: Professional & Technical.\n"
        "   - Audience: Expert LLM.\n"
        "   - Response: Format (e.g., Code Block, Markdown).\n\n"
        "### CRITICAL RULES:\n"
        "- **Context Injection:** Use the provided SESSION MEMORY to maintain continuity.\n"
        "- **No Hallucinations:** Do not invent facts.\n"
        "- **Output:** Return ONLY the final refined prompt text. No explanations."
    )
    
    user_message = f"""
    ### 1. SESSION MEMORY (Context from previous turns)
    {past_context}

    ### 2. RAW USER INPUT
    "{request.prompt}"

    ### TASK:
    Rewrite the "Raw User Input" into a superior prompt using the System Guidelines.
    """


    # --- PHASE 4: GENERATE (Groq AI) ---
    enhanced_prompt = request.prompt # Fallback to original
    try:
        client = get_groq_client()
        if client is None:
            raise HTTPException(status_code=500, detail="Groq client failed to initialize")
        
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.3
        )
        enhanced_prompt = chat_completion.choices[0].message.content
    except Exception as e:
        print(f"❌ Groq API Error: {e}")
        # We continue even if AI fails, returning the original prompt so the user isn't blocked.


    # --- PHASE 5: LOGGING (MongoDB) ---
    # We always log the attempt for analytics/debugging
    log_id = "memory-only"
    if prompts_col is not None:
        try:
            log_entry = {
                "user_id": request.user_id,
                "timestamp": datetime.now(),
                "platform": request.platform,
                "original_input": request.prompt,
                "enhanced_output": enhanced_prompt,
                "context_used": past_context,
                "similarity_score": max_similarity, # Useful to debug
                "latency_sec": round(time.time() - start_time, 2),
            }
            result = prompts_col.insert_one(log_entry)
            log_id = str(result.inserted_id)
        except Exception as e:
            print(f"⚠️ MongoDB log write failed: {e}")


    # --- PHASE 6: SMART MEMORY STORAGE (Qdrant) ---
    # We only save if the prompt is unique (redundancy check).
    try:
        # THRESHOLD CHECK: 
        # If the prompt is >87% similar to an existing one, we assume it's a duplicate/retry.
        if max_similarity > 0.87:
            print(f"♻️ Redundancy Detected (Score: {max_similarity:.4f}). Skipping save.")
        else:
            vec = get_embedding(request.prompt)
            if vec is not None:
                q_client = init_qdrant()
                if q_client:
                    q_client.upsert(
                        collection_name=COLLECTION_NAME,
                        points=[
                            PointStruct(
                                id=int(time.time()), # Simple timestamp ID
                                vector=vec,
                                payload={
                                    "user_id": request.user_id,
                                    "original_prompt": request.prompt,
                                    "refined_prompt": enhanced_prompt
                                }
                            )
                        ]
                    )
                    print(f"💾 Memory Saved (New unique prompt).")
    except Exception as e:
        print(f"⚠️ Warning: Failed to save to Qdrant: {e}")

    # --- RETURN ---
    return {
        "original": request.prompt,
        "enhanced": enhanced_prompt,
        "log_id": log_id,
    }

    
# Run with: uvicorn main:app --reload