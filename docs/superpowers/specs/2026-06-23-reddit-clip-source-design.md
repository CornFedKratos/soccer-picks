# Reddit Clip Source — Design (Phase 1)

**Date:** 2026-06-23
**Status:** Approved (design) — pending implementation plan
**Author:** Don + Claude (CRO → brainstorming)

## Problem & Goal

Soccer-Picks' core value is near-real-time highlights. Highlightly's per-goal clips
are **crowd-sourced** (scraped from social/file hosts as fans post them), so their
arrival is variable — telemetry shows 3 of the last 4 matches got no clip until the
2nd half (~+100 min after KO). No affordable alternative API fixes this; they all draw
from the same upstream well, and the only truly real-time option (Sportradar-class
official feeds) is enterprise-priced and rights-gated away from the World Cup. See
memory `soccer-picks-highlight-api-research.md`.

The fastest *legal-ish* upstream these aggregators lag behind is social media. **Goal:
source clips ourselves from that upstream, starting with Reddit r/soccer match threads**,
to beat Highlightly's latency and reduce dependence on it.

Phasing (user decision): **A) Reddit first → B) X/Twitter → C) Telegram**, only advancing
if a phase proves insufficient.

## Key Insight

The existing pipeline already does the hard part. The `clips` table + worker resolver +
Netlify converter (`match-reel-background`) already ingest streamin/streamain/bunny-CDN
clips and turn them into ad-free MP4s, caption them against `goal_events`, relay them to
Telegram, and (post-fix) never re-send. A new clip *discovery* source only needs to drop
`{clip_id, match_id, descr, src_url}` rows into `clips`; everything downstream is reused.

## Decisions (from brainstorming)

1. **Source order:** Reddit (Phase 1) → X → Telegram.
2. **Relationship to Highlightly:** run **in parallel + dedupe** (keep paying Highlightly
   for now; measure before cutting). Dedupe is natural because both ultimately point at
   the same file hosts.
3. **Trust model:** **host-allowlist + reuse existing `clipCaption()`**. Ingest any
   known-video-host link in the match thread; dedupe by host id; let the existing caption
   logic label it as a goal (scorer/minute match) or relay neutrally. Avoids the old
   per-goal "wrong clip" matching bug.
4. **Build approach:** **Approach 1 — inline in the existing `wc-goal-bot` worker**,
   called every cron tick (1/min) next to `reelSources()`. No new infra.

## Architecture

### Integration point
A new `redditSources(match)` in `wc-goal-bot/index.ts`, called in the existing
clip-discovery loop alongside `reelSources()`. It outputs the same `clips` row shape the
pipeline already consumes, then stops. Resolver → converter → caption → relay →
re-send-guard are unchanged.

### Components (each small, single-purpose)

1. **`redditAuth()`** — client-credentials OAuth token (read-only), cached in memory for
   the warm invocation, refreshed on 401. Token endpoint
   `https://www.reddit.com/api/v1/access_token`.
2. **`findMatchThread(match)`** — searches `r/soccer`
   (`/r/soccer/search?q=...&restrict_sr=1&sort=new`) for `"Match Thread"` + both team
   names, picks the freshest hit, caches the thread id on `matches.reddit_thread_id`
   (search once per match, then poll directly).
3. **`scanThreadForClips(threadId)`** — fetches newest comments
   (`/comments/{id}?sort=new&limit=200&depth=1`) and passes each body to `extractClipLinks`.
4. **`extractClipLinks(text)`** — host-allowlist regex (streamin, streamain, streamff,
   streamja, dubz, streamable, streamwo, …) returning `{url, hostId}`, deriving `hostId`
   with the same "longest id-like path segment" logic `reelSources` uses (so dedupe keys
   align across sources).
5. **`redditSources(match)`** — orchestrates 2→3→4 and upserts each clip into `clips` with
   `clip_id = hostId` (shared with Highlightly clips for dedupe; `rdt_` prefix only if a
   collision-free namespace is later needed), `descr` = comment's first line (feeds
   `clipCaption` labeling), `onConflict: clip_id, ignoreDuplicates: true`.

### Data flow
```
cron tick (1/min)
  └─ for each live match (state in/post, <=4h since KO):
       ├─ reelSources()    -> Highlightly clips ─┐
       └─ redditSources()  -> Reddit clips ──────┤
                                                  v
                            clips table (deduped by host id)
                                                  v
              existing: resolve -> download/transcode (proxy+ffmpeg)
                        -> caption (goal_events) -> relay send -> mark sent
```
Dedupe is automatic: both sources key on the same underlying file-host id, so a clip seen
by both becomes one row; whichever tick inserts first wins; the converter runs once.

## Reddit Access & Auth

- **App:** Reddit "script" app (free) → `client_id` + `secret`; client-credentials OAuth,
  read-only, no user account.
- **Endpoints:** `https://oauth.reddit.com` for data; descriptive unique `User-Agent`
  required (Reddit blocks generic/empty UA).
- **Datacenter risk + mitigation:** unauthenticated `.json` scraping is blocked from cloud
  IPs, but authenticated OAuth from datacenter is allowed within ~100 QPM (we need ~1
  thread/min). If Supabase's IP is still throttled/403'd, reuse the existing
  `RESI_PROXY_URL` egress path. **Verify in planning.**

## Error Handling (fail-safe; never breaks the worker)

- All Reddit calls in try/catch → on failure, log + return empty; Highlightly and the rest
  of the tick proceed. Reddit is purely additive.
- **401** → refresh token once, retry once, else bail this tick.
- **Thread not found** → leave `reddit_thread_id` null; retry discovery next tick (threads
  may post a few min before KO).
- **429** → back off, skip this tick.
- **Bad/dead clip link** → handled downstream (resolver verifies bytes; `CLIP_COMPRESS_TRIES=4`
  → ad-link fallback).

## Edge Cases

- **Reposts/mirrors** → collapsed by shared host-id dedupe.
- **Native Reddit video (v.redd.it) / non-allowlist hosts** → ignored in Phase 1
  (allowlist only); possible Phase 1.1.
- **Wrong-game/joke links** → rare in a match thread; a stray host-id is relayed with a
  neutral caption (not falsely a goal); dedupe + `goal_events` labeling bound the impact.
- **High-volume threads** → only newest ~200 comments per tick + dedupe; cost bounded
  regardless of thread size.

## Config / New Artifacts

- **Vault:** `reddit_client_id`, `reddit_secret`.
- **DB:** new nullable column `worldcup.matches.reddit_thread_id text`.
- **Code:** 5 functions added to `wc-goal-bot/index.ts` + one call site in the discovery
  loop. No changes to the Netlify converter, resolver, or relay.

## Out of Scope (Phase 1)

- X/Twitter (Phase B), Telegram (Phase C).
- v.redd.it / native video extraction.
- A faster-than-1/min dedicated poller (Approach 2) — only if 1/min latency proves
  insufficient.
- Canceling Highlightly — revisit after measuring Reddit in parallel.

## Assumptions to Verify in Planning

1. r/soccer match-thread **comments** still reliably carry streamin/streamja-type clip
   links for World Cup matches. If not, fall back to dedicated clip subreddits
   (r/footballhighlights) or advance to Phase B sooner.
2. Authenticated Reddit OAuth works from Supabase's datacenter IP without the proxy.

## Success Criteria

For a live match with goals, a clip appears in `clips` (Reddit-sourced) and ships to
subscribers within ~1–2 min of being posted to the r/soccer thread — measurably earlier
than Highlightly for the same goal, verified via `clips.detected_at` telemetry.

---

## REVISION 2 (2026-06-23) — pivot to public RSS submissions feed via proxy

**Why:** Reddit's OAuth Data API now requires pre-approval (2–4 weeks) for ALL apps incl.
personal — the create-app gate. AND the original assumption (clips live in match-thread
*comments*) was wrong: tracing the clip origin showed goal clips are r/soccer **posts
(submissions)** titled `Team [score] - score Team - Scorer min'` linking to streamff/
streamin (confirmed live, and matches multiple working OSS bots e.g. fenneh/discord-epl-
goal-clips which monitor r/soccer submissions). Crucially, the public **`.rss` submission
feed needs no app/OAuth/approval** and returns 200 through our existing residential proxy
(JSON is 403 from datacenter; RSS is not part of the gated Data API program).

**Revised approach (supersedes the comments/OAuth design above):**
- Poll **`https://www.reddit.com/r/soccer/new/.rss`** once per cron tick via the residential
  proxy (`Deno.createHttpClient({ proxy: { url } })` — verified working in standard Deno;
  Supabase-edge-runtime support is a deploy-time check, fallback = route the fetch through
  the Netlify function which has confirmed proxy egress).
- Parse Atom entries; for each entry extract a clip-host link from its `<content>` via
  `extractClipLinks`. Match the post `<title>` to a currently-live match by both teams'
  longest tokens (`teamMatchesTitle`). Upsert matches into `clips` (`clip_id = hostId`,
  `descr = post title` — richer than Highlightly: gives scorer+minute+score).
- The existing resolver/converter/relay/dedupe pipeline is unchanged.

**Dropped from the original design:** OAuth (`redditAuth`), Vault `reddit_client_id`/
`reddit_secret`, the manual Reddit-app step (Task 0), per-match thread discovery
(`findMatchThread`), comments scanning (`parseClipsFromComments`/`parseThreadFromSearch`),
and the `matches.reddit_thread_id` column (now unused; left in place, harmless). One feed
covers ALL live matches per tick — simpler than per-match discovery.

**New Vault secret:** `resi_proxy_url` (the worker reads it to build the proxy client).
ToS note: RSS is public and non-Data-API; use is non-commercial, <50 users, ~1 req/min —
gray-area but low-risk, with ESPN alerts + Highlightly as fallback.
