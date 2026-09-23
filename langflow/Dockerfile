# Langflow with local sentence-transformers embeddings and the HR policy RAG flow baked in.
FROM langflowai/langflow:1.9.6

# Base image runs as the non-root "user" (uid 1000), which owns /app.
# torch (CPU) already ships in the base image; only sentence-transformers is missing.
RUN uv pip install --python /app/.venv/bin/python --no-cache "sentence-transformers==6.1.0"

# Download the embedding model at build time so the container never needs the Hub at runtime.
ENV HF_HOME=/app/hf-cache
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')"
ENV HF_HUB_OFFLINE=1

COPY --chown=1000:0 components /app/custom_components
COPY --chown=1000:0 flows /app/flows
