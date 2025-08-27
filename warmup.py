from sentence_transformers import SentenceTransformer
import torch
import os

print("🚀 Warming up model...")
embedding_model = SentenceTransformer("/app/model_cache", device="cpu")

# Some CPU backends on HF Spaces fail on .half(); make it configurable
USE_HALF = os.getenv("EMBEDDING_HALF", "1") == "1"
try:
    if USE_HALF and torch.cuda.is_available():
        embedding_model = embedding_model.half()
except Exception as e:
    print(f"⚠️ Skipping half precision due to: {e}")

embedding_model.to(torch.device("cpu"))
print("✅ Model warm-up complete!")
