FROM ghcr.io/mlflow/mlflow:v2.17.2

# Create persistent data directory
RUN mkdir -p /data/runs /data/artifacts

# Railway injects PORT
ENV PORT=8080

# MLflow server command
CMD mlflow server \
    --host 0.0.0.0 \
    --port $PORT \
    --backend-store-uri file:///data/runs \
    --default-artifact-root /data/artifacts \
    --serve-artifacts
