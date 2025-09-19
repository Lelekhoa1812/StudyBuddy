from helpers.setup import app, rag, logger
from helpers.models import HealthResponse


@app.get("/healthz", response_model=HealthResponse)
def health():
    return HealthResponse(ok=True)


@app.get("/test-db")
async def test_database():
    """Test database connection and basic operations"""
    from datetime import datetime, timezone
    try:
        if not rag:
            return {
                "status": "error",
                "message": "RAG store not initialized",
                "error_type": "RAGStoreNotInitialized"
            }
        rag.client.admin.command('ping')
        test_collection = rag.db["test_collection"]
        test_doc = {"test": True, "timestamp": datetime.now(timezone.utc)}
        result = test_collection.insert_one(test_doc)
        found = test_collection.find_one({"_id": result.inserted_id})
        test_collection.delete_one({"_id": result.inserted_id})
        return {
            "status": "success",
            "message": "Database connection and operations working correctly",
            "test_id": str(result.inserted_id),
            "found_doc": str(found["_id"]) if found else None
        }
    except Exception as e:
        logger.error(f"[TEST-DB] Database test failed: {str(e)}")
        return {
            "status": "error",
            "message": f"Database test failed: {str(e)}",
            "error_type": str(type(e))
        }


@app.get("/rag-status")
async def rag_status():
    """Check the status of the RAG store"""
    if not rag:
        return {
            "status": "error",
            "message": "RAG store not initialized",
            "rag_available": False
        }
    try:
        rag.client.admin.command('ping')
        return {
            "status": "success",
            "message": "RAG store is available and connected",
            "rag_available": True,
            "database": rag.db.name,
            "collections": {
                "chunks": rag.chunks.name,
                "files": rag.files.name
            }
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"RAG store connection failed: {str(e)}",
            "rag_available": False,
            "error": str(e)
        }


