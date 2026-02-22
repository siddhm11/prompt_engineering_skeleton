
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .core.database import MongoDB
from .routers import auth, users, prompts, saved_prompts

app = FastAPI(title="Context-Aware Prompt Engine")

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

@app.get("/")
def health_check():
    return {"status": "running", "service": "Context-Aware Prompt Engine", "production_ready": True}

# Include Routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(prompts.router)
app.include_router(saved_prompts.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
