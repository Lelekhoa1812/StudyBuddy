# Hugging Face Spaces - Docker for Ingestion Pipeline
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# System deps (same as main system)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl git libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*

# Create and use a non-root user (same as main system)
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy ingestion pipeline files (includes utils and helpers)
COPY . .

# Install Python dependencies (same as main system)
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# No local model caches or warmup needed (remote embedding service)

# Expose port for HF Spaces
ENV PORT=7860
EXPOSE 7860

# Start FastAPI (single worker so app.state.jobs remains consistent)
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]