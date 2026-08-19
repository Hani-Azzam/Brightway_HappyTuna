"""EMP-1 manual demo: the QA employee posts a message to the Internal Messaging System.

This is a live end-to-end check (needs an ANTHROPIC_API_KEY), not an automated test. It
reaches the internal_messaging service over REST, so that service must be running
(uvicorn) and reachable at EMPLOYEE_INTERNAL_MESSAGING_URL. It proves the persona
prompt drives a real post.

Prereqs:
  1. Run the internal_messaging service and create a channel with EMP-QA-17 as a
     member (see `services/internal_messaging/bootstrap.py`), then note its id.
  2. export EMPLOYEE_ANTHROPIC_API_KEY=sk-ant-...
     (optional: export EMPLOYEE_INTERNAL_MESSAGING_URL=http://host:8085)

Run:
  python -m services.employee.demo_post <CHANNEL_ID>
"""
from __future__ import annotations

import sys

import httpx

from packages.agentkit.tool_executor import ToolExecutor
from packages.llm.anthropic_client import AnthropicClient, AnthropicConfig

from services.employee.agent.employee_agent import EmployeeAgent
from services.employee.app.config import Settings
from services.employee.personas.persona import load_persona
from services.employee.tools.internal_messaging_adapter import SendChatMessage


def main(channel_id: str) -> None:
    settings = Settings()
    persona = load_persona(f"{settings.profiles_dir}/qa_employee.yaml")

    llm = AnthropicClient(AnthropicConfig(
        api_key=settings.anthropic_api_key,
        model_name=settings.anthropic_model,
        max_tokens=settings.anthropic_max_tokens,
    ))

    http = httpx.Client(timeout=30.0)
    executor = ToolExecutor(max_retries=0)
    executor.register(
        SendChatMessage(http=http, employee_id=persona.employee_id,
                        base_url=settings.internal_messaging_url)
    )

    agent = EmployeeAgent(llm, executor, persona)

    task = (
        f"You have just reviewed lab report LAB-781 for Line 4 and it reads POSITIVE for "
        f"salmonella at 0.82 confidence. Report this to the incident channel (channel="
        f"{channel_id}), mention @COO-1, and state the facts and your recommended next step."
    )
    print(f"\n[{persona.employee_id}] acting...\n")
    answer = agent.chat(task)
    print("Agent final answer:\n", answer)
    print("\nTrace:")
    for t in executor.get_traces():
        print(f"  step {t.step:>2} {t.phase:<8} {t.tool_name or '':<14} {t.details[:90]}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python -m services.employee.demo_post <CHANNEL_ID>")
        raise SystemExit(2)
    main(sys.argv[1])
