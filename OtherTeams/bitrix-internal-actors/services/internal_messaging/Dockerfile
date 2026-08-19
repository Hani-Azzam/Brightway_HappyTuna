# Internal Messaging System — standalone surface (REST + MCP).
# Build context = repo root, so the shared `packages/` come along:
#   docker build -f services/internal_messaging/Dockerfile -t bia-internal-messaging .
FROM python:3.11-slim

WORKDIR /app

# Deps first for layer caching.
COPY services/internal_messaging/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Shared contract packages the service imports (mcp_core + schemas), then the service.
COPY packages/ ./packages/
COPY services/internal_messaging/ ./services/internal_messaging/
# namespace __init__ so `services.internal_messaging` is importable
RUN touch ./services/__init__.py

ENV PYTHONUNBUFFERED=1 \
    CHAT_DB_PATH=/data/chat.db \
    CHAT_PORT=8080

VOLUME ["/data"]
EXPOSE 8080

# A member-scoped health probe is the /health route.
HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
    CMD python -c "import httpx,os; httpx.get(f'http://localhost:{os.environ.get(\"CHAT_PORT\",\"8080\")}/health').raise_for_status()"

CMD ["sh", "-c", "uvicorn services.internal_messaging.app.main:app --host 0.0.0.0 --port ${CHAT_PORT}"]
