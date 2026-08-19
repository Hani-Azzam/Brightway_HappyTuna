FROM python:3.11-slim

WORKDIR /app

# Dependencies first for layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Shared ReAct/RAG runtime, the agent itself, its tools, and its knowledge base.
COPY base/ ./base/
COPY services/ ./services/
COPY tools/ ./tools/
COPY knowledge/ ./knowledge/
COPY *.py ./

ENV PYTHONUNBUFFERED=1

# listener.py subscribes to the event generator's "press" stream and reacts
# to each event (investigate -> publish to the journalism site -> post on the
# social network). main.py is the interactive variant for local testing.
CMD ["python", "listener.py"]
