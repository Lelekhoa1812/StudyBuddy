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
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Optional: general HF cache directory (kept for other models like BLIP)
ENV HF_HOME="/home/user/.cache/huggingface"

# Ensure cache directory ownership
RUN mkdir -p /home/user/.cache/huggingface && \
    chown -R user:user /home/user/.cache/huggingface

# Expose port for HF Spaces
ENV PORT=7860
EXPOSE 7860

# Start FastAPI
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
