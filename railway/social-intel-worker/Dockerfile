# ZINC-FUSION Social Intel Worker
# Lightweight container for scheduled social media scraping

FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source files
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY main.py .

# Default command - can be overridden
CMD ["python", "main.py"]
