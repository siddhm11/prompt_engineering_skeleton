
import time
from datetime import datetime
from typing import List, Tuple
from qdrant_client.models import PointStruct, Filter, FieldCondition, MatchValue
from ..core.config import settings
from ..core.database import QdrantDB, MongoDB, in_memory_prompt_logs
from ..services.llm_service import get_embedding

class MemoryService:
    @staticmethod
    def retrieve_context(user_id: str, query_text: str, limit: int = 3) -> Tuple[str, float]:
        """
        Finds similar past prompts.
        Returns: (context_str, max_score)
        """
        qdrant = QdrantDB.get_client()
        
        # Default return if DB is down
        if qdrant is None:
            return "No relevant past context found.", 0.0

        query_vector = get_embedding(query_text)
        if query_vector is None:
            return "No relevant past context found.", 0.0

        # Search with User ID Filter
        try:
            results = qdrant.search(
                collection_name=settings.COLLECTION_NAME,
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
        except Exception as e:
            print(f"⚠️ Search failed: {e}")
            return "No relevant past context found.", 0.0
        
        context_str = ""
        max_score = 0.0
        
        for hit in results:
            if hit.score > max_score:
                max_score = hit.score

            payload = hit.payload
            # Relevance threshold
            if hit.score > 0.25:
                context_str += f"- Past Prompt: \"{payload.get('original_prompt')}\"\n"
                context_str += f"- Refined Version: \"{payload.get('refined_prompt')}\"\n\n"
                
        final_context = context_str if context_str else "No relevant past context found."
        return final_context, max_score

    @staticmethod
    def get_recent_prompts(user_id: str, limit: int = 5) -> List[str]:
        """Fetches most recent prompts."""
        recent_prompts = []
        
        # 1. Try MongoDB
        if MongoDB.prompts_col is not None:
            try:
                cursor = MongoDB.prompts_col.find(
                    {"user_id": user_id}
                ).sort("timestamp", -1).limit(limit)
                
                for doc in cursor:
                    if "original" in doc:
                        recent_prompts.append(doc["original"])
            except Exception as e:
                print(f"⚠️ Error fetching recent prompts from Mongo: {e}")

        # 2. Fallback to In-Memory
        if MongoDB.prompts_col is None:
            user_logs = [log for log in in_memory_prompt_logs if log.get("user_id") == user_id]
            recent_prompts = [log["original"] for log in user_logs[-limit:]]
            recent_prompts.reverse()
            
        return recent_prompts

    @staticmethod
    def log_prompt(user_id: str, original: str, enhanced: str = None, score: float = 0.0, latency: float = 0.0, source: str = "active"):
        """Logs prompt to Mongo or Memory."""
        log_entry = {
            "user_id": user_id,
            "timestamp": datetime.now(),
            "original": original,
            "enhanced": enhanced,
            "score": score,
            "latency": latency,
            "source": source
        }
        
        log_id = "memory-only"
        if MongoDB.prompts_col is not None:
            try:
                res = MongoDB.prompts_col.insert_one(log_entry)
                log_id = str(res.inserted_id)
            except: pass
        else:
            in_memory_prompt_logs.append(log_entry)
        
        return log_id

    @staticmethod
    def memorize_strategy(user_id: str, original: str, refined: str):
        """Saves high-quality prompts to Vector DB."""
        try:
            vec = get_embedding(original)
            if vec:
                q_client = QdrantDB.get_client()
                if q_client:
                    q_client.upsert(
                        collection_name=settings.COLLECTION_NAME,
                        points=[PointStruct(
                            id=int(time.time()),
                            vector=vec,
                            payload={
                                "user_id": user_id, 
                                "original_prompt": original, 
                                "refined_prompt": refined
                            }
                        )]
                    )
                    print("💾 New strategy memorized.")
        except Exception as e:
            print(f"❌ Memorization failed: {e}")
