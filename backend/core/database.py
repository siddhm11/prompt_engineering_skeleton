
from pymongo import MongoClient
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance
from .config import settings

# MongoDB
class MongoDB:
    client: MongoClient = None
    db = None
    users_col = None
    prompts_col = None
    saved_prompts_col = None
    feedback_col = None
    
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
            cls.saved_prompts_col = cls.db["saved_prompts"]
            cls.feedback_col = cls.db["user_feedback"]

            # Indexes
            cls.users_col.create_index("user_id", unique=True)
            cls.prompts_col.create_index([("user_id", 1), ("timestamp", -1)])
            cls.saved_prompts_col.create_index("user_id")
            cls.feedback_col.create_index([("user_id", 1), ("timestamp", -1)])

            # get_user_feedback_summary() reads db["prompt_feedback"], which is a
            # DIFFERENT collection from feedback_col (db["user_feedback"]) above.
            # It was never indexed, so every /enhance ran an unindexed scan plus
            # an in-memory sort against it.
            cls.db["prompt_feedback"].create_index([("user_id", 1), ("timestamp", -1)])

            # Retention. Atlas M0 is 512 MB and nothing ever deleted a prompt
            # log, so the cluster filled and then failed writes silently.
            # expireAfterSeconds on a date field lets Mongo do the pruning.
            if settings.PROMPT_LOG_TTL_DAYS > 0:
                _ttl = settings.PROMPT_LOG_TTL_DAYS * 86400
                cls._ensure_ttl(cls.prompts_col, "timestamp", _ttl)
                cls._ensure_ttl(cls.db["prompt_feedback"], "timestamp", _ttl)

            print("✅ MongoDB Indexes Verified")
            print("✅ MongoDB Connected")
        except Exception as e:
            print(f"⚠️ MongoDB not available ({e}) — using in-memory fallback.")
            # db and client must be cleared too. Leaving them set produced a
            # split brain: feedback writes (which test `MongoDB.db is not None`)
            # kept targeting a dead client while everything else fell back to
            # RAM, so the two halves of a request disagreed about reality.
            cls.client = None
            cls.db = None
            cls.users_col = None
            cls.prompts_col = None
            cls.saved_prompts_col = None
            cls.feedback_col = None

    @staticmethod
    def _ensure_ttl(col, field: str, seconds: int):
        """Create a TTL index, tolerating one that already exists with a different span."""
        try:
            col.create_index(field, expireAfterSeconds=seconds)
        except Exception as e:
            print(f"⚠️ TTL index on {col.name}.{field} skipped: {e}")

# Qdrant
class QdrantDB:
    client: QdrantClient = None
    _collections_ready = False
    
    SAVED_COLLECTION = "saved_prompt_vectors"
    
    @classmethod
    def get_client(cls):
        if cls.client is None:
            try:
                cls.client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)
                print(f"✅ Qdrant Connected ({settings.QDRANT_URL})")
            except Exception as e:
                print(f"❌ Qdrant Connection Failed: {e}")
                return None
        
        # Ensure collections exist (runs once per process)
        if not cls._collections_ready and cls.client is not None:
            cls._ensure_collection(settings.COLLECTION_NAME)
            cls._ensure_collection(cls.SAVED_COLLECTION)
            cls._collections_ready = True
        
        return cls.client

    @classmethod
    def _ensure_collection(cls, name: str):
        """Create a 384-dim cosine collection if it doesn't exist, with user_id index."""
        try:
            cls.client.get_collection(name)
            print(f"✔ Qdrant collection '{name}' ready")
        except Exception:
            # Collection doesn't exist — create it
            try:
                cls.client.create_collection(
                    collection_name=name,
                    vectors_config=VectorParams(size=384, distance=Distance.COSINE),
                )
                print(f"✅ Created Qdrant collection: '{name}'")
            except Exception as e:
                print(f"⚠️ Could not create collection '{name}': {e}")
                return
        
        # user_id is filtered on every search; mongo_id is filtered on every
        # delete now that deletion matches payload instead of recomputing a
        # point id. Both need a payload index.
        for field in ("user_id", "mongo_id"):
            try:
                cls.client.create_payload_index(
                    collection_name=name,
                    field_name=field,
                    field_schema="keyword",
                )
            except Exception:
                pass

    @classmethod
    def health(cls) -> dict:
        """
        Whether the vector store is actually usable, and what is in it.

        Saved-prompt search failed in production with no way to tell why from
        outside. The embedding model turned out to be fine, which left Qdrant —
        but "is it connected, do the collections exist, is anything in them"
        was unanswerable without shell access to the Space. Point counts are
        the decisive signal: an empty collection means writes never landed, a
        populated one means the query or its filter is at fault.

        Deliberately reports no URL or key.
        """
        out = {"connected": False, "collections": {}, "error": None}
        try:
            client = cls.get_client()
            if client is None:
                out["error"] = "client unavailable"
                return out
            out["connected"] = True
            for name in (settings.COLLECTION_NAME, cls.SAVED_COLLECTION):
                try:
                    info = client.get_collection(name)
                    out["collections"][name] = {
                        "exists": True,
                        "points": getattr(info, "points_count", None),
                    }
                except Exception as e:
                    out["collections"][name] = {"exists": False, "error": str(e)[:120]}
        except Exception as e:
            out["error"] = str(e)[:160]
        return out


# In-Memory Fallbacks
in_memory_users = {}
in_memory_prompt_logs = []
in_memory_saved_prompts = {}  # {prompt_id: {doc}}
