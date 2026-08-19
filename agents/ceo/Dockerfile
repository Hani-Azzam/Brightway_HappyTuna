FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# The gateway (policy, identity, dry-run, audit), the plan-solve agent, and
# the autopilot driver.
COPY base/ ./base/
COPY gateway/ ./gateway/
COPY agents/ ./agents/
COPY services/ ./services/
COPY *.py mcp_servers.yaml roles.yaml ./

ENV PYTHONUNBUFFERED=1 \
    # Sliding-window memory persists here; mounted as a volume in compose.
    CEO_MEMORY_PATH=/data/ceo_memory.json

VOLUME ["/data"]

# autopilot.py: subscribes to press events, runs periodic reviews, and drives
# the plan-solve loop against the full MCP gateway surface. main.py remains
# the host-run one-shot behavioral test.
CMD ["python", "autopilot.py"]
