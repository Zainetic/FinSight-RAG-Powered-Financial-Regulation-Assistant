FROM python:3.13-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install curl for container healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# 1. FORCE THE CPU-ONLY PYTORCH INSTALL FIRST (Blocks the heavy CUDA/GPU download)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# 2. INSTALL APPLICATION DEPENDENCIES (Locks dependency resolution to CPU-only PyTorch)
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt

# Create a non-root application user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

COPY --chown=appuser:appuser . .

USER appuser

# 3. FASTAPI UPDATES BELOW:
EXPOSE 8000

# Ping the FastAPI OpenAPI docs page to ensure the server is responding
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/docs || exit 1

# Boot FastAPI via Uvicorn directly from src.api.main
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]