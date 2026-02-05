import os
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)



class Settings:
    # API Keys
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    MONGO_URI = os.getenv("MONGO_URI")
    QDRANT_URL = os.getenv("QDRANT_URL", ":memory:")
    QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
    SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
    
    # Auth
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
    JWT_SECRET = os.getenv("JWT_SECRET", "unsafedefaultsecret")
    ALGORITHM = "HS256"
    
    # Constants
    EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
    COLLECTION_NAME = "prompt_memory"

settings = Settings()
