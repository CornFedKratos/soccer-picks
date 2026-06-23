# Automated Highlight Backfill — Design

**Date:** 2026-06-23
**Status:** Approved (design) — pending implementation plan
**Author:** Don + Claude (brainstorming)
**Builds on:** the full-time reel pipeline in `wc-goal-bot`, the Netlify converter
(`match-reel-background`, now able to download YouTube via yt-dlp + proxy), and the
Reddit clip source (`soccer-picks-reddit-clips`).

## Problem & Goal

Today the full-game highlight for a finished match is best-effort and inconsistent:
per-goal clips on file hosts (streamff/streamin) expire, per-goal YouTube clips are not
posted for every goal, and geo-locked broadcaster reels (ITV/DAZN/beIN) are skipped
entirely. Meanwhile the durable, complete asset for almost every match is the **official
full-match highlight reel on YouTube** (e.g. FIFA "Highlights | USA 4-1 Paraguay") — and
the converter can now download YouTube to an ad-free MP4.

**Goal:** an automated, game-by-game process that, for every completed match, captures the
**best available full-game highlight** and shows it on the board — preferring an official
full-match reel (downloaded to an ad-free MP4), including geo-locked reels downloaded via a
region-matched proxy, falling back to our own stitched reel, then to a US-only embed link.

## Decisions (from brainstorming)

1. **Send policy:** backfill is **board-only — NO Telegram notifications.** Only genuinely
   fresh matches (existing ~60-min window) notify subscribers; that path is unchanged.
2. **Priority order per match:**
   1. **globalReel** — official US/non-geo full-match reel (FIFA/ESPN/CBS) → download to MP4.
   2. **geoReel** — geo-locked official full-match reel (ITV/DAZN xx/beIN) → **download-only**
      via a proxy in that channel's country, re-hosted as MP4. **Never embedded.** Skipped if
      we have no proxy in its country.
   3. **stitch** — ≥2 downloadable per-goal clips (Reddit ∪ Highlightly file-host) → our MP4.
   4. **embed** — last resort, **US-based / non-geo-locked only** (geo-locked never embedded).
3. **Geo coverage + bandwidth:** free Webshare pool, best-effort + throttle. Covered
   countries from the pool: **US×5, GB×3 (ITV), ES×1 (DAZN ES), JP×1.** Uncovered (IT/FR/…)
   fall back to stitch/embed. Downloads at **≤360p**, backfill throttled to **N=2 matches/tick**,
   oldest-first. Watch bandwidth via telemetry; upgrade to Webshare Static Residential
   ($6/mo, ~unlimited bandwidth + more regions) only if we hit the 1 GB/mo cap.

## Architecture

One shared selection function (`pickBestReel`) picks the best reel by the priority order.
The existing **fresh** full-time path uses it (and still notifies). A new **throttled
backfill pass** uses it **board-only** for past matches. The converter gains a caller-chosen
proxy so the worker can force a region proxy for geo-locked reels.

### Component 1 — `pickBestReel(match)` (worker, `wc-goal-bot`)
Queries Highlightly highlights for the match and returns `{type, url, proxyUrl?}` —
the highest-priority actionable option:

- **Full-match reel classifier** (`isFullReel(title)`): title contains a reel word
  (`highlights`/`resumen`/`résumé`/`resumo`) AND a scoreline (`/\d+\s*[-–]\s*\d+/`), AND is
  NOT a per-goal/aux clip (excludes `goal`, `interview`, `press`, `conference`, `reaction`,
  `preview`, `pre-match`, `post-match press`, `train`, `shorts`, `gamified`, `alt cast`).
- **globalReel:** best `isFullReel` highlight whose channel is in `YT_PREF` (US/global:
  FIFA, ESPN FC, ESPN, CBS Sports Golazo, FOX, NBC, Telemundo, beIN SPORTS USA). Not
  geo-locked. `proxyUrl` = any (rotation).
- **geoReel:** best `isFullReel` highlight on a geo-locked channel (in `YT_BLOCK`:
  DAZN/ITV/Arena/T Sports/Sky/Viaplay/SuperSport/TNT/Optus/beIN xx) **only if** the
  channel→country map yields a country we have a proxy for. `proxyUrl` = a proxy in that country.
- **stitch:** ≥2 rows in `clips` for the match with a downloadable host. (Reuses the
  existing stitch path with `clips: [...]`.)
- **embed:** a `YT_PREF`/global reel URL when download isn't chosen/possible (US-only).

### Component 2 — Backfill driver (worker)
A new pass each tick (after the existing fresh-reel section):
- Select up to **N=2** matches with `state='post'` lacking a downloaded MP4 reel —
  `match_reels` row missing, OR status in `('embed','noclips','error')`, OR `archived`
  with null `our_url` — **ORDER BY kickoff ASC** (oldest first).
- For each: `pickBestReel` → trigger converter (global/geo/stitch) or set `embed` (US-only).
  **Board-only: never calls the Telegram send.**
- Increment `match_reels.attempts`; once `attempts >= 3` with no MP4 obtained, stop selecting
  it (leave its best embed/stitch result in place) to avoid hammering unobtainable matches.

### Component 3 — Converter changes (Netlify `match-reel-background`)
- Accept optional **`proxyUrl`** in the POST body. yt-dlp `--proxy` uses `proxyUrl` when
  present, else the env default. Lets the worker pin a *region* proxy for geo-locked reels.
- Full-reel download capped at **≤360p** (`-f "b[height<=360]/wv*[height<=360]+ba/b"`-style),
  transcoded and uploaded to `reels/<matchId>.mp4`, marked via `wc_reel_done` ready. The
  single-URL path already works (the `-user_agent`-on-local-input fix from earlier today).

### Data / new artifacts
- **Vault/secret:** `RESI_PROXY_GEO` = country-tagged proxy list, e.g.
  `gb:http://USER:PASS@31.59.20.176:6754,es:http://USER:PASS@64.137.96.74:6641,us:http://…`
  (the rotation list `RESI_PROXY_URLS` stays for global downloads).
- **Code:** `isFullReel`, channel→country map, `pickBestReel`, the backfill loop in
  `index.ts`; the `proxyUrl` + 360p handling in `match-reel-background.mjs`.
- No new DB columns required (reuses `match_reels.status/url/attempts` and `clips`).

## Error Handling / Fail-Safe
- Every step wrapped; a failed download/transcode just increments `attempts`; the match stays
  eligible (until the cap) and falls to the next-priority source next pass. Never breaks the tick.
- Geo reel with no region proxy → skipped → stitch/embed.
- Additive: the existing fresh-match send flow is untouched; backfill only populates the board.

## Telemetry
Cron response gains `backfilled` (count this tick) and a light `reelType` note (e.g.
`global/geo/stitch/embed`) so we can watch progress and proxy bandwidth.

## Out of Scope
- Sending backfilled (old) reels to subscribers (board-only by decision).
- Italy/France/other uncovered geo regions (fall back; revisit with paid proxies if wanted).
- v.redd.it native clips in the stitch (possible later via yt-dlp).
- Telegram delivery of full reels (they exceed the 20 MB sendVideo cap; fresh-send path
  unchanged — it sends the US embed link / short stitched reel as today).

## Success Criteria
Over successive ticks, every completed match ends up with the best obtainable full-game
highlight on the board: a downloaded ad-free MP4 when an official reel exists (global, or
geo-locked re-hosted via region proxy), else a stitched MP4, else a US-only embed link —
with zero old-match notifications to subscribers, verified by the board + `match_reels`.
