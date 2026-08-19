# Influencer Agent

A standalone Python service that plays one influencer persona during the HappyTuna crisis
simulation. It is built on the [NVIDIA NeMo Agent Toolkit](https://github.com/NVIDIA/NeMo-Agent-Toolkit)
(`nvidia-nat`) and talks to `social_network` **only** through its public HTTP API — never
through Prisma, never through the database file. The two services can be deployed, scaled,
and restarted independently.

## Architecture

```
social_network (Node/TS, HTTP API)
        ^
        |  login, feed, comments, reposts — plain REST, envelope {success, data}
        v
influencer-agent (this service)
  +-- poller.py        polls the feed, tracks a per-persona cursor, calls the workflow
  |                    below, then posts the resulting comment/repost back to social_network
  +-- nat serve         a NAT workflow bound to 127.0.0.1 only inside this container;
       (register.py)    given {persona_prompt, post_content, ...} it calls the LLM and
                        returns a validated {decision, reason, responseText}
```

`register.py` never calls social_network, and `poller.py` never calls the LLM — the two
responsibilities only meet over one local HTTP call (`POST /generate`), so "decide" and
"act" stay swappable/testable independently.

## Persona files

Two layers, merged at startup by `persona.py`:

1. **Base template** — `../docs/influencer_persona_prompt.md` (Week 2). Shared by every
   influencer persona: role, objectives, decision process, constraints.
2. **Persona instance** — `personas/<name>.yaml`. This bot's concrete identity and
   attribute values (see `../docs/persona_attributes.md` for the attribute schema):
   `audience_size`, `influence_level`, `credibility`, `sensationalism`,
   `controversy_seeking`, `brand_support`, `viral_probability`.

Only `personas/brand_supporter.yaml` exists so far (one of the three archetypes named in
the team's `PROJECT_README.md` — consumer-rights and sensational are natural next additions:
copy `brand_supporter.yaml`, adjust the attributes, and point `PERSONA_FILE` at the new file).

The base template's own "Output Format" example (`action`/`tone`/`post`/`credibility_score`/...)
predates this integration and doesn't match the schema this service actually needs. Rather
than edit the Week 2 doc, `persona.py` appends a **Decision Contract** section that
supersedes it — the LLM is told explicitly that the JSON block later in the prompt is the
one that counts:

```json
{
  "decision": "amplify" | "criticize" | "ignore",
  "reason": "...",
  "responseText": "..."
}
```

## What happens on each new post

| Decision | Effect on social_network |
|---|---|
| `amplify` | `POST /api/posts/:id/comments` with `responseText`, then `POST /api/posts/:id/repost` |
| `criticize` | `POST /api/posts/:id/comments` with `responseText` |
| `ignore` | nothing |

The repost-on-amplify step is one addition beyond the literal `{decision, reason,
responseText}` spec — `repost` is social_network's dedicated pure-amplification endpoint, and
skipping it would make "amplify" indistinguishable from "criticize" in the product's own
data model. Remove the `repost` call in `poller.py::_handle_post` if you'd rather keep it to
comments only.

## Running with Docker Compose (recommended)

From the repo root:

```bash
cp .env.example .env   # fill in NVIDIA_API_KEY (or OPENAI_API_KEY, see below)
docker compose up --build social-network influencer-agent
```

This also builds `social-network` (added to `docker-compose.yml` alongside this service) so
the two talk to each other over the Docker network at `http://social-network:3000` — no
manual wiring needed. `docs/` is mounted read-only into the container (the build context is
this directory, which can't reach the repo-root `docs/` folder at build time); persona
"last seen post" cursors persist in the `influencer_agent_state` named volume.

Swagger UI for the NAT workflow itself (useful for testing a decision in isolation) is at
`http://localhost:8002/docs` once the container is up.

## Running locally without Docker

```bash
cd influencer-agent
python -m venv .venv && .venv/Scripts/activate   # or source .venv/bin/activate
pip install -e .
export NVIDIA_API_KEY=...                        # https://build.nvidia.com
export SOCIAL_NETWORK_BASE_URL=http://localhost:3000
export BASE_PERSONA_TEMPLATE_PATH=../docs/influencer_persona_prompt.md
export STATE_DIR=./state
python -m influencer_agent.main
```

(`social_network` must already be running separately, e.g. `npm run dev` in that folder.)

To exercise just the NAT workflow — no social_network, no poller — with a single post:

```bash
nat run --config_file configs/config.nim.yml --input \
  '{"persona_prompt": "You are a test persona.", "post_id": "p1", "post_author": "alice", "post_content": "HappyTuna recalled a batch today.", "company_name": "HappyTuna"}'
```

## Switching LLM provider

Two config files are provided; only one field differs (the `llms:` block) between them:

- `configs/config.nim.yml` (default) — NVIDIA NIM, needs `NVIDIA_API_KEY`.
- `configs/config.openai.yml` — OpenAI, needs `OPENAI_API_KEY`.

Select one via `NAT_CONFIG_FILE` (see `docker-compose.yml` / the env vars table below).


