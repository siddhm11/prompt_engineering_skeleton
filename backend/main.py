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


@app.post("/enhance")
def enhance_prompt(request: PromptRequest):
    start_time = time.time()
    
    # 1. GET USER CONTEXT (MongoDB Priority)
    user_data = None
    if users_col is not None:
        user_data = users_col.find_one({"user_id": request.user_id})
    if user_data is None:
        user_data = _in_memory_users.get(request.user_id, {})

    # Defaults
    ts_raw = user_data.get("tech_stack", ["General Python", "Data Science"])
    tech_stack = ", ".join(ts_raw) if isinstance(ts_raw, list) else str(ts_raw)
    preferences = user_data.get("preferences", "Clean, modular code with docstrings.")
    
    # 2. RETRIEVE MEMORY
    past_context, max_similarity = retrieve_context(request.user_id, request.prompt)

    # 3. CONSTRUCT SOTA PROMPT
    formatted_system = SOTA_SYSTEM_PROMPT.format(
        tech_stack=tech_stack,
        preferences=preferences
    )

    user_message = f"""
    ### 1. MEMORY & PAST STRATEGIES
    {past_context}

    ### 2. RAW USER INPUT
    "{request.prompt}"

    ### 3. TASK
    Apply the 7 Rules. Transform the raw input into a SOTA prompt.
    Ensure you define a specific EXPERT ROLE and Negative Constraints.
    """

    enhanced_prompt = request.prompt # Fallback
    try:
        client = get_groq_client()
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": formatted_system},
                {"role": "user", "content": user_message}
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.3, # Low temp for precision
        )
        enhanced_prompt = chat_completion.choices[0].message.content
    except Exception as e:
        print(f"❌ Groq API Error: {e}")

    # 4. LOGGING (MongoDB)

    process_time = round(time.time() - start_time, 2) 
    log_id = "memory-only"
    if prompts_col is not None:
        try:
            log_entry = {
                "user_id": request.user_id,
                "timestamp": datetime.now(),
                "original": request.prompt,
                "enhanced": enhanced_prompt,
                "score": max_similarity,
                "latency": process_time            
            }
            res = prompts_col.insert_one(log_entry)
            log_id = str(res.inserted_id)
        except: pass    # <--- HANDLE ERRORS HERE

    # 5. MEMORY STORAGE (Qdrant)
    # Only save if unique (similarity < 0.90)
    if max_similarity < 0.90:
        try:
            vec = get_embedding(request.prompt)
            if vec:
                q_client = init_qdrant()
                if q_client:
                    q_client.upsert(
                        collection_name=COLLECTION_NAME,
                        points=[PointStruct(
                            id=int(time.time()),
                            vector=vec,
                            payload={"user_id": request.user_id, "original_prompt": request.prompt, "refined_prompt": enhanced_prompt}
                        )]
                    )
                    print("💾 New strategy memorized.")
        except: pass
    else:
        print(f"♻️ Redundancy detected (Score {max_similarity:.2f}). Skipping save.")

    return {
        "original": request.prompt,
        "enhanced": enhanced_prompt,
        "log_id": log_id,
        "latency": process_time
    }
    

# Run with: uvicorn main:app --reload

## change content.js as well 

