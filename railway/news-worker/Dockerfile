# ZINC-FUSION News Ingestion Worker
# Runs as a scheduled cron job on Railway

FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for caching)
COPY requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt

# Copy application code (relative to railway/news-worker context)
COPY scripts/ scripts/
COPY src/ src/

# Create logs directory
RUN mkdir -p logs

# Set Python path
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Default command
CMD ["python", "scripts/ingest_news_sources.py", "--mode", "full", "--days", "7"]
