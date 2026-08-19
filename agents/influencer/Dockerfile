FROM python:3.11-slim
WORKDIR /app

# curl is used by the HEALTHCHECK below to probe the embedded NAT workflow server.
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY src ./src
COPY configs ./configs
COPY personas ./personas
# The shared persona base template (persona.py merges it with personas/*.yaml).
COPY docs ./docs

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e .

# state/ is where per-persona "last seen post" cursors are persisted across restarts.
RUN mkdir -p /app/state

ENV PYTHONUNBUFFERED=1

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://127.0.0.1:${NAT_SERVE_PORT:-8000}/health || exit 1

CMD ["python", "-m", "influencer_agent.main"]
