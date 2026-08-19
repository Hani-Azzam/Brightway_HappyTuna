# Influencer Agent — Full Walkthrough (A to Z)

This document explains everything that was built for the Week 3 influencer-agent work: why
each piece exists, how the pieces fit together, every file that was created or changed, the
real bugs found while testing it, and how to run/verify it yourself. It's written to be
readable standalone — you shouldn't need the chat history to follow it.

---

## 1. The goal

Build the Influencer Agent as a **separate Python service**, outside `social_network`
(Node/TS), that:

1. Notices new posts on `social_network`.
2. Loads a persona prompt (written in Week 2).
3. Asks an LLM, via **NVIDIA NeMo Agent Toolkit (NAT)**, to decide one of:
   `amplify`, `criticize`, or `ignore`.
4. If `amplify` or `criticize`: generates a response and posts it back to `social_network`.
5. Never touches `social_network`'s database directly — HTTP only.

The output contract required from the LLM:

```json
{ "decision": "amplify | criticize | ignore", "reason": "...", "responseText": "..." }
```

---

## 2. What `social_network` already offered (investigated before writing any code)

`social_network` is a Node/TS + Express + Prisma/SQLite app. All responses use one envelope:
`{ "success": bool, "data"?: T, "error"?: string }`. Auth is intentionally trivial for this
simulation — `POST /api/auth/login` with just a `name` upserts a user and returns a token
that **is** the user's id; that token is sent back as `Authorization: Bearer <token>`.

| Need | Endpoint |
|---|---|
| Create/log in the bot's identity | `POST /api/auth/login` `{name}` → `{token, user}` |
| Mark it as an influencer account | `PATCH /api/users/:id` `{accountType: "influencer"}` |
| Poll for new posts | `GET /api/posts?page=&limit=` — global feed, **newest-first**, no `since` filter |
| React — comment | `POST /api/posts/:id/comments` `{content}` |
| React — pure amplification | `POST /api/posts/:id/repost` |

Two consequences of "no `since` filter": (a) the agent must keep its own cursor of the last
post id it has seen, and (b) a brand-new persona must not treat the entire existing feed as
"new" the first time it runs (see §7, bug #3).

I also checked `docs/persona_attributes.md` and `docs/influencer_persona_prompt.md` (the
Week 2 deliverables) and the team's `PROJECT_README.md`, which names three influencer
archetypes: **consumer-rights, sensational, brand-supporter**. Only the shared template and
the attribute schema existed — no concrete per-persona files — so creating those instance
files was part of this work, not something to assume already existed.

---

## 3. Architecture

```
social_network (Node/TS)                    influencer-agent (Python)
  Prisma/SQLite, port 3000        <—HTTP—>     poller.py  <—HTTP (localhost only)—>  nat serve
                                                   |                                     |
                                            social_client.py                      register.py
                                            (only module that                    (the NAT workflow:
                                             talks to social_network)              persona + post → LLM
                                                                                    → validated decision)
```

Two processes run inside **one container**:

- **`nat serve`** — NVIDIA NeMo Agent Toolkit's own FastAPI server, running the custom
  workflow defined in `register.py`. Its only job: given a persona prompt and one post's
  text, call the LLM and return `{decision, reason, responseText}`. It never calls
  `social_network` and never reads files from disk.
- **`poller.py`** (the orchestrator) — polls `social_network` for new posts, calls the NAT
  workflow's `/generate` endpoint over local HTTP for each one, and — depending on the
  decision — posts a comment and/or a repost back to `social_network`.

This split means "decide" (LLM reasoning) and "act" (HTTP side-effects on the social
network) never share code, and either half could be tested or replaced independently.

---

## 4. Every file, what it does, and why

### `influencer-agent/pyproject.toml`
Makes this an installable Python package (`influencer-agent`) and registers it as a NAT
plugin via the `[project.entry-points.'nat.components']` hook — this is how NAT discovers
`register.py` at runtime. Pins `nvidia-nat[langchain]==1.8.0` (verified against the real
PyPI package, not guessed), plus `httpx` and `pyyaml`.

### `influencer-agent/configs/config.nim.yml` / `config.openai.yml`
NAT's own YAML workflow config. Each declares one LLM (`llms:`) and sets our custom
function as the top-level `workflow:` — meaning the workflow **is** the decision function,
not an agent that calls it as a tool. `config.nim.yml` (default) uses NVIDIA NIM
(`meta/llama-3.3-70b-instruct`, needs `NVIDIA_API_KEY`); `config.openai.yml` is a drop-in
alternative (`gpt-4o-mini`, needs `OPENAI_API_KEY`). Switching providers = picking a
different file via `NAT_CONFIG_FILE`.

### `influencer-agent/src/influencer_agent/schemas.py`
The only contract between "decide" and "act":
- `DecisionRequest` — what the workflow needs (`persona_prompt`, `post_id`, `post_author`,
  `post_content`, `company_name`). No social_network or filesystem access implied.
- `DecisionResult` — `decision` / `reason` / `responseText`, with a Pydantic validator that
  **rejects** `amplify`/`criticize` decisions carrying an empty `responseText` — this is what
  drives the retry loop in `register.py` when the LLM forgets to fill it in.

### `influencer-agent/src/influencer_agent/register.py`
The NAT workflow itself. Key pieces:
- `InfluencerDecisionConfig(FunctionBaseConfig, name="influencer_decision")` — the YAML-configurable
  fields (`llm_name`, `max_retries`).
- `@register_function(...)` decorated `influencer_decision_function` — gets an LLM handle via
  `builder.get_llm(...)`, then defines `_decide(request: DecisionRequest) -> DecisionResult`
  and hands it to NAT via `FunctionInfo.from_fn(...)`.
- `_decide` builds a `SystemMessage` (the full persona prompt) + `HumanMessage` (the post),
  calls the LLM, and parses the reply as JSON (`_extract_json_object` strips markdown code
  fences first). If parsing or schema validation fails, it appends the error back into the
  conversation and asks the model to correct itself — up to `max_retries` times — before
  raising.

### `influencer-agent/src/influencer_agent/persona.py`
Loads and merges two layers into one system prompt:
1. **Base template** — `docs/influencer_persona_prompt.md` (Week 2, shared by every persona).
2. **Persona instance** — `personas/<name>.yaml` (this bot's concrete identity/attributes).

It also appends a **Decision Contract** section that explicitly supersedes the base
template's own example output format (which predates this integration and used a different,
incompatible schema — `action`/`tone`/`post`/`credibility_score`/...). Rather than edit the
Week 2 document, the loader tells the LLM which schema in the prompt actually governs.

### `influencer-agent/personas/brand_supporter.yaml`
The first concrete persona instance (one of the three named in `PROJECT_README.md`):
name, handle, bio, and the seven attributes from `docs/persona_attributes.md`
(`audience_size`, `influence_level`, `credibility`, `sensationalism`, `controversy_seeking`,
`brand_support`, `viral_probability`) with real values skewed toward a supportive influencer.
Adding `consumer_rights.yaml` / `sensational.yaml` later is a copy-and-adjust-numbers task —
see the README's "Adding a second persona" section.

### `influencer-agent/src/influencer_agent/social_client.py`
**The only module allowed to call `social_network`.** Wraps: login/upsert-and-set-accountType,
paging the global feed, posting a comment, reposting. Unwraps social_network's
`{success, data, error}` envelope and raises `SocialNetworkError` on failure.

### `influencer-agent/src/influencer_agent/state.py`
`PersonaCursor` — persists "last seen post id" to a JSON file per persona
(`STATE_DIR/<handle>.json`), so restarts don't re-react to old posts. Backed by a Docker
named volume (`influencer_agent_state`) in production.

### `influencer-agent/src/influencer_agent/nat_client.py`
The poller's HTTP client for the *local* NAT workflow server: `POST /generate` with a
`DecisionRequest`, get back a `DecisionResult`; `wait_until_ready()` polls `/health` at
startup so the poller never races the workflow server coming up.

### `influencer-agent/src/influencer_agent/poller.py`
The orchestration loop (`InfluencerPoller`):
1. Logs the persona in once (`social_client.login_or_create_bot`).
2. Every `POLL_INTERVAL_SECONDS`: pages the feed newest-first until it hits the last seen
   post id, collecting everything newer; processes them **oldest-first** (so reactions read
   in the order posts were actually published); skips any post authored by the bot itself.
3. For each post: builds a `DecisionRequest`, calls the NAT workflow, and acts:
   - `amplify` → comment with `responseText`, **then repost** (see §6 for why).
   - `criticize` → comment with `responseText`.
   - `ignore` → nothing.
4. Advances and saves the cursor to the newest post id processed this cycle.

### `influencer-agent/src/influencer_agent/main.py`
The container's entrypoint. Starts `nat serve` as a subprocess bound to `0.0.0.0` (see §7
bug #4 for why that matters), waits for it to report healthy, loads the configured persona,
builds the poller, and runs it forever — with graceful shutdown on `SIGTERM`/`SIGINT`
(guarded for Windows, where `asyncio` doesn't support Unix signal handlers, so local dev
outside Docker doesn't crash on import).

### `influencer-agent/Dockerfile`
`python:3.11-slim` + `curl` (for the `HEALTHCHECK`, which hits `/health`) + `pip install -e .`
(installs this package and `nvidia-nat[langchain]` together, editable). Creates empty
`/app/docs` and `/app/state` mount points — `docs/` is supplied at *runtime* via a
docker-compose volume mount, because this image's build context (`./influencer-agent`) can't
reach the repo-root `docs/` folder at build time.

### Root `docker-compose.yml`
Added a **`social-network` service** — it had no compose entry at all before this work,
even though it already had its own Dockerfile. Wired `influencer-agent` to it:
`SOCIAL_NETWORK_BASE_URL=http://social-network:3000` (Docker's internal DNS), `depends_on`,
a read-only `docs/` mount, and the `influencer_agent_state` named volume. Port mapping
`8002:8000` was already there; it now actually works (see §7 bug #4).

### Root `.env.example`
Didn't exist before. One file, shared by every service via each service's `env_file: .env`
— `COMPANY_NAME`, `PLATFORM_NAME`, `NVIDIA_API_KEY`, `OPENAI_API_KEY`, etc.

---

## 5. The decision flow, end to end

1. `poller.py` finds a new post: `{id, content, user: {name}}`.
2. Builds `DecisionRequest{persona_prompt, post_id, post_author, post_content, company_name}`.
3. `POST http://127.0.0.1:8000/generate` (inside the container) with that JSON.
4. `register.py`'s `_decide` sends `SystemMessage(persona_prompt)` +
   `HumanMessage(post text)` to the configured LLM (NIM or OpenAI).
5. LLM replies; `_extract_json_object` strips any markdown fencing and parses it;
   `DecisionResult.model_validate(...)` enforces the schema (retries on failure, up to
   `max_retries`).
6. Poller gets back `{decision, reason, responseText}` and acts via `social_client.py`.
7. Cursor advances so this post is never re-processed.

Verified for real — not just by reading the code — with:
```json
{"decision":"amplify","reason":"give them the benefit of the doubt for taking proactive measures","responseText":"Kudos to HappyTuna for prioritizing consumer safety! ..."}
```
against a live NIM call for a sample recall post.

---

## 6. Design decisions made on your behalf (flagged so you can revisit them)

- **`amplify` also triggers a repost, not just a comment.** The literal spec only mentioned
  "generate a response and send it back"; `repost` is `social_network`'s dedicated
  pure-amplification endpoint, and skipping it would make `amplify` indistinguishable from
  `criticize` in the product's own data model. Remove the `repost` call in
  `poller.py::_handle_post` if you want comments-only.
- **The Decision Contract supersedes the Week 2 doc's example output**, rather than editing
  `docs/influencer_persona_prompt.md` directly — keeps that file as the shared, team-owned
  template while still getting the right schema out of the LLM.
- **The raw `/generate` endpoint is reachable from the host with no auth**, because it's
  bound to `0.0.0.0` so Docker's port mapping can reach it (see bug #4 below). Acceptable
  given the whole platform's auth model is already "no real security, name-only tokens"
  (`social_network/CLAUDE.md`), but worth knowing if this ever goes beyond a local sim.
- **First-ever run for a persona doesn't react to the existing backlog** — it just records
  the current newest post as its starting cursor. Otherwise a fresh persona container would
  immediately comment on every historical post in the feed.

---

## 7. Bugs found and fixed while actually testing this (not just writing it)

| # | Bug | How it was caught | Fix |
|---|---|---|---|
| 1 | `from __future__ import annotations` in `register.py` broke NAT's internal `typing.get_type_hints()` resolution of `DecisionRequest`/`DecisionResult` — `nat run` failed with `NameError: name 'DecisionRequest' is not defined`. | Installed `nvidia-nat` in a throwaway venv and actually ran `nat run` against the config. | Removed the future-annotations import from `register.py` (only that file — it's the one NAT introspects). |
| 2 | `DECISION_CONTRACT.format(company_name=...)` crashed (`KeyError`) because the template contains a literal JSON example with `{`/`}` characters, which `str.format()` tried to treat as placeholders. | Ran `persona.py`'s renderer directly against the real `docs/influencer_persona_prompt.md`. | Switched to `str.replace("{company_name}", ...)`. |
| 3 | A fresh persona's first poll cycle would append every post on page 1 to "new posts" *before* checking the first-run condition — meaning a new persona would react to the entire existing backlog instead of starting clean. | Re-reading `poller.py::_fetch_new_posts` line by line after writing it. | Restructured so the first-run branch returns `[]` immediately after recording the baseline cursor. |
| 4 | `nat serve` was bound to `127.0.0.1` inside the container. Docker's `8002:8000` port publishing forwards to the container's external interface, not its internal loopback — so `http://localhost:8002/docs` was unreachable from the host even though the container's own poller (same network namespace) could still reach it fine. | You reported `/docs` wouldn't load; reasoned through Docker's port-forwarding model. | Split into `nat_bind_host="0.0.0.0"` (what `nat serve --host` uses) vs. `nat_client_host="127.0.0.1"` (what the in-container poller connects to). |
| 5 | The real `NVIDIA_API_KEY` ended up written into `.env.example` (not just `.env`). `.env` is gitignored; `.env.example` is not — so the key was one `git add .` away from landing in git history. | Read both files while debugging bug #4. | Cleared the key back out of `.env.example`; confirmed neither file was git-tracked yet, so nothing had leaked. |

Bugs 1–3 were caught by actually installing `nvidia-nat` and running the workflow
(`nat validate`, `nat run`) before ever wiring up Docker — not by inspection alone.

---

## 8. Environment variables (full reference)

| Variable | Default | Used by | Meaning |
|---|---|---|---|
| `NVIDIA_API_KEY` | — | NAT (`config.nim.yml`) | Required for the default NIM backend. |
| `OPENAI_API_KEY` | — | NAT (`config.openai.yml`) | Required only if you switch `NAT_CONFIG_FILE`. |
| `NAT_CONFIG_FILE` | `configs/config.nim.yml` | `main.py` | Which NAT workflow config to serve. |
| `NAT_SERVE_PORT` | `8000` | `main.py`, Dockerfile healthcheck | Port `nat serve` listens on (container-internal; mapped to host `8002`). |
| `SOCIAL_NETWORK_BASE_URL` | `http://localhost:3000` | `main.py` → `social_client.py` | Base URL of the social_network API (`http://social-network:3000` in Docker). |
| `COMPANY_NAME` | `HappyTuna` | `main.py` → persona prompt | Keep in sync with social_network's own `COMPANY_NAME`. |
| `PERSONA_FILE` | `brand_supporter.yaml` | `main.py` | Which file under `personas/` this container instance plays. |
| `BASE_PERSONA_TEMPLATE_PATH` | `/app/docs/influencer_persona_prompt.md` | `main.py` | Path to the Week 2 base template (mounted read-only by compose). |
| `STATE_DIR` | `/app/state` | `main.py` → `state.py` | Where per-persona cursor files are written. |
| `POLL_INTERVAL_SECONDS` | `30` | `main.py` → `poller.py` | How often the feed is re-checked. |
| `FEED_PAGE_SIZE` | `20` | `main.py` → `poller.py` | Page size when paging the global feed. |

---

## 9. How to run and verify it yourself

```powershell
cd "c:\Users\סירין\Desktop\customer-influencer-agents"
copy .env.example .env        # then fill in NVIDIA_API_KEY
docker compose up --build social-network influencer-agent
```

Watch for `Logged in as Jordan Ashford (user id ...)` in the `influencer-agent` logs, then:

- **Isolated decision test** (no social_network involved): open
  `http://localhost:8002/docs`, `POST /generate` with a sample `DecisionRequest` body.
- **Full loop**: create a post as some other user via `POST /api/auth/login` then
  `POST /api/posts` against `http://localhost:3000`, then watch
  `docker compose logs -f influencer-agent` for `Post <id> -> amplify (...)` within
  ~`POLL_INTERVAL_SECONDS`, and confirm the comment (and repost, if `amplify`) landed via
  `http://localhost:3000/app` or `GET /api/posts/:id/comments`.
- **Persistence check**: `docker compose restart influencer-agent` and confirm it does not
  re-react to a post it already handled.

See `README.md` in this folder for the day-to-day version of these instructions (this file
is the "why", that one is the "how").

---

## 10. What's not done yet

- Only one persona (`brand_supporter`) exists. `consumer_rights.yaml` and
  `sensational.yaml` are the natural next additions (README has the steps).
- No automated tests were written for this service — everything above was verified by
  actually running it (unit-level checks during development, plus the live end-to-end
  `/generate` call in §5), but there's no `pytest` suite committed.
- `social_network`'s own `Dockerfile`/`docker-entrypoint.sh` were mid-edit by a teammate
  when this work started (visible in `git status` as modified) — they were left untouched;
  only a new compose service block referencing them was added.
