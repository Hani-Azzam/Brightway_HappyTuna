# Analytics Methodology

How we interpret social activity to research public opinion about **BrightWay**. This is the
"special methodology" of the project: every metric below has a defined input, formula, and
intent so it can be implemented and audited.

**Last updated:** 2026-06-24 · Related: [`architecture.md`](./architecture.md)

---

## 0. Guiding principles

1. **We measure opinion *and* detect events.** The other team injects company events into the
   bots, but **never tells us when an event happens.** So a core job is to infer an event's
   *footprint* from the data (volume spikes, sentiment swings, emerging topics) and quantify how
   opinion moves around it.
2. **Cheap, cached, reproducible.** Per-post signals (sentiment, aspects, topics, company
   mention) are computed **on-demand** (a researcher runs `POST /api/analytics/analyze`) and
   cached on the `Post` row. Aggregates are then computed over a time window from those cached
   signals. (Analysis is deliberately *not* run on post-create — see §5.)
3. **Hybrid analysis, deterministic fallback.** Classification uses Claude when a key is present,
   and a deterministic lexicon otherwise — so tests and offline runs are fast and reproducible.

---

## 1. The per-post analysis pipeline

When analysis runs, `sentimentService.analyzeText(content)` produces and caches, per post:

| Field | Meaning |
|---|---|
| `mentionsCompany` (bool) | content matches the **company lexicon** (see Appendix A) |
| `sentimentScore` ∈ [−1, 1] | polarity toward the subject |
| `sentimentLabel` | `positive` (score > τ⁺), `negative` (score < τ⁻), else `neutral`. Default τ⁺ = +0.15, τ⁻ = −0.15 |
| `aspects` (json) | map `aspect → score ∈ [−1,1]` for each tuna aspect the post touches (Appendix B) |
| topics/hashtags | `#hashtags` parsed from content (stored via `PostHashtag`); optional keyword topics |

**Hybrid engine**
- **Claude path** (`ANTHROPIC_API_KEY` set): `claude-haiku-4-5-20251001` is asked to return strict
  JSON: `{ sentiment: -1..1, label, aspects: {…}, mentionsCompany: bool }`. Cheap, nuanced, handles
  sarcasm/context. Optional `claude-opus-4-8` for occasional **narrative summaries** (free-text
  digests of the dominant storyline), not per-post.
- **Lexicon path** (no key / tests / offline): deterministic scorer (Appendix C). Fully
  reproducible; powers the test suite so coverage stays > 80% without API calls.

The two paths share the same output shape, so all downstream metrics are engine-agnostic.

---

## 2. Notation

- **Window** `W` — a time range (e.g. last 24h), split into **buckets** `b` (e.g. hourly).
- **Company posts** `C(W)` — posts in `W` with `mentionsCompany = true`.
- `s_p` — `sentimentScore` of post `p`. `eng_p = likes_p + reposts_p + comments_p`.
- `V(b)` — count of company posts in bucket `b`.
- `acct(u)` — account type of user `u`; `typeBoost` per Appendix D.

---

## 3. Metric catalog

### A. Headline KPIs

**A1. Opinion Index** — the headline number an exec watches.
```
OpinionIndex(W) = 100 × mean_{p∈C(W)} s_p              ∈ [−100, +100]
```
- **Engagement-weighted variant:** `100 × Σ w_p·s_p / Σ w_p`, `w_p = 1 + ln(1 + eng_p)`.
- **Influence-weighted variant (Phase 6):** `w_p = (1 + ln(1+eng_p)) × typeBoost(acct(author_p))`.
- Plotted as a **time series** by computing per bucket.

**A2. Sentiment timeline** — per bucket, the share of `C(b)` that is positive / neutral /
negative (stacked-area). Shows the mix, not just the average.

**A3. Crisis Meter** — early-warning gauge combining negativity and acceleration.
```
negShare(b)   = |negative posts in C(b)| / |C(b)|
volVelocity(b)= (V(b) − baseline(b)) / max(baseline(b), 1)        # baseline = trailing mean of V
Crisis(b)     = clamp( negShare(b) × (1 + max(0, volVelocity(b))), 0, 1 ) × 100
```
Bands (tunable): `0–30 calm · 30–60 watch · 60–80 elevated · 80–100 crisis`. A negative spike
(many new negative posts) drives it up fast; a calm or positive period keeps it low.

**A4. Share of Voice** — how much of the conversation is about BrightWay.
```
SoV(W) = |C(W)| / |all posts in W|
```

### B. Themes & narratives

**B1. Trending — current & rising.** For each hashtag/topic `t`, with `cur` = count in `W` and
`prev` = count in the preceding equal window:
```
TrendingNow(t)  = cur                                  # raw volume leaders
Rising(t)       = cur / (prev + α)    for cur ≥ floor   # growth leaders; α smoothing, floor min-volume
```
Each trend carries **per-topic sentiment** = `mean_{p uses t} s_p`.

**B2. Aspect-based sentiment** — *which issue* drives the mood. For each tuna aspect `a`
(Appendix B), over posts whose `aspects` contains `a`:
```
AspectSentiment(a, W) = mean_{p: a∈aspects_p} aspects_p[a]
AspectVolume(a, W)    = |{p : a∈aspects_p}|
```
Rendered as a bar/radar (sustainability, health/mercury, price, taste/quality, ethics/labor,
safety/recall). A recall event, for example, tanks `safety/recall` while others hold.

**B3. Narrative clusters** — group semantically-similar company posts into "takes." v1:
cluster by shared top hashtags/keywords; later: embedding similarity. Each cluster reports size,
sentiment, growth, and example posts — surfaces an emerging storyline early.

**B4. Keyword clouds split by sentiment** — top tokens (stopword-filtered) among positive vs
negative company posts: *what critics say* vs *what supporters say*.

### C. Influence & network

**C1. Influence score** per user `u`:
```
Influence(u) = ln(1 + followers(u)) + 0.5·ln(1 + repostsReceived(u)) + typeBoost(acct(u))
```
**Top influencers** list each show their **stance** = `mean s_p` over their company posts. A
high-influence account turning negative is a leading indicator.

**C2. Amplification / virality** — for post `p`:
```
Virality(p) = reposts(p) + 0.5·quoteReposts(p)         # cascade size (chains via repostOfId)
```
Top viral posts (positive vs negative) show what's actually spreading.

**C3. Polarization index** — is opinion one camp or two?
```
Polarization(W) = share(s_p > +0.5) + share(s_p < −0.5)   over C(W)     ∈ [0,1]
```
High tails + low middle ⇒ a polarized debate; mass in the middle ⇒ consensus/indifference.

**C4. Communities** — connected components / clustering on the follow graph (echo chambers).
Phase ≥ 6; v1 may approximate via shared-follow overlap.

**C5. Narrative-shaper analytics (Phase 6 — implemented).**

- **Influence-weighted Opinion Index** (`/overview` → `weightedOpinionIndex`): the opinion that is
  actually *reaching* people. Each company post is weighted by author boost × amplification:
  ```
  w_p = typeBoost(acct(author_p)) × (1 + ln(1 + likes_p + reposts_p))
  WeightedOpinionIndex = 100 × Σ(w_p·s_p) / Σ w_p
  ```
- **Cohort split** (`/cohorts`): `OpinionIndex` + sentiment mix computed per account type, plus the
  headline **shapers vs public** comparison and the **gap**:
  ```
  shapers = {journalist, influencer};  public = {regular};  official reported separately
  gap = OpinionIndex(shapers) − OpinionIndex(public)
  ```
  A wide gap = the voices with reach are ahead of (or behind) where the public sits. The official
  account is **never** folded into either group (it is company PR, not independent opinion).
- **Narrative provenance & propagation** (`/narratives`): per busy hashtag, the **earliest** poster
  is the *originator*; `origin ∈ {shaper, official, grassroots}` from their account type. Each
  narrative reports total posts, distinct authors, mean sentiment, first/last seen, and a
  **per-account-type breakdown** (`byType`) — the propagation footprint that distinguishes a
  shaper-led storyline from a grassroots one.

### D. Temporal dynamics (event footprints)

**D1. Spike / event-footprint detection.** With trailing mean `μ` and std `σ` of `V(b)`:
```
z(b) = (V(b) − μ) / max(σ, 1);   spike if z(b) ≥ k        # k ≈ 2.5
```
Each spike becomes a **"detected event"** stamped with time, magnitude `z`, dominant
hashtags/aspects in that bucket, and the concurrent sentiment shift — our inference of *when an
injected event landed and what it was about*.

**D2. Before/after shift** around a detected event at `t*`:
```
ΔIndex = OpinionIndex([t*, t*+Δ]) − OpinionIndex([t*−Δ, t*])
```

**D3. Recovery time / resilience** — time after `t*` until `OpinionIndex` returns within ε of its
pre-event baseline (or "not recovered").

**D4. Sentiment velocity** — `dOpinionIndex/dt` per bucket; flags how *fast* opinion is turning,
independent of its level.

### E. Engagement & reach

- **E1. Top posts** — by `eng_p`, split positive vs negative.
- **E2. Conversation depth** — mean/max comment-thread length on company posts; deeper threads
  ⇒ more contested issues.
- **E3. Engagement-rate trend** — `Σ eng_p / |posts|` over `W`, as a time series.

---

## 4. Tunable parameters (single source)

| Param | Default | Used by |
|---|---|---|
| Window `W` / bucket | 24h / 1h | all time-series |
| Sentiment thresholds τ⁺ / τ⁻ | +0.15 / −0.15 | label assignment |
| Polarization tails | ±0.5 | C3 |
| Spike `k` (z-score) | 2.5 | D1 |
| Trend smoothing α / floor | 1 / 5 | B1 |
| Crisis bands | 30/60/80 | A3 |

All live in config / `src/analytics/lexicon.ts` so researchers can retune without code changes.

---

## 5. Operational notes (as implemented)

- **On-demand, not on write.** Posts are analyzed when a researcher calls
  `POST /api/analytics/analyze` (`reanalyze: true` recomputes all). Results are cached on the
  Post row (`sentimentScore`, `sentimentLabel`, `aspects`, `mentionsCompany`, `analyzedAt`,
  `analyzedBy`). All metric endpoints read these cached fields.
- **AI toggle.** Claude is used only when the runtime toggle is **on** *and* a key is present
  (`activeEngine()`), otherwise the lexicon. Toggle via `GET`/`PUT /api/analytics/config`
  (in-memory; defaults from `AI_ANALYSIS_ENABLED`). Claude failures fall back to the lexicon
  per post.
- **Endpoint map.** A1–A4 → `/overview` (incl. `weightedOpinionIndex`); A2 timeline →
  `/sentiment/timeline`; B2 → `/aspects`; B1 → `/trends`; C1 → `/influencers`;
  **C5 → `/cohorts` + `/narratives`**; D1 → `/spikes`; E1 → `/top-posts`.
- **v1 simplifications (to refine later):** aspect score = the post's overall sentiment for each
  detected aspect (not sentence-restricted); Crisis Meter velocity is **capped at 1.0** so
  all-at-once data can't run away (it can still legitimately read 100 in a sustained negative
  burst, as the seed crisis arc does); narrative-shaper analytics (C5) shipped in Phase 6.

## Appendix A — Company lexicon (`mentionsCompany`)

Case-insensitive substring match against terms **derived from configuration**, not hardcoded: the
configured company name (with and without spaces) plus any `COMPANY_ALIASES` (handles, cashtags,
alternate spellings). For `COMPANY_NAME="Happy Tuna"` this matches `happy tuna`, `happytuna`,
`@happytuna`, `#happytuna`, etc. Implemented as `companyKeywords()` in `src/analytics/lexicon.ts`,
reading `src/config.ts`. Changing `COMPANY_NAME` updates detection everywhere — no code edits, and
the UI name updates with it (served via `GET /api/meta`).

## Appendix B — Tuna aspect lexicons

| Aspect | Trigger keywords (illustrative) |
|---|---|
| sustainability / dolphin-safe | dolphin, dolphin-safe, bycatch, overfishing, sustainab*, MSC, pole-and-line, ocean |
| health / mercury | mercury, contaminat*, toxin, FDA, omega-3, protein, pregnan*, health |
| price / value | price, expensive, cheap, cost, afford*, value, inflation, $ |
| taste / quality | taste, fresh, flavor, quality, texture, mushy, bland, delicious |
| ethics / labor | labor, worker, wage, forced labor, slavery, supply chain, ethical |
| safety / recall | recall, contaminated, listeria, botulism, sick, poison, lawsuit, FDA recall |

## Appendix C — Lexicon sentiment scorer (deterministic fallback)

```
pos = count of positive-lexicon hits;  neg = count of negative-lexicon hits
sentimentScore = (pos − neg) / (pos + neg + 1)            # smoothed, ∈ (−1, 1)
aspect score: same formula restricted to sentences containing that aspect's keywords
```
Negation handling: a negator (`not`, `no`, `never`) within N tokens flips the polarity of the
next sentiment word. Word lists live in `src/analytics/lexicon.ts`.

## Appendix D — Account-type boosts (`typeBoost`)

| accountType | typeBoost |
|---|---|
| regular | 1.0 |
| influencer | 1.5 |
| journalist | 1.5 |
| official | 1.0 (BrightWay's own voice — usually excluded from "public" opinion aggregates) |

Defined once in `src/utils/accountTypes.ts` (with the allowed-type validator and the shaper set),
and used by the influence-weighted Opinion Index (A1), influence score (C1), and the cohort split +
provenance (C5). For the cohort split, **shapers = {journalist, influencer}** and the **official**
account is reported on its own — never folded into "the public" — so the company's own PR doesn't
skew the measured *public* mood.
