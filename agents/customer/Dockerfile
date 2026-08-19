FROM python:3.11-slim
WORKDIR /app

COPY pyproject.toml .
COPY register.py personas.py system_prompt.py event_client.py driver.py main.py ./
COPY personas.yaml workflow.yml ./
COPY guardrails_config ./guardrails_config

# Installing as a real package (not just "pip install -r requirements.txt")
# is required -- this is what registers our customer_agent_decision
# function type with the "nat" CLI's plugin discovery. Without this,
# "nat mcp serve" has no way of knowing register.py exists.
RUN pip install --no-cache-dir .

# personas.py resolves its default path via Path(__file__).parent -- but
# a real (non-editable) pip install copies personas.py into site-packages,
# separate from personas.yaml which only exists here in /app. Point it
# explicitly at the copy that's actually sitting next to this Dockerfile's
# other files, rather than relying on the two staying adjacent by accident.
ENV PERSONAS_CONFIG_PATH=/app/personas.yaml

EXPOSE 8000

# main.py starts "nat mcp serve" itself (as a subprocess, with the same
# --tool_names restriction previously set here directly -- see main.py's
# docstring) and, in this process, driver.py's event-generator loop that
# makes the agent react on its own instead of purely on demand.
CMD ["python", "main.py"]