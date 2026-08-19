FROM python:3.11-slim

WORKDIR /app

# Copy shared base and services
COPY base/ ./base/
COPY services/ ./services/

# Copy journalist agent
COPY agents/journalist/ ./agents/journalist/

# Install dependencies
RUN pip install --no-cache-dir -r agents/journalist/requirements.txt

# Set Python path so imports work
ENV PYTHONPATH=/app

EXPOSE 8080

CMD ["python", "-m", "agents.journalist.listener"]