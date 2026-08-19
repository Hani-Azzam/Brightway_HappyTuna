FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Shared agent runtime (ReAct engine + Claude client) and the worker itself.
COPY packages/ ./packages/
COPY services/ ./services/

ENV PYTHONUNBUFFERED=1 \
    # Durable per-persona memory and the coordinator's activation log.
    BITRIX_EMPLOYEE_DB=/data/employee.db \
    BITRIX_COORD_DB=/data/activations.db

VOLUME ["/data"]

# The worker embeds the coordinator: it polls the Internal Chat activation
# firehose (waking personas that are mentioned) and periodically sweeps the
# Customer Support queue so open complaints get addressed.
CMD ["python", "-m", "services.employee.app.main"]
