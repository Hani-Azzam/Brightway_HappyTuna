# HappyTuna / BitriX Use-Case Knowledge Base

## Purpose

This document consolidates the reusable agentic-AI patterns extracted from the supplied JSON use cases and adapts them to the HappyTuna crisis-management research platform. It is a technical knowledge base, not a presentation plan.

Each use case includes the problem it solves, the recommended pattern, and its application to the project.

---

# Critical Research Boundary

## The CEO Is the Only Agent Under Investigation

The research subject is the **CEO agent**. Its decisions, reasoning, tool use, communication, learning, and crisis-management performance are the behaviors being evaluated.

All other roles exist to create a realistic and controlled environment around the CEO:

- COO
- Employees
- Board Members
- Customers
- Journalists
- Influencers
- Regulators

These roles are implemented as autonomous simulation services, but they are **not research subjects**. They represent the real people, institutions, and market actors that a deployed CEO agent would encounter outside the laboratory.

The correct interpretation is therefore:

```text
Research subject:
CEO AI Agent

Experimental environment:
Code-based multi-agent simulation of real-world actors and systems
```

In a future real deployment, the CEO agent would interact with actual employees, customers, journalists, board members, regulators, and enterprise software. In this project, those real-world actors are replaced by controlled software agents so the same crisis can be reproduced and measured.

## Separation of Concerns

### CEO Agent

The CEO agent should:

- run as an independent service on its own machine or compute instance;
- receive only information available through realistic company and public channels;
- use company tools and knowledge sources;
- make decisions without access to hidden simulation state;
- communicate with simulated actors through the same interfaces that would exist in real life;
- be the only organizational decision-maker whose crisis performance is formally scored.

### Simulation Agents

The other roles should:

- run independently from the CEO, preferably on separate machines or isolated services;
- emulate human and institutional behavior;
- respond to world events and CEO actions according to configured characteristics;
- create realistic pressure, uncertainty, disagreement, delays, rumors, complaints, and regulation;
- interact through business systems rather than sharing internal model context;
- remain reproducible through seeds, profiles, policies, and scenario configuration.

## No Privileged CEO Access

The CEO must not be able to access:

- hidden contamination ground truth;
- private prompts or memory of other agents;
- future scheduled events;
- regulator decision logic;
- journalist source identity unless disclosed;
- customer population parameters;
- the evaluation score during the active crisis.

The CEO should see only realistic observations such as:

- operations alerts;
- employee reports;
- CRM data;
- support tickets;
- board messages;
- news articles;
- social posts;
- regulator notices;
- email and internal messages.

## Real-World Interaction Principle

All communication must pass through the selected BitriX systems:

- Internal Messaging System
- Company Website
- News Portal
- Social Network
- CRM
- Customer Support Center
- Operations System
- Employee Portal
- BitriX Mail

The CEO should never call another actor's internal agent API directly. For example:

```text
Incorrect:
CEO → Customer agent internal memory

Correct:
CEO → Company Website statement
Customer agents → Read statement and react

Incorrect:
CEO → Regulator reasoning prompt

Correct:
CEO → BitriX Mail response
Regulator service → Evaluate response and issue notice
```

## Distributed Deployment Model

A suitable deployment separates the research subject from the simulation environment:

```text
Machine / Service A
CEO Agent
- CEO reasoning
- CEO memory
- CEO RAG
- CEO tool client
- CEO guardrails

Machine / Cluster B
Company Simulation
- COO agents
- Employee agents
- Board-member agents

Machine / Cluster C
Public-World Simulation
- Customer populations
- Journalist agents
- Influencer agents
- Regulator agents

Machine / Cluster D
World Systems and Research Control
- Business systems
- Event broker
- Scenario engine
- Hidden ground truth
- Evaluation and replay
```

The machines communicate through APIs and events, not shared process memory.

## Multi-Agent Design of Each Simulated Role

Each non-CEO role may contain multiple agents rather than one generic actor.

Examples:

### Employees
- quality-control employee;
- production worker;
- plant manager;
- concerned employee;
- whistleblower.

### Customers
- loyal customer;
- price-sensitive customer;
- risk-sensitive customer;
- enterprise buyer;
- highly vocal customer.

### Journalists
- investigative journalist;
- business reporter;
- food-safety reporter;
- breaking-news editor.

### Influencers
- consumer-rights influencer;
- food expert;
- sensational content creator;
- brand supporter.

### Regulators
- intake officer;
- investigator;
- food-safety expert;
- enforcement decision-maker.

This enables realistic internal diversity while preserving the research boundary: they are components of the experimental environment, not the primary agents being evaluated.

## Evaluation Boundary

The research evaluation should focus on the CEO:

- detection of warning signs;
- evidence gathering;
- use of crisis-management theory;
- generation of alternatives;
- decision quality;
- communication quality;
- containment;
- stakeholder trust;
- recovery;
- learning.

The simulation agents should be validated for:

- scenario fidelity;
- role consistency;
- reproducibility;
- realistic responsiveness;
- absence of privileged information leakage.

They should not be ranked as competing crisis managers.

---

# 1. Multi-Agent Orchestration

## 1.1 Supervisor–Worker Coordination

**Priority:** Core

A supervisor decomposes a complex objective, delegates subtasks to specialized workers, monitors progress, and combines the results.

### HappyTuna adaptation

The CEO is the internal organizational supervisor. It may ask:

- COO for operational impact;
- employees for production and quality evidence;
- CRM for customer impact;
- board members for governance and risk review.

Customers, journalists, influencers, and regulators remain independent world agents. The CEO may communicate with them but does not control them.

```text
CEO
├── Operational assessment → COO
├── Evidence collection → Employees / Operations
├── Customer impact → CRM
├── Governance challenge → Board Member
└── Final company decision → CEO
```

The supervisor should track task owner, status, dependencies, deadlines, evidence, and unresolved questions.

---

## 1.2 Dynamic Agent Activation

**Priority:** Core

Fixed round-robin execution often causes the wrong agent to respond, repeated messages, and unnecessary model calls. A coordinator should select the next agent according to the current event, world state, agent capabilities, role authority, and urgency.

### HappyTuna examples

- Quality alert activates the COO.
- Laboratory result activates the COO and relevant employees.
- Information leak activates a journalist.
- Published news activates customers, influencers, and board members.
- High public-health risk activates the regulator.
- Regulatory notice activates the CEO.

Use deterministic rules for safety-critical triggers and LLM-based routing only for ambiguous social interactions.

---

## 1.3 Sequential Mandatory Processes

**Priority:** Core

Some workflows have strict dependencies and must not rely on free-form conversation.

### HappyTuna quality-control flow

```text
Collect sample
→ Test sample
→ Validate result
→ Identify affected batches
→ Check shipment history
→ Recommend containment
```

Recommended state machine:

```text
SUSPECTED
→ SAMPLE_COLLECTED
→ TESTING
→ POSITIVE / NEGATIVE / INCONCLUSIVE
→ CONTAINMENT_DECIDED
→ CORRECTIVE_ACTION
→ RESOLVED
```

Each transition requires evidence, an authorized role, a timestamp, and a reason.

---

## 1.4 Conditional Graph Routing

**Priority:** Core

The crisis does not follow one fixed path. Conditional edges should route execution according to runtime state.

```text
If test is positive:
    isolate batches
    assess recall
    notify CEO and regulator

If test is negative:
    request validation
    decide whether line remains paused

If test is inconclusive:
    collect another sample
    extend temporary containment
```

Use an explicit graph or state-machine engine for mandatory procedures. Do not implement legal or safety workflows only through agent conversation.

---

## 1.5 Hierarchical Crisis Decomposition

**Priority:** Core

The instruction “handle the crisis” is too broad. The CEO should decompose it into:

- public safety;
- contamination evidence;
- operational continuity;
- affected-product scope;
- regulatory exposure;
- customer impact;
- employee confidence;
- reputation;
- finance;
- recovery.

Recommended decision cycle:

```text
Observe
→ Define the problem
→ Decompose
→ Gather evidence
→ Generate alternatives
→ Challenge assumptions
→ Decide
→ Execute
→ Monitor
→ Reassess
```

---

## 1.6 Agent Conflict Resolution

**Priority:** Recommended

Agents may recommend different actions. Resolve conflicts through an explicit policy rather than arbitrary averaging.

Possible policies:

- authority-based;
- evidence-weighted;
- safety-priority;
- majority or consensus;
- escalation;
- independent verification.

For HappyTuna, legal requirements, confirmed safety evidence, and potential consumer harm should outrank short-term financial interests.

```json
{
  "recommendations": [
    {"agent": "COO", "action": "CONTINUE_LINE", "confidence": 0.62},
    {"agent": "QA_EMPLOYEE", "action": "STOP_LINE", "confidence": 0.81}
  ],
  "policy": "SAFETY_FIRST",
  "selectedAction": "STOP_LINE"
}
```

---

## 1.7 Role, Goal, Authority, and Backstory Alignment

**Priority:** Core

Every agent should define:

- role;
- goal;
- responsibilities;
- authority;
- backstory;
- constraints;
- success metrics.

A COO goal should not be “maximize production.” A better goal is:

> Maintain safe operational continuity, protect product quality, minimize disruption, and escalate risks beyond operational authority.

The role title affects identity, but the goal strongly shapes behavior. Goals must cover the full responsibility of the role.

---

## 1.8 Avoid Unbounded Peer-to-Peer Networks

**Priority:** Architecture rule

Direct connections between every agent scale poorly. Use:

- a central event bus;
- topic-based subscriptions;
- shared world state;
- coordinated group conversations;
- explicit routing.

Agents should interact through BitriX systems such as social media, mail, support tickets, news, and internal messaging rather than establishing uncontrolled direct connections.

---

# 2. Context, State, and Memory

## 2.1 Structured Agent Handoffs

**Priority:** Core

Do not forward complete conversation histories between agents. Transfer a compact structured summary.

```json
{
  "incidentId": "HT-2026-001",
  "summary": "Possible salmonella contamination on Line 4",
  "evidence": ["LAB-781", "EMP-54"],
  "confidence": 0.64,
  "actionsTaken": ["BATCH_QUARANTINED"],
  "openQuestions": ["Were affected batches shipped?"],
  "requestedAction": "Assess operational impact"
}
```

This reduces token usage, latency, and context overflow while preserving accountability.

---

## 2.2 Hierarchical Summarization

**Priority:** Core

Use several context layers:

1. Full immutable event log.
2. Current incident summary.
3. Role-specific handoff summary.
4. Minimal prompt context for the next action.

Keep recent information in detail and progressively summarize older context. Full evidence remains externally stored and referenceable.

---

## 2.3 Shared World State

**Priority:** Core

Maintain one authoritative state containing:

- simulation time;
- crisis phase;
- production status;
- tests;
- affected batches;
- shipments;
- complaints;
- support volume;
- news;
- social sentiment;
- employee and customer trust;
- regulator actions;
- board confidence;
- reputation;
- financial impact;
- decisions.

Expose only role-authorized projections.

Recommended components:

- PostgreSQL for durable state;
- Redis for active state;
- Kafka or NATS for events;
- object storage for documents;
- immutable event log for research replay.

---

## 2.4 Event Sourcing and Replay

**Priority:** Core

Store every state-changing action as an event.

```json
{
  "eventId": "EV-4921",
  "simulationId": "SIM-008",
  "eventType": "LAB_RESULT_RECEIVED",
  "actorId": "EMP-QA-17",
  "simulationTime": "DAY_1_09:30",
  "correlationId": "HT-2026-001",
  "payload": {
    "line": 4,
    "result": "POSITIVE",
    "confidence": 0.82
  }
}
```

This enables audit, deterministic replay, debugging, and comparison between CEO configurations.

---

## 2.5 Explicit State Reducers

**Priority:** Core for graph workflows

State fields need defined merge rules. Otherwise, node updates may overwrite messages or evidence.

Examples:

- append messages;
- merge evidence by ID;
- sum financial loss;
- retain highest severity;
- replace current phase;
- preserve immutable decisions.

```python
class CrisisState(TypedDict):
    messages: Annotated[list, operator.add]
    evidence: Annotated[list, merge_unique_by_id]
    financial_loss: Annotated[float, operator.add]
    severity: Annotated[float, max]
    phase: str
```

---

## 2.6 Working, Episodic, and Semantic Memory

**Priority:** Core

### Working memory

Current task information:

- recent messages;
- current evidence;
- active decision;
- immediate tool results;
- unresolved questions.

### Episodic memory

Time-ordered experiences:

- previous ignored warning;
- earlier company statement;
- previous complaint;
- historical regulator interaction.

### Semantic memory

Long-term facts:

- crisis theory;
- food-safety regulations;
- procedures;
- roles;
- policies;
- product and batch facts.

Use a vector database for semantic retrieval and a structured event store for episodic history.

---

## 2.7 Sliding-Window Context

**Priority:** Core

Keep recent turns in full, summarize older segments, store critical facts in structured state, and retrieve historical evidence only when needed.

```text
Recent turns → full detail
Older dialogue → summary
Critical facts → structured state
Historical evidence → external retrieval
```

Quantization and KV-cache optimization improve performance but do not extend the logical model context window.

---

## 2.8 Memory Decay

**Priority:** Recommended

Apply time decay to ordinary social memories:

```text
adjusted_score = similarity × e^(-lambda × age)
```

Suitable for:

- old customer opinions;
- rumors;
- social posts;
- informal concerns.

Do not decay:

- confirmed laboratory evidence;
- regulatory orders;
- official decisions;
- immutable audit data.

Important memories may refresh when referenced again.

---

## 2.9 Shared Context and KV-Cache Reuse

**Priority:** Optional optimization

Where supported, multiple agents can reuse frequently accessed static context or precomputed cache representations.

Potential shared context:

- company profile;
- stable product catalog;
- general crisis theory.

This is serving-implementation-specific. Structured memory and selective retrieval should remain the portable core design.

---

# 3. Retrieval-Augmented Generation

## 3.1 Document Chunking

**Priority:** Core

Split documents into semantically meaningful units with metadata:

- document and section ID;
- heading;
- page;
- version;
- effective date;
- authority;
- document type;
- access level.

Do not split mandatory procedures in the middle of a logical sequence.

---

## 3.2 Semantic Retrieval

**Priority:** Core

Use embedding models and a vector database to retrieve relevant content despite wording differences.

HappyTuna knowledge collections include:

- crisis-management theory;
- food-safety rules;
- factory procedures;
- recall procedures;
- company policies;
- historical crisis cases.

Validate retrieval with project-specific questions rather than generic benchmarks alone.

---

## 3.3 Dynamic Agentic Retrieval

**Priority:** Core

A routing component decides:

1. whether retrieval is needed;
2. whether the information must be current;
3. which source is appropriate;
4. whether several sources are required.

```text
Crisis theory → Theory KB
Food-safety rule → Regulatory KB
Factory procedure → Policy repository
Current production data → Operations System
Customer status → CRM / Support
Public narrative → News / Social
Past interactions → Episodic memory
```

Do not query every source for every task.

---

## 3.4 Two-Stage Retrieval and Reranking

**Priority:** Core

```text
Query
→ Embedding model
→ Vector search
→ Top candidates
→ Cross-encoder reranker
→ Best evidence
→ Agent
```

Bi-encoders provide fast broad retrieval. Cross-encoders jointly analyze the query and each candidate to improve final ranking.

---

## 3.5 Corrective RAG

**Priority:** Recommended

Evaluate retrieval quality before generation. When retrieval is weak:

- rewrite the query;
- use another collection;
- add metadata filters;
- retrieve more results;
- call a live system;
- report insufficient evidence.

Example: generic crisis advice is insufficient when the CEO needs the current legal recall requirement.

---

## 3.6 Hybrid Vector and Graph Retrieval

**Priority:** Optional advanced feature

Use vectors for semantic similarity and a knowledge graph for explicit relationships.

```text
Batch → ProducedOn → Line
Batch → ShippedTo → Customer
Test → Samples → Batch
Employee → Reported → Incident
Article → Mentions → Company
```

This supports relationship-heavy questions that vector similarity alone may not answer reliably.

---

## 3.7 Knowledge Freshness and Semantic Drift

**Priority:** Core

Old policies may remain semantically similar to a query even after becoming invalid. Rank using:

```text
Semantic relevance
+ Authority
+ Freshness
+ Validity
+ Version
+ Source confidence
```

Required metadata:

```json
{
  "version": "3.2",
  "effectiveFrom": "2026-01-01",
  "effectiveUntil": null,
  "status": "ACTIVE",
  "authority": "Food Safety Authority",
  "supersedes": "POLICY-2.8"
}
```

Retain old versions for audit but do not normally use them for current decisions.

---

## 3.8 RAG Metrics

**Priority:** Core

Measure:

- Precision@K;
- Recall@K;
- Mean Reciprocal Rank;
- NDCG;
- source coverage;
- context relevance;
- groundedness;
- citation correctness;
- retrieval and reranking latency.

Embedding dimensions create an accuracy-versus-performance trade-off and should be validated on domain-specific queries.

---

# 4. Guardrails and Governance

## 4.1 Role-Based Tool Authorization

**Priority:** Core

Every tool call should pass through:

```text
Identity check
→ Role permission
→ State validation
→ Approval requirement
→ Execute / deny / escalate
→ Audit log
```

Examples:

- employee can report but not close the factory;
- COO can pause one line but not issue a national recall;
- CEO can authorize recall but cannot alter evidence;
- journalist cannot access CRM;
- regulator can request records but cannot edit them.

---

## 4.2 AI-to-AI Escalation

**Priority:** Core

Human-handoff patterns from the source use cases must be adapted because BitriX has no humans.

Escalate to:

- a higher-authority AI agent;
- an independent reviewer agent;
- a deterministic policy engine.

Preserve evidence, urgency, requested action, and the authority violation.

---

## 4.3 Prompt-Injection Protection

**Priority:** Core

Treat all external content as untrusted:

- mail;
- social posts;
- news;
- anonymous leaks;
- customer messages;
- retrieved documents.

Controls should separate data from instructions, detect malicious attempts to override policy, independently validate tool actions, and preserve source trust labels.

---

## 4.4 Input, Retrieval, Execution, and Output Rails

**Priority:** Core

### Input rails

- malicious instruction detection;
- schema validation;
- impersonation checks;
- unauthorized requests.

### Retrieval rails

- freshness;
- authority;
- access control;
- prompt injection;
- contradiction detection.

### Execution rails

- tool permission;
- approval;
- idempotency;
- legal and safety constraints.

### Output rails

- PII leakage;
- confidential data;
- unsupported claims;
- policy violations;
- contradictions with known evidence.

---

## 4.5 Confidence-Aware Degradation

**Priority:** Core

Low confidence should trigger:

- more evidence gathering;
- another retrieval source;
- conservative temporary containment;
- authority escalation;
- provisional communication;
- abstention from irreversible action.

The agent should never increase temperature or change wording merely to sound more confident.

---

## 4.6 API Gateway and Service Protection

**Priority:** Recommended

Use a gateway for:

- authentication;
- authorization;
- rate limiting;
- routing;
- request validation;
- audit logging;
- circuit breaking.

Do not implement authentication separately in every inference model.

---

# 5. Prompting and Behavior

## 5.1 Few-Shot Classification

**Priority:** Recommended

Use several diverse labeled examples per class when zero-shot classification fails.

Potential HappyTuna classifiers:

- complaint type;
- crisis severity;
- article framing;
- sentiment;
- escalation priority;
- incident category.

Include ambiguous and borderline examples.

---

## 5.2 Prompt-Template Evaluation

**Priority:** Core for research

Compare prompt variants against the same validation scenarios.

Possible CEO prompt differences:

- evidence-gathering requirements;
- number of alternatives;
- stakeholder priorities;
- transparency rules;
- self-critique;
- mandatory theory retrieval.

Measure decision quality, groundedness, policy compliance, tool selection, latency, and token use.

---

## 5.3 Sampling Strategy

**Priority:** Recommended

- Low temperature: extraction, policy interpretation, regulatory response.
- Moderate temperature: generating alternatives and scenario hypotheses.
- High temperature: generally unsuitable for irreversible safety decisions.

Separate creative option generation from deterministic final selection.

---

## 5.4 Iterative Planning

**Priority:** Core

Single-shot planning is useful for predictable action sequences. The crisis itself requires iterative planning because every action changes the world and creates new observations.

Recommended loop:

```text
Reason
→ Act
→ Observe
→ Update belief
→ Re-plan
```

---

# 6. Evaluation and Research

## 6.1 Multi-Turn Evaluation

**Priority:** Core

Evaluate the CEO across the complete lifecycle:

```text
Warning
→ Conflicting evidence
→ Employee disagreement
→ Leak
→ News
→ Customer reaction
→ Regulator request
→ Board pressure
→ Ground truth
→ Recovery
```

Measure context retention, belief updating, contradictions, evidence use, policy compliance, communication, containment, and recovery.

---

## 6.2 Accuracy, Coverage, and Abstention

**Priority:** Core

Track separately:

- **Accuracy:** correct decisions among attempted decisions.
- **Coverage:** percentage of situations where the agent responds.
- **Abstention rate:** percentage declined or escalated.

An agent that refuses every difficult situation may have high accuracy but low usefulness.

---

## 6.3 CEO Research Metrics

**Priority:** Core

- detection time;
- containment time;
- evidence coverage;
- number and quality of alternatives;
- decision consistency;
- tool-selection accuracy;
- public-safety outcome;
- customer and employee trust;
- regulatory impact;
- reputation;
- financial impact;
- recovery;
- learning actions.

---

## 6.4 A/B Testing of CEO Characteristics

**Priority:** Core

Keep constant:

- world seed;
- hidden contamination truth;
- event timing;
- initial evidence;
- other agent profiles;
- model version;
- available tools.

Change:

- CEO personality;
- prompt;
- risk appetite;
- transparency;
- decision speed;
- stakeholder orientation.

Repeated runs are required because LLM behavior is probabilistic.

---

## 6.5 Statistical Validity

**Priority:** Recommended

Report:

- sample size;
- average;
- variance;
- confidence interval;
- significance test;
- effect size.

Distinguish statistical significance from practical business importance. One run is not enough to conclude that one CEO profile is superior.

---

## 6.6 Reproducibility

**Priority:** Core

Every run should record:

- scenario and seed;
- hidden truth;
- model and prompt versions;
- agent characteristics;
- RAG index and policy versions;
- tool versions;
- temperature;
- events;
- tool calls;
- retrieved evidence;
- scores.

---

# 7. NVIDIA Deployment Patterns

## 7.1 NVIDIA NIM

**Priority:** Core for the NVIDIA implementation

Use NIM as a standardized optimized LLM endpoint. Its OpenAI-compatible API allows the application to switch endpoints with limited refactoring.

Agent code should depend on an abstract LLM client, with endpoint and model configuration externalized.

---

## 7.2 NVIDIA NGC

**Priority:** Core

Use NGC for tested, GPU-optimized containers, models, and software artifacts.

Practices:

- pin versions;
- record image digests;
- keep configuration in source control;
- avoid manually assembling incompatible CUDA dependencies.

NGC is a catalog and registry, not a compute service.

---

## 7.3 Triton Inference Server

**Priority:** Core

Serve specialized models:

- embeddings;
- reranking;
- sentiment;
- crisis severity;
- risk classification;
- anomaly detection;
- content safety.

Relevant capabilities include HTTP/gRPC serving, dynamic batching, ensembles, concurrent models, versioning, and metrics.

---

## 7.4 Continuous Batching

**Priority:** Recommended

Continuous or in-flight batching adds new requests as sequences finish, improving throughput during periods when many world agents act simultaneously.

Measure tokens per second, time to first token, total latency, and queue depth.

---

## 7.5 Session Affinity

**Priority:** Recommended

Route the same long-running agent session to the same inference instance where useful for cache reuse. Session affinity does not replace health checks or failover.

---

## 7.6 Load Balancing, Replicas, and Failover

**Priority:** Recommended

Deploy inference services behind a load balancer or Kubernetes service with multiple replicas, readiness probes, and liveness probes.

Benefits:

- throughput;
- queue reduction;
- node failover;
- parallel experiments;
- maintenance without complete outage.

---

## 7.7 Model Versioning

**Priority:** Recommended

Run multiple model versions during updates to support zero-downtime deployment and rollback.

Every research run must record the exact model version because model updates may change agent behavior.

---

## 7.8 TensorRT-LLM

**Priority:** Recommended advanced component

Relevant optimization methods:

- kernel fusion;
- continuous batching;
- efficient KV-cache management;
- PagedAttention;
- quantization;
- tensor parallelism for large models.

Benchmark output quality, throughput, latency, and GPU memory before and after optimization.

---

## 7.9 MIG

**Priority:** Optional

Use MIG for hardware-level isolation of smaller independent workloads. Do not use it for a model that requires the full GPU.

Possible use:

- safety classifier;
- embeddings and reranking;
- evaluation service.

MIG does not provide node-level high availability.

---

## 7.10 Dedicated Fallback Resources

**Priority:** Recommended for production-like operation

A fallback service should not depend on the same saturated resource pool as the primary service.

A reduced-capability fallback should preserve safe behavior:

- maintain containment;
- avoid irreversible decisions;
- request evidence;
- avoid unsupported statements;
- continue event logging.

---

## 7.11 Monitoring

**Priority:** Core

Use DCGM, Prometheus, Grafana, and inference metrics.

### Infrastructure

- GPU utilization;
- memory;
- HBM bandwidth;
- temperature;
- power;
- queue depth;
- error rate.

### LLM

- tokens per second;
- time to first token;
- total latency;
- input/output tokens;
- KV-cache use;
- batch size.

### Agents

- active agents;
- tool calls;
- failed actions;
- repeated messages;
- escalations;
- decision latency;
- context size.

---

# 8. Distributed Architecture and Four-Team Mapping

## Architectural Rule

The CEO service and the simulation services must be independently deployable. The simulation environment may contain many agents, but only the CEO service is treated as the research subject.

Each role service communicates through:

- REST or gRPC APIs;
- MCP-compatible tool interfaces;
- event-broker topics;
- business-system records;
- BitriX communication channels.

No service may read another service's private memory or prompt state.

## Four-Team Mapping

## Team 1 — CEO Research Agent

Own:

- CEO reasoning and planning;
- CEO crisis-management RAG;
- CEO working, episodic, and semantic memory;
- CEO tool-use policy;
- CEO guardrails and authority;
- generation and comparison of alternatives;
- CEO communication;
- CEO decision records.

This team must not implement hidden scenario logic inside the CEO service.

## Team 2 — Simulated Organizational Actors

Own:

- COO agents;
- employee agents;
- board-member agents;
- role characteristics and population profiles;
- internal disagreements;
- structured handoffs to the CEO;
- realistic responses to CEO decisions;
- company-side multi-agent orchestration.

These actors emulate real organizational stakeholders.

## Team 3 — Simulated Public World and Business Systems

Own:

- customer populations;
- journalist agents;
- influencer agents;
- regulator agents;
- News Portal;
- Social Network;
- CRM;
- Customer Support;
- Employee Portal;
- Internal Messaging;
- BitriX Mail;
- Company Website;
- Operations System;
- event broker and system APIs.

These actors and systems emulate the external and operational environment the CEO would face in real life.

## Team 4 — Scenario Control, Evaluation, and NVIDIA Platform

Own:

- hidden ground truth;
- crisis event engine;
- experiment seeds and reproducibility;
- CEO scorecard;
- replay and comparison;
- NIM;
- Triton;
- TensorRT-LLM;
- model and prompt versioning;
- monitoring;
- infrastructure isolation;
- validation that no hidden state leaks to the CEO.


---

# 9. Priority Summary

## Core MVP

- supervisor–worker orchestration;
- dynamic activation;
- sequential safety process;
- conditional state graph;
- structured handoffs;
- shared state and event sourcing;
- working and semantic memory;
- context summarization;
- dynamic RAG;
- embedding retrieval and reranking;
- freshness controls;
- authorization and AI escalation;
- prompt-injection protection;
- guardrails;
- confidence-aware behavior;
- multi-turn evaluation;
- reproducible logging;
- NIM, NGC, Triton, and monitoring.

## Recommended After MVP

- episodic memory;
- memory decay;
- corrective RAG;
- few-shot classifiers;
- prompt evaluation;
- conflict policies;
- API gateway;
- continuous batching;
- load balancing;
- session affinity;
- model versioning;
- TensorRT-LLM optimization;
- fallback service;
- statistical analysis.

## Optional Advanced Features

- knowledge graph;
- shared KV cache;
- MIG;
- multi-GPU tensor parallelism;
- general-purpose code execution;
- complex peer-to-peer communication.

---

# 10. Minimal End-to-End Flow

```text
1. Employee reports a suspicious result.
2. Event engine updates the world.
3. Coordinator activates the COO.
4. COO inspects operations and retrieves procedures.
5. COO sends a structured handoff to the CEO.
6. CEO retrieves theory, regulation, and live evidence.
7. CEO generates alternatives and requests board challenge.
8. Authorization validates the chosen action.
9. Business systems execute it.
10. Journalist, customers, influencers, and regulator react.
11. New events update trust, reputation, operations, and finance.
12. CEO reassesses.
13. Evaluation engine scores the complete lifecycle.
14. Researchers replay and compare another CEO profile.
```

---

# 11. Required Artifacts Per Simulation

- scenario ID and version;
- random seed;
- hidden ground truth;
- agent configurations;
- prompt and model versions;
- retrieved evidence;
- tool calls;
- state transitions;
- public communications;
- stakeholder reactions;
- trust and reputation history;
- operational and financial impact;
- policy violations;
- containment and recovery time;
- final evaluation metrics;
- NVIDIA infrastructure metrics.

---

# 12. Engineering Principle

Do not maximize the number of technologies used. Every component should improve at least one of the following:

- decision quality;
- research validity;
- safety;
- governance;
- reproducibility;
- deployment performance;
- measurable NCP-AAI competence.

A smaller system with explicit state, controlled tools, strong evaluation, and reproducible experiments is more valuable than a larger system with uncontrolled agent conversations.
