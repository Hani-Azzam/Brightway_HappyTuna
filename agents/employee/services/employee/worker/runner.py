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

from services.coordinator.events import ActivationEvent
from services.coordinator.reader import RestMessageReader
from services.coordinator.watcher import Coordinator
from services.employee.agent.employee_agent import EmployeeAgent
from services.employee.app.config import Settings
from services.employee.domain.authority import AuthorityPolicy, authorized
from services.employee.domain.memory import EmployeeMemory
from services.employee.domain.perception import Perception
from services.employee.personas.persona import Persona, load_personas
from services.employee.tools.customer_support_tool import ListOpenTickets, RespondToTicket
from services.employee.tools.internal_messaging_adapter import SendChatMessage
from services.employee.tools.internal_messaging_client import InternalMessagingClient
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
    if "customer_support" in allowed:
        for tool in (
            ListOpenTickets(http=chat_http, employee_id=persona.employee_id,
                            base_url=settings.customer_support_url),
            RespondToTicket(http=chat_http, employee_id=persona.employee_id,
                            base_url=settings.customer_support_url),
        ):
            tools.append(authorized(
                tool, channel="customer_support", policy=policy, on_deny=on_deny))
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


def _support_sweep(
    runtimes: dict[str, EmployeeRuntime],
    http: httpx.Client,
    settings: Settings,
    next_on_duty: int,
) -> int:
    """One support-duty pass: if open tickets are waiting, wake ONE support-capable
    persona (round-robin) to triage and respond through its customer-support tools.

    The check itself is a cheap REST GET — no LLM call happens unless there is
    actually something to respond to, which keeps quiet periods free.
    """
    on_duty = [
        eid for eid, rt in runtimes.items()
        if "customer_support" in rt.agent.persona.authority.channels
    ]
    if not on_duty:
        return next_on_duty
    try:
        resp = http.get(f"{settings.customer_support_url}/tickets",
                        params={"status": "open"})
        open_tickets = resp.json() if resp.status_code == 200 else []
    except Exception:  # noqa: BLE001 — support system down is not the worker's problem
        return next_on_duty
    if not open_tickets:
        return next_on_duty

    eid = on_duty[next_on_duty % len(on_duty)]
    runtimes[eid].activate(ActivationEvent(
        kind="SUPPORT_SWEEP",
        source="customer_support",
        name="OPEN_TICKETS",
        actor_id="support-queue",
        trust_label="internal",
        body=(
            f"{len(open_tickets)} customer support ticket(s) are open and waiting for a "
            f"response. You are on support duty: use list_open_tickets to see them, then "
            f"address the most urgent one with respond_to_ticket (acknowledge the "
            f"customer, say what the company is doing, and set an appropriate status)."
        ),
    ))
    return next_on_duty + 1


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
    tests inject an in-process/fake one.

    Besides chat activations, the loop runs a periodic customer-support sweep so
    employees also act on the ticket queue, not only on mentions (see _support_sweep).
    """
    settings = settings or Settings()
    runtimes, http = build_population(settings, llm_factory=llm_factory, chat_http=chat_http)
    reader = reader or RestMessageReader(
        http, settings.internal_messaging_url, settings.coordinator_id
    )
    coord = Coordinator(activate=make_activator(runtimes), reader=reader)
    interval = settings.poll_interval if interval is None else interval

    polls = 0
    next_on_duty = 0
    last_sweep = 0.0
    try:
        while not (stop and stop.is_set()):
            coord.poll_once()
            now = time.monotonic()
            if settings.support_sweep_interval > 0 and (
                now - last_sweep >= settings.support_sweep_interval
            ):
                last_sweep = now
                next_on_duty = _support_sweep(runtimes, http, settings, next_on_duty)
            polls += 1
            if max_polls is not None and polls >= max_polls:
                break
            time.sleep(interval)
    except KeyboardInterrupt:
        pass                       # clean exit on Ctrl+C (no traceback)
    finally:
        if chat_http is None:      # only close a client we created
            http.close()
