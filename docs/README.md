# Documentation index

Everything written about this project, in one place. Cross-cutting documents
live here; component-specific docs live next to their code and are linked
below.

## Cross-cutting

| Document | What it covers |
|---|---|
| [architecture.md](architecture.md) | The whole world on one page: platforms, agents, event flow, communication contracts, LLM usage, isolation rules |
| [ceo-agent.md](ceo-agent.md) | The CEO agent in depth: gateway, plan-solve cycle, memory design, guardrails — with diagrams |
| [persona_attributes.md](persona_attributes.md) | The attribute schema (0.0–1.0 traits) behind customer and influencer personas |
| [customer_persona_prompt.md](customer_persona_prompt.md) | The customer persona prompt spec (implemented in `agents/customer/system_prompt.py`) |

## Platforms

| Component | Docs |
|---|---|
| Customer Support | [README](../platforms/customer-support/README.md) · [API endpoints](../platforms/customer-support/Customer_Support_API_Endpoints.md) · [schema](../platforms/customer-support/Customer_Support_Schema.md) |
| Social Network | [README](../platforms/social-network/README.md) · [docs/](../platforms/social-network/docs/) (architecture, MCP tools, analytics methodology) |
| Journalism Site | [README](../platforms/journalism-site/README.md) |
| Internal Chat | [service README](../platforms/internal-chat/services/internal_messaging/README.md) · [integration guide](../platforms/internal-chat/services/internal_messaging/INTEGRATION.md) · [design](../platforms/internal-chat/DESIGN.md) |

## Agents

| Component | Docs |
|---|---|
| Customer | [README](../agents/customer/README.md) |
| Influencer | [README](../agents/influencer/README.md) · [walkthrough](../agents/influencer/WALKTHROUGH.md) · [persona base template](../agents/influencer/docs/influencer_persona_prompt.md) (runtime asset) |
| Journalist | [README](../agents/journalist/README.md) |
| Employee | [README](../agents/employee/README.md) |
| CEO | [README (gateway)](../agents/ceo/README.md) · [ceo-agent.md](ceo-agent.md) |

## Event generator

| Component | Docs |
|---|---|
| Event generator | [README](../event-generator/README.md) — architecture, API, the scripted crisis feed, subscribing |
