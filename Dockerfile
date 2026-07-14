# ClinicalxCRAFT — Hugging Face Docker Space
# Serves the FastAPI app (static dashboard at / + live agent at /api/ask) on port 7860.
FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy only what the FastAPI app needs (no .env, no .venv, no git)
COPY app ./app
COPY data ./data
COPY web ./web

# HF Spaces routes to this port; the LLM runs on Nebius, so the container stays light.
EXPOSE 7860

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
