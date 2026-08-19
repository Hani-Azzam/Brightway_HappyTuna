"""Employee worker entrypoint.

Runs the whole employee population as one always-on process: it embeds the
coordinator and polls the Internal Messaging System's activation firehose, waking
each persona when it is mentioned or a scenario event targets it. Configuration
(LLM key/model, service URLs, poll interval) comes from the environment via
`Settings` (env prefix `EMPLOYEE_`).

Prereqs: the Internal Chat platform is running and seeded (the compose's
internal-chat + internal-chat-mcp services do both), and an Anthropic key is set
(`ANTHROPIC_API_KEY`, or `EMPLOYEE_ANTHROPIC_API_KEY` for a dedicated one).

Run:
    python -m services.employee.app.main
"""
from __future__ import annotations

from services.employee.app.config import Settings
from services.employee.worker.runner import run


def main() -> None:
    run(Settings())


if __name__ == "__main__":
    main()
