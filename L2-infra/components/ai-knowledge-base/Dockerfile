# AI Knowledge Base - Production Image
FROM python:3.11-slim

WORKDIR /app

# System deps for OCR and office parsing
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-chi-sim \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY pyproject.toml README.md ./
COPY ai_kb/ ./ai_kb/
COPY api/ ./api/
COPY cli/ ./cli/
COPY mcp/ ./mcp/
COPY scripts/ ./scripts/

RUN pip install --no-cache-dir -e ".[embedding]"

# Data dir
RUN mkdir -p /data
ENV AIKB_DB_PATH=/data/ai-kb.db

EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1

CMD ["python3", "-m", "api.server", "--host", "0.0.0.0", "--port", "8000", "--config", "/app/config.example.yaml"]
