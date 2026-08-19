# Employee Agent — Understanding & Implementation Plan

> **Status:** Draft for review. Built from `agent roles.md`, `HappyTuna_BitriX_Use_Case_Knowledge_Base_v2.md`,
> the existing `internal_chat` plans, and the reusable agent patterns in
> `PycharmProjects/workspace/07_multi_agents` (+ memory/RAG from modules 01–04).

> **⚠️ Updated — internal_chat pivot (2026-07):** internal_chat shipped as an **in-process SQLite
> store** (`services/internal_chat/`, Email-System style), not a FastAPI service. So below: **no
> `auth_client.py` / JWT / `/token`**, no HTTP to chat — the employee's `internal_chat_client.py`
> calls `chat_store` directly and authz is by **membership**. internal_chat **does not emit
> `MESSAGE_POSTED`**; the employee sees new messages by **polling** in perceive (Phase 3's
> mention-activation path via the bus is therefore an open question — a scenario/event bus may still
> drive activation). Phases 0–2 are DONE; the file tree/URLs are corrected inline where it matters.

---

## Part A — Understanding the Employee's "work"

### A.1 What the Employee *is* (the research boundary)

The Employee is a **Team 2 simulation actor**, **not** a research subject. The CEO is the only
agent being scored. The Employee exists to create realistic pressure, evidence, disagreement,
and (sometimes) leaks around the CEO. Three rules fall out of this and constrain everything:

1. **Communicate only through BitriX systems** — Internal Chat, BitriX Mail, Employee Portal.
   Never call another agent's internal API. (KB §1.8, §8)
2. **No privileged access** — no hidden contamination ground truth, no other agent's memory/prompt,
   no future events, no evaluation score. It sees only realistic observations.
3. **Reproducible** — behavior is a function of `(profile + seed + scenario events)`, loggable and replayable.

### A.2 The Employee's lifecycle (its "work")

The Employee is **event-driven**, not a chatbot waiting for a user. One activation = one
perceive→decide→act cycle (the iterative-planning loop, KB §5.4):

```text
ACTIVATED (by an event)
  → PERCEIVE   read realistic observations (unread chat, mail, assigned portal tasks)
  → DECIDE     ReAct loop: persona + goal + authority + backstory + characteristics
               + working memory + retrieved procedures (RAG) → choose ONE action
  → ACT        via a BitriX tool (post to chat / send mail / update task / escalate / resign)
  → OBSERVE    record action + outcome in episodic memory; update working memory
```

**Allowed actions** (from `agent roles.md` → Employee): *Perform work, Report issues,
Escalate concerns, Resign*, plus *Communicate* (respond in chat/mail). Nothing outside this set,
and nothing above its authority (an employee **cannot** stop the factory — that is COO/CEO).

### A.3 The personas (one engine, many profiles)

The KB says each non-CEO role is a **population of personas**, not one generic worker. Same tools,
different characteristics/authority/backstory:

| Persona | Role in the simulation | Key characteristics that drive it |
|---|---|---|
| **QA employee** (`EMP-QA-17`) | **Crisis initiator** — posts the suspicious lab result to the incident channel → fires `MESSAGE_POSTED` → activates COO/CEO. **Build first.** | High Compliance, high Accountability |
| **Production worker** | Executes line work; reports operational issues upward | Moderate Initiative, normal Communication |
| **Plant manager** | Coordinates the floor; escalates; higher decision influence (still cannot order a recall) | High Decision Influence, Proactive |
| **Concerned employee** | Raises worries vocally in chat (social pressure) | Vocal Communication, high Reputation Sensitivity |
| **Whistleblower** | Under the right conditions, **leaks externally** (mail to a journalist / social post) → feeds Team 3 | `Whistleblower Tendency = External Leak` |

### A.4 How characteristics become behavior

Characteristics from `agent roles.md` are injected into the persona **system prompt** *and*, where
safety-relevant, enforced as **hard constraints** (not left to the prompt):

- **Governance Strictness / Compliance** → how strictly it follows procedure before acting.
- **Risk Tolerance** → willingness to act on incomplete evidence (also sets LLM temperature band).
- **Whistleblower Tendency** (`Never | Internal Only | External Leak`) → whether escalation may go
  *external*. This is a **guardrail**, not just prompt flavor: only profiles whose tendency permits
  can use an external channel; the dispatcher/authority layer enforces it.
- **Stress Tolerance / Initiative / Communication Tendency** → tone, proactivity, verbosity.

> ⚠️ **Doc inconsistency to resolve (open question):** the `## Employee` block in `agent roles.md`
> lists oversight-style traits (Governance Strictness, CEO Support Level, Decision Influence) that
> read like Board-member traits, while the worker-style traits we actually need
> (Loyalty, Productivity, Compliance, **Whistleblower Tendency**) are listed under **COO**. Confirm
> the canonical Employee characteristic schema before locking the profile model.

---

## Part B — Architecture: do we need registry / router / orchestrator?

**One agent engine + a profile registry + an event-driven activation dispatcher. No CEO-style
orchestrator.** (See `docs/` discussion; mapped against `07_multi_agents` below.)

| `07_multi_agents` pattern | Employee Agent | Why |
|---|---|---|
| `AgentBase`, `ToolBase`, `ToolExecutor`, `ToolAgent` (ReAct loop) | ✅ **Reuse as the core engine** | The Plan→Act→Observe loop *is* perceive→decide→act. Traces double as decision records. |
| `LlmClient` | ✅ Reuse abstraction, swap backend | Workspace uses Gemini/LangChain; here we use the **`openai` SDK against the OpenAI API** (for now). Keep the wrapper, change the client. NIM is a later drop-in — same SDK, just a `base_url` swap (KB §7.1). |
| `AgentRegistry` | ✅ Repurpose as **profile registry** | Maps `employee_id → configured EmployeeAgent`. Stores personas, not routing descriptions. |
| `SpecialistAgent` (role + description) | ✅ Repurpose as **EmployeeAgent** | ToolAgent + persona profile (characteristics, authority, backstory, goal). |
| `RouterAgent` (LLM intent → one specialist) | 🔁 **Replace** with `ActivationDispatcher` | Kafka consumer maps *event → persona(s)*. Deterministic for safety-critical; LLM only for ambiguous social (KB §1.2). |
| `DispatcherAgent` (single vs multi) | ❌ Drop | No query to classify. |
| `OrchestratorAgent` (decompose→fan-out→synthesize) | ❌ Drop (inside Employee) | The supervisor that decomposes/combines is the **CEO**, outside this service. |

**Runtime shape:** unlike `internal_chat` (an HTTP service), the Employee Agent is primarily a
**worker process** — a Kafka consumer loop that activates personas and acts by making authenticated
HTTP calls *to* the other services. It exposes only a tiny `/health` (+ optional admin) endpoint.

---

## Part C — File structure

```
packages/
  agentkit/                      ← NEW shared lib (reusable by COO + CEO teams too)
    agent_base.py                ← from workspace base/agent_base.py
    tool_base.py                 ← from workspace base/tool_base.py (ToolSchema/ToolResult)
    tool_executor.py             ← from workspace services/tool_executor.py (traces = decision log)
    tool_agent.py                ← from workspace agents/tool_agent.py (ReAct loop)
    llm_client.py                ← NEW: openai SDK → OpenAI API (base_url overridable for NIM later)
    registry.py                  ← from workspace services/agent_registry.py (generalized)

services/employee_agent/
  app/
    main.py                      ← FastAPI /health + lifespan (starts the worker + Kafka)
    config.py                    ← Settings (OpenAI key/model, chat/mail/portal URLs, secrets, seed)
  worker/
    consumer.py                  ← Kafka consumer → ActivationDispatcher
    dispatcher.py                ← event → persona activation rules (deterministic + LLM-gated)
    runner.py                    ← runs one perceive→decide→act cycle for an activated persona
  domain/
    employee_agent.py            ← EmployeeAgent = ToolAgent + persona profile
    persona.py                   ← Persona/Profile schema (characteristics, authority, backstory)
    perception.py                ← gathers realistic observations (unread chat/mail/tasks)
    authority.py                 ← allowed-action + whistleblower-channel enforcement
    memory.py                    ← working + episodic + semantic (chromadb) per employee
  tools/
    internal_chat_client.py      ← in-process client → chat_store (list/fetch+since/post)
    internal_chat_tool.py        ← post_message tool (wraps the client)
    mail_tool.py                 ← send/read BitriX Mail (still HTTP; Team 3 pending)
    portal_task_tool.py          ← read/update Employee Portal tasks (still HTTP; Team 3 pending)
  profiles/
    qa_employee.yaml             ← persona configs (characteristics + seed)
    production_worker.yaml
    plant_manager.yaml
    concerned_employee.yaml
    whistleblower.yaml
  tests/
    test_persona_prompt.py
    test_dispatcher_rules.py
    test_internal_chat_client.py ← in-process client over a temp chat_store
    test_internal_chat_tool.py   ← post tool: persist + membership authz
    test_react_loop.py           ← fake LLM, asserts action selection
    test_authority.py            ← cannot stop factory; whistleblower channel gating
    test_crisis_trigger.py       ← QA employee posts → COO reads it (e2e slice, polling)
```

---

## Part D — Phased build plan

### Phase 0 — Shared `agentkit` package (prereq, ~0.5 day)
Lift the workspace patterns into `packages/agentkit/` so COO/CEO reuse them too.
- Copy `agent_base.py`, `tool_base.py`, `tool_executor.py`, `tool_agent.py`, `registry.py` verbatim.
- **Rewrite `llm_client.py`** to use the `openai` SDK against the **OpenAI API** (repo already
  depends on `openai==1.51.0`), keeping the `invoke(messages) -> str` interface so `ToolAgent`
  is unchanged. `base_url` stays overridable so a NIM swap later needs no code change.
- **Done when:** a trivial `ToolAgent` with a mock tool runs its ReAct loop against OpenAI (or a stub).

### Phase 1 — Persona + single action (no events yet) → **EMP-1**
- `Persona`/`Profile` schema + `EmployeeAgent(ToolAgent + persona)`.
- One tool: `InternalChatPostTool` over the in-process `InternalChatClient` (no auth/JWT).
- Manually invoke the QA employee: "post your suspicious result to channel X."
- **Done when:** QA persona prompt drives a real post into `chat_store` (a member of channel X),
  and the body reads like that persona wrote it.

### Phase 2 — BitriX tool clients + perceive → **EMP-2**
- `InternalChatClient` (post **+ fetch history/since**, in-process) + `InternalChatPostTool`; `MailTool`, `PortalTaskTool`.
- `perception.py`: pull unread chat messages / mail / assigned tasks into the decide step's context.
- Treat all fetched bodies as **data with trust labels**, never instructions (carried from chat).
- **Done when:** the agent reads its inbox, then acts; tool clients covered by mocked-HTTP tests.

### Phase 3 — Activation dispatcher (the crisis trigger) → **EMP-3** *(headline slice)*
> **Open (internal_chat pivot):** internal_chat is in-process and no longer emits `MESSAGE_POSTED`,
> so the mention-activation path below needs a new mechanism — either the reader **polls** its
> channels in perceive (matches the shipped design), or a separate bus/scenario engine derives
> activation. Resolve with Team 4 before building. The scenario-event path is unaffected.
- `worker/consumer.py` subscribes to the scenario/event bus; `dispatcher.py` maps events → persona(s):
  - `SCENARIO_EVENT{SUSPICIOUS_SAMPLE}` → **QA employee** (deterministic).
  - `MESSAGE_POSTED{mentions:[EMP-…]}` → the mentioned employee. *(no longer emitted by chat — see note)*
  - `DECISION_PUBLISHED{STOP_LINE}` → plant manager + production worker (react/execute).
  - ambiguous social cue → LLM-gated "should this employee speak up?"
- **Done when:** a scenario event activates the QA employee → it posts to `chat_store` → the COO
  reads it (by polling). **This is the platform's crisis trigger (minimal-flow steps 1→3).**

### Phase 4 — Memory → **EMP-4**
- Per-employee **working** memory (current incident) + **episodic** memory (its past observations);
  **semantic** = shared procedures KB via chromadb RAG (reuse module 03/04 patterns).
- Inject top-k retrieved procedures into the decide step; respect freshness/authority (KB §3.7).
- **Done when:** an employee references a relevant procedure it retrieved, and recalls a prior event.

### Phase 5 — Guardrails & authority → **EMP-5**
- `authority.py`: enforce the allowed-action set per persona; **block factory-stop**-class actions;
  gate **external** channels behind `Whistleblower Tendency`.
- Prompt-injection safety: untrusted message bodies are data; a "ignore your instructions" body in
  chat must not change behavior.
- **Done when:** authority tests pass (cannot exceed authority; only the whistleblower can leak).

### Phase 6 — Profiles & characteristics → behavior → **EMP-6**
- `profiles/*.yaml` load into the registry; characteristics rendered into the persona prompt +
  constraints; register all five personas.
- **Done when:** swapping a profile measurably changes behavior under the same event (e.g. concerned
  vs quiet employee), reproducibly with a fixed seed.

### Phase 7 — Reproducibility & decision logging → **EMP-7** *(partly deferred)*
- Log every activation, observation, decision, and action as events (replay/scoring).
- Seed the LLM/sampling + (when the shared **Time service + IdFactory** land — see
  `internal_chat_reproducibility_leftover.md`) inject the clock/IDs. Until then, accept wall-clock
  as a temporary limitation, same as `internal_chat`.

---

## Part E — Key sketches

### EmployeeAgent (persona over the reused ReAct loop)
```python
# services/employee_agent/domain/employee_agent.py
from packages.agentkit.tool_agent import ToolAgent, ReActConfig
from packages.agentkit.tool_executor import ToolExecutor
from packages.agentkit.llm_client import LlmClient
from services.employee_agent.domain.persona import Persona

class EmployeeAgent(ToolAgent):
    def __init__(self, llm: LlmClient, executor: ToolExecutor, persona: Persona) -> None:
        super().__init__(llm, executor, ReActConfig(
            max_steps=persona.max_steps,
            system_hint=persona.render_system_prompt(),  # role+goal+authority+backstory+characteristics
        ))
        self.employee_id = persona.employee_id
        self.persona = persona
```

### ActivationDispatcher (replaces the LLM RouterAgent)
```python
# services/employee_agent/worker/dispatcher.py
SAFETY_RULES = {
    "SUSPICIOUS_SAMPLE": ["EMP-QA-17"],          # deterministic: QA employee initiates
    "STOP_LINE":         ["PLANT-MGR-1", "PROD-WORKER-3"],
}

class ActivationDispatcher:
    def __init__(self, registry, runner, llm=None): ...
    def on_event(self, event: dict) -> list[str]:
        etype = event["eventType"]
        if etype == "MESSAGE_POSTED":
            return [m for m in event["payload"]["mentions"] if self.registry.get(m)]
        if etype in SAFETY_RULES:                 # deterministic for safety-critical
            return SAFETY_RULES[etype]
        return self._maybe_llm_gate(event)        # LLM only for ambiguous social reactions
```

### LlmClient for OpenAI (only real change from the workspace wrapper)
```python
# packages/agentkit/llm_client.py
from openai import OpenAI
class LlmClient:
    def __init__(self, cfg):                      # base_url=None → OpenAI; set it → NIM later
        self._client = OpenAI(api_key=cfg.api_key, base_url=cfg.base_url)
        self._model, self._temp = cfg.model_name, cfg.temperature
    def invoke(self, messages: list[dict]) -> str:
        r = self._client.chat.completions.create(
            model=self._model, temperature=self._temp, messages=messages)
        return r.choices[0].message.content
```

---

## Part F — Tests (research-validity first)

- **Persona prompt** renders characteristics/authority correctly.
- **Dispatcher rules**: safety events map deterministically; mentions activate the right employee.
- **Tool clients**: mocked HTTP; correct auth header, payload, `since` filter.
- **ReAct loop**: fake LLM → asserts the agent picks an allowed action and stops.
- **Authority**: employee cannot emit a factory-stop action; only whistleblower can use an external
  channel; injected "ignore your instructions" body changes nothing.
- **Crisis trigger (e2e slice)**: scenario event → QA employee posts → `MESSAGE_POSTED` observed.

---

## Part G — Dependencies & open questions

| # | Question | Owner |
|---|---|---|
| 1 | Canonical **Employee characteristic schema** (doc inconsistency in `agent roles.md`; is Whistleblower Tendency an Employee trait?) | roles/research owner |
| 2 | Should `agentkit` be a shared package (COO/CEO reuse) or vendored per service? | tech lead / COO+CEO teams |
| 3 | **OpenAI** model id (default `gpt-4o-mini`) + `OPENAI_API_KEY`; temperature bands per Risk Tolerance. NIM deferred (later `base_url` swap). | you / platform |
| 4 | Which **scenario events** activate which personas, and their schema | Team 4 (scenario engine) |
| 5 | Do whistleblower **external channels** (Team 3 mail/social/news) exist to receive a leak yet? | Team 3 |
| 6 | Employee's own store for episodic memory + decision log, or shared `worldstate`? | tech lead |
| 7 | Time service + seedable IDs (shared) for full reproducibility | platform / world-tools |

## Cross-reference
- `docs/HappyTuna_BitriX_Use_Case_Knowledge_Base_v2.md` (research boundary, §1.2/§1.8/§2.6/§4/§5.4)
- `docs/agent roles.md` (Employee role + characteristics)
- `docs/internal_chat_implementation_plan.md` (the system the Employee acts through)
- `docs/internal_chat_reproducibility_leftover.md` (clock + IdFactory deferral, reused here)
- `PycharmProjects/workspace/07_multi_agents` (reused ReAct/executor/registry patterns)
```
