
from groq import Groq
from sentence_transformers import SentenceTransformer
from ..core.config import settings

# Global singletons
_embedding_model = None
_groq_client = None
_embedding_unavailable = False

def get_groq_client():
    """Lazily initialize Groq client."""
    global _groq_client
    if _groq_client is None:
        try:
            _groq_client = Groq(api_key=settings.GROQ_API_KEY)
        except Exception as e:
            print(f"⚠️ Warning: Groq client initialization failed: {e}")
    return _groq_client

def get_embedding(text: str):
    """Converts text to vector using free MiniLM model."""
    global _embedding_model, _embedding_unavailable
    
    if _embedding_unavailable:
        return None
        
    if _embedding_model is None:
        try:
            print("⏳ Loading free embedding model...")
            try:
                # Try ONNX for performance
                _embedding_model = SentenceTransformer(settings.EMBEDDING_MODEL_NAME, backend="onnx")
                print("✅ Embedding model loaded (ONNX backend)")
            except Exception:
                _embedding_model = SentenceTransformer(settings.EMBEDDING_MODEL_NAME)
                print("✅ Embedding model loaded (default backend)")
        except Exception as e:
            _embedding_unavailable = True
            print(f"⚠️ Embedding unavailable: {e}")
            return None
            
    return _embedding_model.encode(text, convert_to_numpy=True).tolist()
