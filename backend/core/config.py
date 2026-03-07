import os
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)


class Settings:
    # API Keys
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    GROQ_API_KEY_2 = os.getenv("GROQ_API_KEY_2")
    MONGO_URI = os.getenv("MONGO_URI")
    QDRANT_URL = os.getenv("QDRANT_URL", ":memory:")
    QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
    SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
    
    # Auth
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
    GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "https://siddhm11-prompt-engine.hf.space/auth/google/callback")
    JWT_SECRET = os.getenv("JWT_SECRET", "unsafedefaultsecret")
    ALGORITHM = "HS256"
    
    # Constants
    EMBEDDING_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    COLLECTION_NAME = "prompt_memory"

    # Rate Limiting
    RATE_LIMIT_ENHANCE = os.getenv("RATE_LIMIT_ENHANCE", "30/minute")
    RATE_LIMIT_VOICE = os.getenv("RATE_LIMIT_VOICE", "10/minute")

settings = Settings()
