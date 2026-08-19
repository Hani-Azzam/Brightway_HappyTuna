"""Assemble and run the employee population — the piece that turns the parts
(persona, tools, perception, memory, authority) into a live worker.

`build_population` wires, for each `personas/*.yaml`: an LLM, an identity-bound REST
client to the Internal Messaging System, durable memory, perception, and the write
tools **wrapped in the authority guard** (`authorized`) so a tool the persona may not
use never executes — authority enforced in code, not just the prompt (KB §4.1).

`run` embeds the coordinator (the activation layer) and polls the messaging firehose
over REST: each poll wakes the mentioned/relevant persona, which perceives and acts.
Cycles run synchronously, so one persona's activations are serialized (no interleaved
memory writes). This is the single-process MVP; a bus/remote coordinator swaps in at
the `reader` seam with no change to the personas.
"""
from __future__ import annotations

import time
from typing import Callable

import httpx

from packages.agentkit.llm import LLM
from packages.agentkit.tool_base import ToolBase
from packages.agentkit.tool_executor import ToolExecutor

from services.coordinator.reader import RestMessageReader
from services.coordinator.watcher import Coordinator
from services.employee.agent.employee_agent import EmployeeAgent
from services.employee.app.config import Settings
from services.employee.domain.authority import AuthorityPolicy, authorized
from services.employee.domain.memory import EmployeeMemory
from services.employee.domain.perception import Perception
from services.employee.personas.persona import Persona, load_personas
from services.employee.tools.internal_messaging_adapter import SendChatMessage
from services.employee.tools.internal_messaging_client import InternalMessagingClient
from services.employee.tools.mail_tool import MailSendTool
from services.employee.tools.portal_task_tool import PortalTaskUpdateTool
from services.employee.worker.activation import EmployeeRuntime, make_activator

# persona -> its LLM. Injectable so tests pass a fake (and so the anthropic import
# stays lazy — importing this module must not require the SDK).
LlmFactory = Callable[[Persona], LLM]


def _default_llm(persona: Persona, settings: Settings) -> LLM:
    # Lazy import keeps the anthropic SDK out of the import path until an LLM is built.
    from packages.llm.anthropic_client import AnthropicClient, AnthropicConfig

    return AnthropicClient(
        AnthropicConfig(
            api_key=settings.anthropic_api_key,
            model_name=settings.anthropic_model,
            max_tokens=settings.anthropic_max_tokens,
        )
    )


def build_authorized_tools(
    persona: Persona,
    *,
    chat_http: httpx.Client,
    settings: Settings,
    policy: AuthorityPolicy,
    memory: EmployeeMemory,
) -> list[ToolBase]:
    """The persona's write tools, each behind the authority guard. Only channels the
    persona is authorized for are registered (capability = the first authority gate),
    and the wrapper audits/denies at call time (the second gate, incl. external-leak)."""
    def on_deny(name: str, channel: str, reason: str) -> None:
        memory.remember("DENIED", ref=name, summary=f"{channel}: {reason}")

    allowed = set(persona.authority.channels)
    tools: list[ToolBase] = []
    if "internal_messaging" in allowed:
        tools.append(authorized(
            SendChatMessage(http=chat_http, employee_id=persona.employee_id,
                            base_url=settings.internal_messaging_url),
            channel="internal_messaging", policy=policy, on_deny=on_deny))
    if "mail" in allowed:
        tools.append(authorized(
            MailSendTool(base_url=settings.mail_url, agent_id=persona.employee_id),
            channel="mail", policy=policy, on_deny=on_deny))
    if "portal" in allowed:
        tools.append(authorized(
            PortalTaskUpdateTool(base_url=settings.portal_url, agent_id=persona.employee_id),
            channel="portal", policy=policy, on_deny=on_deny))
    return tools


def build_population(
    settings: Settings,
    *,
    llm_factory: LlmFactory | None = None,
    chat_http: httpx.Client | None = None,
) -> tuple[dict[str, EmployeeRuntime], httpx.Client]:
    """One `EmployeeRuntime` per persona YAML, keyed by `employee_id`. Returns the
    runtimes and the shared chat HTTP client (reused by the firehose reader; close it
    when done)."""
    http = chat_http or httpx.Client(timeout=30.0)
    make_llm = llm_factory or (lambda p: _default_llm(p, settings))

    runtimes: dict[str, EmployeeRuntime] = {}
    for persona in load_personas(settings.profiles_dir):
        memory = EmployeeMemory(persona.employee_id)
        policy = AuthorityPolicy(persona)
        executor = ToolExecutor(max_retries=0)
        for tool in build_authorized_tools(
            persona, chat_http=http, settings=settings, policy=policy, memory=memory
        ):
            executor.register(tool)
        agent = EmployeeAgent(make_llm(persona), executor, persona)
        chat = InternalMessagingClient(http, persona.employee_id, settings.internal_messaging_url)
        perception = Perception(chat, cursors=memory)          # durable cursors
        runtimes[persona.employee_id] = EmployeeRuntime(
            agent=agent, perception=perception, memory=memory, executor=executor
        )
    return runtimes, http


def run(
    settings: Settings | None = None,
    *,
    reader=None,
    llm_factory: LlmFactory | None = None,
    chat_http: httpx.Client | None = None,
    interval: float | None = None,
    stop=None,
    max_polls: int | None = None,
) -> None:
    """Build the population and poll the activation firehose until `stop` is set (or
    `max_polls` polls elapse — used by tests). `reader` defaults to the REST firehose;
    tests inject an in-process/fake one."""
    settings = settings or Settings()
    runtimes, http = build_population(settings, llm_factory=llm_factory, chat_http=chat_http)
    reader = reader or RestMessageReader(
        http, settings.internal_messaging_url, settings.coordinator_id
    )
    coord = Coordinator(activate=make_activator(runtimes), reader=reader)
    interval = settings.poll_interval if interval is None else interval

    polls = 0
    try:
        while not (stop and stop.is_set()):
            coord.poll_once()
            polls += 1
            if max_polls is not None and polls >= max_polls:
                break
            time.sleep(interval)
    except KeyboardInterrupt:
        pass                       # clean exit on Ctrl+C (no traceback)
    finally:
        if chat_http is None:      # only close a client we created
            http.close()
