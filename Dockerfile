# Hugging Face Spaces - Docker
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl git libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*

# Create and use a non-root user
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy project files
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Hugging Face cache directories
ENV HF_HOME="/home/user/.cache/huggingface"
ENV SENTENCE_TRANSFORMERS_HOME="/home/user/.cache/huggingface/sentence-transformers"
ENV MEDGEMMA_HOME="/home/user/.cache/huggingface/sentence-transformers"

# Create cache directories and set permissions
RUN mkdir -p /app/model_cache /home/user/.cache/huggingface/sentence-transformers && \
    chown -R user:user /app/model_cache /home/user/.cache/huggingface

# Control preloading flags
ENV PRELOAD_TRANSLATORS="0"
ENV EMBEDDING_HALF="0"

# Preload embedding model and warmup
RUN python /app/dw_model.py && python /app/warmup.py

# Ensure ownership stays correct
RUN chown -R user:user /app/model_cache

# Expose port for HF Spaces
ENV PORT=7860
EXPOSE 7860

# Start FastAPI
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
