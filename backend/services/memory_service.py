
import time
import uuid
from datetime import datetime
from typing import List, Tuple, Optional
from qdrant_client.models import PointStruct, Filter, FieldCondition, MatchValue
from ..core.config import settings
from ..core.database import QdrantDB, MongoDB, in_memory_prompt_logs, in_memory_saved_prompts
from ..services.llm_service import get_embedding

class MemoryService:

    # =========================================================================
    # PASSIVE TRACKING (existing — searches the original prompt_memory collection)
    # =========================================================================

    @staticmethod
    def retrieve_context(user_id: str, query_text: str, limit: int = 3) -> Tuple[str, float]:
        """
        Finds similar past prompts from PASSIVE tracking.
        Returns: (context_str, max_score)
        """
        qdrant = QdrantDB.get_client()
        
        if qdrant is None:
            return "No relevant past context found.", 0.0

        query_vector = get_embedding(query_text)
        if query_vector is None:
            return "No relevant past context found.", 0.0

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
            if hit.score > 0.25:
                context_str += f"- Past Prompt: \"{payload.get('original_prompt')}\"\n"
                context_str += f"- Refined Version: \"{payload.get('refined_prompt')}\"\n\n"
                
        final_context = context_str if context_str else "No relevant past context found."
        return final_context, max_score

    @staticmethod
    def get_recent_prompts(user_id: str, limit: int = 5) -> List[str]:
        """Fetches most recent prompts from passive log."""
        recent_prompts = []
        
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
        """Saves high-quality prompts to passive tracking Vector DB."""
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

    # =========================================================================
    # SAVED PROMPTS (new — searches the saved_prompt_vectors collection)
    # =========================================================================

    @staticmethod
    def search_saved_prompts(user_id: str, query_text: str, limit: int = 5, exclude_ids: Optional[List[str]] = None) -> List[dict]:
        """
        Semantic search ONLY against the user's saved prompts.
        Returns list of dicts: [{mongo_id, content, title, tags, score}, ...]
        Excludes any IDs in exclude_ids (already selected by user).
        """
        qdrant = QdrantDB.get_client()
        if qdrant is None:
            return []

        query_vector = get_embedding(query_text)
        if query_vector is None:
            return []

        try:
            results = qdrant.search(
                collection_name=QdrantDB.SAVED_COLLECTION,
                query_vector=query_vector,
                query_filter=Filter(
                    must=[
                        FieldCondition(key="user_id", match=MatchValue(value=user_id))
                    ]
                ),
                limit=limit + (len(exclude_ids) if exclude_ids else 0),
            )
        except Exception as e:
            print(f"⚠️ Saved prompts search failed: {e}")
            return []

        exclude_set = set(exclude_ids or [])
        matched = []
        for hit in results:
            mongo_id = hit.payload.get("mongo_id", "")
            if mongo_id in exclude_set:
                continue
            if hit.score < 0.20:
                continue
            matched.append({
                "mongo_id": mongo_id,
                "content": hit.payload.get("content", ""),
                "title": hit.payload.get("title", ""),
                "tags": hit.payload.get("tags", []),
                "score": round(hit.score, 3),
            })
            if len(matched) >= limit:
                break

        return matched

    @staticmethod
    def embed_saved_prompt(user_id: str, mongo_id: str, content: str, title: str = "", tags: list = None):
        """Embed a saved prompt into the saved_prompt_vectors Qdrant collection."""
        try:
            vec = get_embedding(content)
            if vec:
                q_client = QdrantDB.get_client()
                if q_client:
                    # Use a deterministic numeric ID from the mongo_id hash
                    point_id = abs(hash(mongo_id)) % (2**63)
                    q_client.upsert(
                        collection_name=QdrantDB.SAVED_COLLECTION,
                        points=[PointStruct(
                            id=point_id,
                            vector=vec,
                            payload={
                                "user_id": user_id,
                                "mongo_id": mongo_id,
                                "content": content,
                                "title": title or "",
                                "tags": tags or [],
                            }
                        )]
                    )
                    print(f"💾 Saved prompt embedded (id={mongo_id})")
        except Exception as e:
            print(f"❌ Saved prompt embedding failed: {e}")

    @staticmethod
    def delete_saved_prompt_vector(mongo_id: str):
        """Remove a saved prompt's vector from Qdrant."""
        try:
            q_client = QdrantDB.get_client()
            if q_client:
                point_id = abs(hash(mongo_id)) % (2**63)
                q_client.delete(
                    collection_name=QdrantDB.SAVED_COLLECTION,
                    points_selector=[point_id],
                )
                print(f"🗑️ Saved prompt vector deleted (id={mongo_id})")
        except Exception as e:
            print(f"⚠️ Could not delete saved prompt vector: {e}")
