# ────────────────────────────── utils/rag.py ──────────────────────────────
import os
import math
from typing import List, Dict, Any, Optional
from pymongo import MongoClient, ASCENDING, TEXT
from pymongo.collection import Collection
from pymongo.errors import PyMongoError
import numpy as np
from .logger import get_logger

VECTOR_DIM = 384  # all-MiniLM-L6-v2
INDEX_NAME = os.getenv("MONGO_VECTOR_INDEX", "vector_index")
USE_ATLAS_VECTOR = os.getenv("ATLAS_VECTOR", "0") == "1"
logger = get_logger("RAG", __name__)



class RAGStore:
    def __init__(self, mongo_uri: str, db_name: str = "studybuddy"):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.chunks: Collection = self.db["chunks"]
        self.files: Collection = self.db["files"]

    # ── Write ────────────────────────────────────────────────────────────────
    def store_cards(self, cards: List[Dict[str, Any]]):
        if not cards:
            return
        for c in cards:
            # basic validation
            emb = c.get("embedding")
            if not emb or len(emb) != VECTOR_DIM:
                raise ValueError("Invalid embedding length; expected %d" % VECTOR_DIM)
        self.chunks.insert_many(cards, ordered=False)
        logger.info(f"Inserted {len(cards)} cards into MongoDB")

    def upsert_file_summary(self, user_id: str, filename: str, summary: str):
        self.files.update_one(
            {"user_id": user_id, "filename": filename},
            {"$set": {"summary": summary}},
            upsert=True
        )
        logger.info(f"Upserted summary for {filename} (user {user_id})")

    # ── Read ────────────────────────────────────────────────────────────────
    def list_cards(self, user_id: str, filename: Optional[str], limit: int, skip: int):
        q = {"user_id": user_id}
        if filename:
            q["filename"] = filename
        cur = self.chunks.find(q, {"embedding": 0}).skip(skip).limit(limit).sort([("_id", ASCENDING)])
        return list(cur)

    def list_files(self, user_id: str) -> List[Dict[str, Any]]:
        cur = self.files.find({"user_id": user_id}, {"_id": 0})
        return list(cur)

    def get_file_summary(self, user_id: str, filename: str):
        return self.files.find_one({"user_id": user_id, "filename": filename})

    def vector_search(self, user_id: str, query_vector: List[float], k: int = 6, filenames: Optional[List[str]] = None):
        if USE_ATLAS_VECTOR:
            # Atlas Vector Search (requires pre-created index on 'embedding')
            pipeline = [
                {
                    "$search": {
                        "index": INDEX_NAME,
                        "knnBeta": {
                            "vector": query_vector,
                            "path": "embedding",
                            "k": k,
                        },
                        "filter": {"equals": {"path": "user_id", "value": user_id}},
                    }
                },
                {"$project": {"embedding": 0, "score": {"$meta": "searchScore"}, "doc": "$$ROOT"}},
            ]
            if filenames:
                pipeline.append({"$match": {"doc.filename": {"$in": filenames}}})
            pipeline.append({"$limit": k})
            hits = list(self.chunks.aggregate(pipeline))
            return [{"doc": h["doc"], "score": h["score"]} for h in hits]
        # Fallback: scan limited sample and compute cosine locally
        else:
            q = {"user_id": user_id}
            # Apply filename filter if provided
            if filenames:
                q["filename"] = {"$in": filenames}
            # Scan limited sample and compute cosine locally    
            sample = list(self.chunks.find(q).limit(max(2000, k*10)))
            # If no sample, return empty list       
            if not sample:
                return []
            # Compute cosine similarity for each sample
            qv = np.array(query_vector, dtype="float32")
            scores = [] 
            # Compute cosine similarity for each sample
            for d in sample:
                v = np.array(d.get("embedding", [0]*VECTOR_DIM), dtype="float32")
                denom = (np.linalg.norm(qv) * np.linalg.norm(v)) or 1.0
                sim = float(np.dot(qv, v) / denom)
                scores.append((sim, d))
            # Sort scores by cosine similarity in descending order  
            scores.sort(key=lambda x: x[0], reverse=True)
            # Get top k sc ores
            top = scores[:k]
            # Log the results
            logger.info(f"Vector search sample={len(sample)} returned top={len(top)}")
            return [{"doc": d, "score": s} for (s, d) in top]


def ensure_indexes(store: RAGStore):
    # Basic text index for fallback keyword search (optional)
    try:
        store.chunks.create_index([("user_id", ASCENDING), ("filename", ASCENDING)])
        store.chunks.create_index([("content", TEXT), ("topic_name", TEXT), ("summary", TEXT)], name="text_idx")
        store.files.create_index([("user_id", ASCENDING), ("filename", ASCENDING)], unique=True)
    except PyMongoError as e:
        logger.warning(f"Index creation warning: {e}")
    # Note: For Atlas Vector, create an Atlas Search index named INDEX_NAME on field "embedding" with vector options.
    # Example (in Atlas UI):
    # {
    #   "mappings": {
    #     "dynamic": false,
    #     "fields": {
    #       "embedding": {
    #         "type": "knnVector",
    #         "dimensions": 384,
    #         "similarity": "cosine"
    #       }
    #     }
    #   }
    # }