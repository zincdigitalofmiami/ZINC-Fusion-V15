# Fly.io Dockerfile for Databento Live Connector
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir \
    databento \
    psycopg2-binary \
    python-dotenv \
    requests

# Copy the live connector script (from parent dir during build)
COPY ingest_databento_live_zl.py /app/

# Run continuously with 6-hour cycles (auto-restarts via Fly)
CMD ["python", "ingest_databento_live_zl.py", "--run-seconds", "21600", "--buffer-minutes", "30", "--max-replay-hours", "6", "--default-hours", "1"]
