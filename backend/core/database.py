
from pymongo import MongoClient
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance
from .config import settings

#MongoDB
class MongoDB:
    client: MongoClient = None
    db = None
    users_col = None
    prompts_col = None
    
    @classmethod
    def connect(cls):
        try:
            cls.client = MongoClient(
                settings.MONGO_URI or "mongodb://localhost:27017",
                serverSelectionTimeoutMS=3000,
            )
            cls.client.admin.command("ping")
            cls.db = cls.client["prompt_engine_db"]
            cls.users_col = cls.db["users"]
            cls.prompts_col = cls.db["prompt_logs"]

            # 1. Index for Users: Ensures fast lookups and unique user_ids
            cls.users_col.create_index("user_id", unique=True)

            # 2. Index for Logs: Speed up finding a user's history sorted by time
            #    This matches your query: .find({"user_id": ...}).sort("timestamp", -1)
            cls.prompts_col.create_index([("user_id", 1), ("timestamp", -1)])
            
            print("✅ MongoDB Indexes Verified")

            print("✅ MongoDB Connected")
        except Exception as e:
            print(f"⚠️ MongoDB not available ({e}) — using in-memory fallback.")
            cls.users_col = None
            cls.prompts_col = None

# Qdrant
class QdrantDB:
    client: QdrantClient = None
    
    @classmethod
    def get_client(cls):
        if cls.client is None:
            try:
                cls.client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)
                
                # Check/Create Collection
                try:
                    if not cls.client.collection_exists(settings.COLLECTION_NAME):
                        cls.client.create_collection(
                            collection_name=settings.COLLECTION_NAME,
                            vectors_config=VectorParams(size=384, distance=Distance.COSINE),
                        )
                        print(f"✅ Created new Qdrant collection: '{settings.COLLECTION_NAME}'")
                except Exception:
                    # Fallback check
                    try:
                        cls.client.get_collection(settings.COLLECTION_NAME)
                    except:
                        pass # Creation might have failed or raced
                
                # Create Payload Index
                try:
                    cls.client.create_payload_index(
                        collection_name=settings.COLLECTION_NAME,
                        field_name="user_id",
                        field_schema="keyword"
                    )
                except Exception:
                    pass
                
                print(f"✅ Qdrant Connected ({settings.QDRANT_URL})")
            except Exception as e:
                print(f"❌ Qdrant Connection Failed: {e}")
                return None
        return cls.client

# In-Memory Fallbacks
in_memory_users = {}
in_memory_prompt_logs = []
