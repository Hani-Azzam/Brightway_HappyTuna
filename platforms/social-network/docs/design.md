# Design System — BrightTweets

(The platform is branded **BrightTweets**; **BrightWay** is the tuna company it discusses.)

The frontend brief (from CLAUDE.md): **bright white, light-blue accent, intuitive & readable,
old-Twitter feel** (pre-X). This doc pins the tokens so the social app (Phase 4) and the analytics
dashboard (Phase 5) stay coherent. Tokens live in `client/src/index.css` as CSS variables.

## Thesis
An old-Twitter shell that is unmistakably *about the sea*. The layout is faithful and quiet; the
personality comes from an oceanic palette, a distinctive type pairing, and one signature motif.

## Palette
| Token | Hex | Use |
|---|---|---|
| Foam White | `#FFFFFF` | cards, surfaces |
| Sea Mist | `#F5F8FB` | app canvas background |
| Tide Blue | `#1C9DEC` | primary accent — links, buttons, active nav |
| Deep Tide | `#1483CC` | hover / pressed accent |
| Tide Wash | `#E7F4FD` | hover/selected backgrounds, accent tint |
| Ink | `#0F1419` | primary text |
| Slate | `#536471` | secondary text, icons, meta |
| Hairline | `#E5EBF0` | borders, dividers |
| Coral | `#E0245E` | like (heart), negative sentiment |
| Kelp | `#17BF63` | repost, positive sentiment |
| Sand | `#F0B429` | influencer/star, highlights |

## Type
- **Display / brand / section headers:** Space Grotesk (600–700) — distinctive grotesque, used with restraint.
- **Body / UI:** Hanken Grotesque (400–700) — humanist, friendly, highly readable.
- **Numbers** (counts, timestamps): body face with `font-variant-numeric: tabular-nums`.
- Scale: 28/20/17/15/13 px; body 15px; meta 13px. Line-height 1.4 body, 1.2 headers.

## Layout
Classic **3-column**, centered, max-width ~1250px:
- **Left (220px):** brand wordmark, primary nav (Home, Explore, Profile), Post button, account chip.
- **Center (680px):** sticky header (title + waterline), compose box, post feed.
- **Right (350px):** sticky search, Trends panel, Who-to-follow, link to the Research dashboard.
Collapses to a single column with a bottom-less top nav under 1000px; right rail hides under 1000px,
left nav becomes icon-only / a top bar under 700px.

## Signature
A 2px **waterline** — a horizontal gradient rule (Tide Blue → transparent) sitting beneath every
sticky header, evoking a sea surface. The brand wordmark pairs a 🐟 glyph with "BrightTweets" set in
Space Grotesk. Account types are first-class identity:
- **official** 🏢 — Tide Blue verified check
- **journalist** 📰 — Slate badge
- **influencer** ⭐ — Sand star
- regular — none

## Narrative-shaper UI (Phase 6)
The dashboard gains a **"Narrative shapers"** section under the charts:
- **Cohort panel** — two centered −100…+100 **opinion bars** ("Press & creators" vs "The public"),
  a **gap** callout, and a per-account-type table. Bars use Kelp (positive) / Coral (negative).
- **Narrative origins panel** — per hashtag: an **origin badge** (Shaper-led = Sand wash ·
  Company = Tide wash · Grassroots = Kelp wash), the originator's handle, and a stacked
  **propagation bar** colored by account type (journalist Slate · influencer Sand · official Tide ·
  public Kelp) showing how the topic spread.
- **Opinion Index card** — adds a hollow dashed **"ghost" marker** + caption for the
  influence-weighted index next to the solid raw marker.

In the **social app**, a profile shows a self-service **Account role** picker (pill toggles, Tide
Wash active state) — only on your own profile.

**Self-documenting dashboard.** A **"? Help"** button in the dashboard header opens a wide,
plain-English **Help modal** (two-column on desktop) explaining every metric in formal language
with its formula; full formulas live in [`analytics-methodology.md`](./analytics-methodology.md).
A faint footer credits the build team and **sparkles** on hover. Each panel header also carries a
small **ⓘ tooltip** (`InfoDot`) — a single dark popup on hover/focus (no native `title`, so it
never doubles up), keyboard-focusable and screen-reader-labelled.

**Opinion Index toggle.** The Opinion Index KPI carries a segmented **Raw / Influence-weighted**
toggle; the headline value, colour, and meter marker switch to whichever index is selected.

All copy (labels, tooltips, Help) is **company-name-agnostic** — it reads the name from
`GET /api/meta` (`useMeta`), never a hardcoded brand.

## Quality floor
Responsive to mobile, visible keyboard focus rings (Tide Wash), `prefers-reduced-motion` respected,
sentiment colors never the only signal (always paired with a label/icon).
