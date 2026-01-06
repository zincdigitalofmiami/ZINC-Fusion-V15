# ZINC-FUSION Data Worker
# Runs as a scheduled cron job on Railway (daily at 8 AM UTC)
# Handles FRED, CFTC, USDA, EPA data ingestion

FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY main.py .
COPY scripts/ scripts/

# Set Python path
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Default command - run data ingestion
CMD ["python", "main.py"]
