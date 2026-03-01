
import time as _time
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from .core.database import MongoDB
from .routers import auth, users, prompts, saved_prompts

# Rate limiter (shared across routers)
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="Context-Aware Prompt Engine")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── REQUEST LOGGING MIDDLEWARE ──
# Prints every request to the terminal so you can see what's being hit
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = _time.time()
    method = request.method
    path = request.url.path
    origin = request.headers.get("origin", "direct")

    print(f"\n{'='*60}")
    print(f"📥 {method} {path}")
    print(f"   Origin: {origin}")

    try:
        response = await call_next(request)
        duration = round((_time.time() - start) * 1000)
        status = response.status_code

        emoji = "✅" if status < 400 else "⚠️" if status < 500 else "❌"
        print(f"   {emoji} Status: {status}  |  ⏱ {duration}ms")
        print(f"{'='*60}")
        return response
    except Exception as e:
        duration = round((_time.time() - start) * 1000)
        print(f"   ❌ ERROR: {e}  |  ⏱ {duration}ms")
        print(f"{'='*60}")
        raise

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Startup Events
@app.on_event("startup")
def startup_db_client():
    MongoDB.connect()
    # Pre-load embedding model to eliminate first-request cold start
    try:
        from .services.llm_service import preload_embedding_model
        preload_embedding_model()
    except Exception as e:
        print(f"⚠️ Embedding preload skipped: {e}")

    print(f"\n{'='*60}")
    print(f"🚀 Prompt Memory v4.0 — Server Ready!")
    print(f"   http://localhost:8000")
    print(f"   Docs: http://localhost:8000/docs")
    print(f"{'='*60}\n")

@app.get("/")
def health_check():
    return {"status": "running", "service": "Context-Aware Prompt Engine", "version": "4.0"}

# Include Routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(prompts.router)
app.include_router(saved_prompts.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
