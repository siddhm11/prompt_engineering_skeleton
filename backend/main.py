import os
import time
from datetime import datetime
from typing import List, Optional

# Third-party libraries
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, Distance, VectorParams
# Lazy import: from sentence_transformers import SentenceTransformer
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

# Basic check to ensure keys are present
if not GROQ_API_KEY:
    raise ValueError("❌ ERROR: GROQ_API_KEY is missing from .env file!")

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

# C. MongoDB (User Profiles & Logs)
try:
    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client["prompt_engine_db"]
    users_col = db["users"]
    prompts_col = db["prompt_logs"]
    print("✅ MongoDB Connected")
except Exception as e:
    print(f"❌ MongoDB Connection Failed: {e}")

# D. Qdrant (Vector Memory)
qdrant = None
COLLECTION_NAME = "prompt_memory"

def init_qdrant():
    """Lazily initialize Qdrant connection."""
    global qdrant
    if qdrant is None:
        try:
            qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
            # Try to check if collection exists, with fallback for version compatibility
            try:
                collection_exists = qdrant.collection_exists(COLLECTION_NAME)
            except (AttributeError, Exception):
                # Fallback: try to get_collection, if it fails, collection doesn't exist
                try:
                    qdrant.get_collection(COLLECTION_NAME)
                    collection_exists = True
                except:
                    collection_exists = False
            
            if not collection_exists:
                try:
                    qdrant.create_collection(
                        collection_name=COLLECTION_NAME,
                        vectors_config=VectorParams(size=384, distance=Distance.COSINE),
                    )
                except Exception as e:
                    # Handle 409 Conflict: collection already exists
                    if "409" in str(e) or "already exists" in str(e):
                        print(f"✅ Qdrant Collection '{COLLECTION_NAME}' already exists")
                    else:
                        raise
            print(f"✅ Qdrant Connected ({QDRANT_URL})")
        except Exception as e:
            print(f"❌ Qdrant Connection Failed: {e}")
    return qdrant

# E. AI Models
print("Embedding model will be loaded lazily on first use")
EMBEDDING_MODEL = None

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
    """Converts text to vector. Lazily loads the embedding model on first call."""
    global EMBEDDING_MODEL
    if EMBEDDING_MODEL is None:
        try:
            from sentence_transformers import SentenceTransformer
            print("⏳ Loading Embedding Model...")
            EMBEDDING_MODEL = SentenceTransformer('all-MiniLM-L6-v2')
            print("✅ Embedding Model Loaded")
        except Exception as e:
            raise RuntimeError(f"Failed to load embedding model: {e}")
    return EMBEDDING_MODEL.encode(text).tolist()

def retrieve_context(user_id: str, query_text: str, limit: int = 3):
    """Finds similar past prompts."""
    global qdrant
    qdrant = init_qdrant()  # Ensure Qdrant is initialized
    
    if qdrant is None:
        return "No relevant past context found."
    
    query_vector = get_embedding(query_text)
    
    # Use search method compatible with qdrant-client v1.16.2
    results = qdrant.search(
        collection_name=COLLECTION_NAME,
        query_vector=query_vector,
        limit=limit
    )
    
    context_str = ""
    for hit in results:
        if hit.score > 0.25:  # Relevance threshold
            payload = hit.payload
            # Only use context if it matches the user (simple filter)
            if payload.get("user_id") == user_id:
                context_str += f"- Past Prompt: \"{payload.get('original_prompt')}\"\n"
                context_str += f"- Refined Version: \"{payload.get('refined_prompt')}\"\n\n"
            
    return context_str if context_str else "No relevant past context found."

# --- 5. API ENDPOINTS ---

@app.get("/")
def health_check():
    return {"status": "running", "service": "Context-Aware Prompt Engine"}

@app.post("/users/register")
def register_user(profile: UserProfile):
    """Creates or updates a user profile."""
    users_col.update_one(
        {"user_id": profile.user_id}, 
        {"$set": profile.dict()}, 
        upsert=True
    )
    return {"message": f"User {profile.user_id} registered successfully."}

@app.post("/enhance")
def enhance_prompt(request: PromptRequest):
    """The main logic: Retrieve -> Refine -> Store"""
    start_time = time.time()
    
    print(f"📥 Received prompt from {request.user_id}: {request.prompt[:50]}...")

    # 1. Fetch User Profile (MongoDB)
    user_data = users_col.find_one({"user_id": request.user_id})
    
    # Default fallback if user not found
    if not user_data:
        tech_stack = "General Programming"
        preferences = "Standard best practices"
    else:
        tech_stack = ", ".join(user_data.get("tech_stack", []))
        preferences = user_data.get("preferences", "")

    # 2. Retrieve Context (Qdrant)
    past_context = retrieve_context(request.user_id, request.prompt)

    # # 3. Construct System Prompt
    # system_prompt = f"""
    # You are an expert Technical Prompt Engineer.
    # USER PROFILE: {tech_stack}
    # PREFERENCES: {preferences}
    
    # PAST CONTEXT (Learn from this style):
    # {past_context}
    
    # TASK: Convert the VAGUE INPUT into a detailed, professional technical prompt.
    # RETURN ONLY THE REFINED PROMPT TEXT. NO EXPLANATIONS.
    # """
    
    # system_message = (
    #     "You are an expert Prompt Engineer. Refine the user's prompt to be precise and actionable.\n"
    #     "RULES:\n"
    #     "1. USER INPUT IS KING: If input contradicts memory, ignore memory.\n"
    #     "2. USE GLOBAL PROFILE: Apply coding style preferences.\n"
    #     "3. NO HALLUCINATIONS: Do not invent constraints.\n"
    #     "4. OUTPUT: Return ONLY the refined prompt text."
    # )

    # --- UPGRADED SYSTEM MESSAGE ---
    # This prompt forces the model to choose: "Pass-through" vs. "Engineer"
    system_message = (
        "You are an elite Prompt Engineer and Intent Optimizer.\n"
        "Your goal is to transform the user's raw input into a high-precision LLM prompt, "
        "but ONLY when necessary to improve performance.\n\n"
        "### DECISION LOGIC:\n"
        "1. **PASS-THROUGH (Low Complexity):** If the input is conversational (e.g., 'Hi', 'Thanks') "
        "or a simple fact lookup (e.g., 'Capital of France?'), return it AS-IS. Do not over-engineer.\n"
        "2. **ENGINEER (High Complexity):** If the input is a request for Code, Content Creation, "
        "Complex Reasoning, or Analysis, rewrite it using the **CO-STAR Framework**:\n"
        "   - **C**ontext: Define the role and situation.\n"
        "   - **O**bjective: Clear, actionable goal.\n"
        "   - **S**tyle: Specific coding style or writing voice (use Global Profile if relevant).\n"
        "   - **T**one: The attitude of the response.\n"
        "   - **A**udience: Who is this for?\n"
        "   - **R**esponse: Format (JSON, Markdown, Code Block).\n\n"
        "### CRITICAL RULES:\n"
        "- **Context Injection:** If past history is relevant, weave it into the 'Context' section.\n"
        "- **No Hallucinations:** Do not invent facts not present in the input or memory.\n"
        "- **Output:** Return ONLY the final prompt text. No explanations."
    )
    
    # --- UPGRADED USER MESSAGE ---
    # Presents the data clearly and forces the "Optimization" task
    user_message = f"""
    ### 1. USER GLOBAL PREFERENCES

    ### 2. SESSION CONTEXT (Memory)
    {past_context}

    ### 3. RAW USER INPUT
    "{request.prompt}"

    ### TASK:
    Evaluate the "Raw User Input". If it requires engineering, rewrite it using CO-STAR. If it is simple, output it unchanged.
    """
    
    # 4. Call Groq AI
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
        raise HTTPException(status_code=500, detail=f"Groq API Error: {str(e)}")
    
    # 5. Save Logs (MongoDB)
    log_entry = {
        "user_id": request.user_id,
        "timestamp": datetime.now(),
        "platform": request.platform,
        "original_input": request.prompt,
        "enhanced_output": enhanced_prompt,
        "context_used": past_context,
        "latency_sec": round(time.time() - start_time, 2)
    }
    prompts_col.insert_one(log_entry)
    
    # 6. Update Memory (Qdrant)
    # We save the interaction so the system learns for next time
    try:
        q_client = init_qdrant()
        if q_client:
            q_client.upsert(
                collection_name=COLLECTION_NAME,
                points=[
                    PointStruct(
                        id=int(time.time()), 
                        vector=get_embedding(request.prompt),
                        payload={
                            "user_id": request.user_id,
                            "original_prompt": request.prompt,
                            "refined_prompt": enhanced_prompt
                        }
                    )
                ]
            )
    except Exception as e:
        print(f"⚠️ Warning: Failed to save to Qdrant: {e}")

    # 7. Return to Frontend
    return {
        "original": request.prompt,
        "enhanced": enhanced_prompt,
        "log_id": str(log_entry.get("_id"))
    }

# Run with: uvicorn main:app --reload