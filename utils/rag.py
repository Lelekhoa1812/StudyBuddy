# ────────────────────────────── utils/rag.py ──────────────────────────────
import os
import math
from typing import List, Dict, Any, Optional
from pymongo import MongoClient, ASCENDING, TEXT
from pymongo.collection import Collection
from pymongo.errors import PyMongoError
import numpy as np
import logging
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

    def upsert_file_summary(self, user_id: str, project_id: str, filename: str, summary: str):
        self.files.update_one(
            {"user_id": user_id, "project_id": project_id, "filename": filename},
            {"$set": {"summary": summary}},
            upsert=True
        )
        logger.info(f"Upserted summary for {filename} (user {user_id}, project {project_id})")

    # ── Read ────────────────────────────────────────────────────────────────
    def list_cards(self, user_id: str, project_id: str, filename: Optional[str], limit: int, skip: int):
        q = {"user_id": user_id, "project_id": project_id}
        if filename:
            q["filename"] = filename
        cur = self.chunks.find(q, {"embedding": 0}).skip(skip).limit(limit).sort([("_id", ASCENDING)])
        # Convert MongoDB documents to JSON-serializable format
        cards = []
        for card in cur:
            serializable_card = {}
            for key, value in card.items():
                if key == '_id':
                    serializable_card[key] = str(value)  # Convert ObjectId to string
                elif hasattr(value, 'isoformat'):  # Handle datetime objects
                    serializable_card[key] = value.isoformat()
                else:
                    serializable_card[key] = value
            cards.append(serializable_card)
        return cards

    def get_file_summary(self, user_id: str, project_id: str, filename: str):
        doc = self.files.find_one({"user_id": user_id, "project_id": project_id, "filename": filename})
        if doc:
            # Convert MongoDB document to JSON-serializable format
            serializable_doc = {}
            for key, value in doc.items():
                if key == '_id':
                    serializable_doc[key] = str(value)  # Convert ObjectId to string
                elif hasattr(value, 'isoformat'):  # Handle datetime objects
                    serializable_doc[key] = value.isoformat()
                else:
                    serializable_doc[key] = value
            return serializable_doc
        return None

    def list_files(self, user_id: str, project_id: str):
        """List all files for a project with their summaries"""
        files_cursor = self.files.find(
            {"user_id": user_id, "project_id": project_id},
            {"_id": 0, "filename": 1, "summary": 1}
        ).sort("filename", ASCENDING)
        
        # Convert MongoDB documents to JSON-serializable format
        files = []
        for file_doc in files_cursor:
            serializable_file = {}
            for key, value in file_doc.items():
                if hasattr(value, 'isoformat'):  # Handle datetime objects
                    serializable_file[key] = value.isoformat()
                else:
                    serializable_file[key] = value
            files.append(serializable_file)
        return files

    def vector_search(self, user_id: str, project_id: str, query_vector: List[float], k: int = 6, filenames: Optional[List[str]] = None):
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
                        "filter": {
                            "compound": {
                                "must": [
                                    {"equals": {"path": "user_id", "value": user_id}},
                                    {"equals": {"path": "project_id", "value": project_id}}
                                ]
                            }
                        },
                    }
                },
                {"$project": {"doc": "$$ROOT", "score": {"$meta": "searchScore"}}},
                {"$limit": k},
            ]
            # Append hit scoring algorithm
            hits = list(self.chunks.aggregate(pipeline))
            
            # Convert MongoDB documents to JSON-serializable format
            serializable_hits = []
            for hit in hits:
                doc = hit["doc"]
                serializable_doc = {}
                for key, value in doc.items():
                    if key == '_id':
                        serializable_doc[key] = str(value)  # Convert ObjectId to string
                    elif hasattr(value, 'isoformat'):  # Handle datetime objects
                        serializable_doc[key] = value.isoformat()
                    else:
                        serializable_doc[key] = value
                
                serializable_hits.append({
                    "doc": serializable_doc,
                    "score": float(hit["score"])  # Ensure score is a regular float
                })
            
            return serializable_hits
        else:
            # Fallback: scan limited sample and compute cosine locally
            q = {"user_id": user_id, "project_id": project_id}
            if filenames:
                q["filename"] = {"$in": filenames}
            sample = list(self.chunks.find(q).limit(max(2000, k*10)))
            if not sample:
                return []
            qv = np.array(query_vector, dtype="float32")
            scores = []
            for d in sample:
                v = np.array(d.get("embedding", [0]*VECTOR_DIM), dtype="float32")
                denom = (np.linalg.norm(qv) * np.linalg.norm(v)) or 1.0
                sim = float(np.dot(qv, v) / denom)
                scores.append((sim, d))
            scores.sort(key=lambda x: x[0], reverse=True)
            top = scores[:k]
            logger.info(f"Vector search sample={len(sample)} returned top={len(top)}")
            
            # Convert MongoDB documents to JSON-serializable format
            serializable_results = []
            for score, doc in top:
                serializable_doc = {}
                for key, value in doc.items():
                    if key == '_id':
                        serializable_doc[key] = str(value)  # Convert ObjectId to string
                    elif hasattr(value, 'isoformat'):  # Handle datetime objects
                        serializable_doc[key] = value.isoformat()
                    else:
                        serializable_doc[key] = value
                
                serializable_results.append({
                    "doc": serializable_doc,
                    "score": float(score)  # Ensure score is a regular float
                })
            
            return serializable_results


def ensure_indexes(store: RAGStore):
    # Basic text index for fallback keyword search (optional)
    try:
        store.chunks.create_index([("user_id", ASCENDING), ("project_id", ASCENDING), ("filename", ASCENDING)])
        store.chunks.create_index([("content", TEXT), ("topic_name", TEXT), ("summary", TEXT)], name="text_idx")
        store.files.create_index([("user_id", ASCENDING), ("project_id", ASCENDING), ("filename", ASCENDING)], unique=True)
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