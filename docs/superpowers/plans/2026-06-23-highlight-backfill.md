# Automated Highlight Backfill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** For every completed match, automatically capture the best available full-game highlight on the board — preferring an official full-match reel downloaded to an ad-free MP4 (global, or geo-locked re-hosted via a region proxy), falling back to a stitched reel, then a US-only embed link — board-only, no subscriber notifications.

**Architecture:** A pure `reels.ts` module classifies highlights (`isFullReel`, `channelCountry`). The worker adds `pickBestReel(match)` (priority: globalReel → geoReel → stitch → embed) and a throttled, board-only backfill pass over past matches. The Netlify converter accepts a caller-chosen `proxyUrl` (region proxy for geo-locked) and a `maxHeight` (≤360p for reels).

**Tech Stack:** Deno, TypeScript, Supabase (Postgres `worldcup` + Storage + Vault), Highlightly API, Netlify function (Node) + yt-dlp + ffmpeg, `deno test`.

**Spec:** `docs/superpowers/specs/2026-06-23-highlight-backfill-design.md`

---

## File Structure

- **Create** `_handoff/supabase/functions/wc-goal-bot/reels.ts` — pure helpers: `isFullReel(title)`, `channelCountry(channel)`. No side effects.
- **Create** `_handoff/supabase/functions/wc-goal-bot/reels_test.ts` — `deno test` for the pure helpers.
- **Modify** `_handoff/supabase/functions/wc-goal-bot/index.ts` — geo-proxy parsing + `proxyForCountry`/`anyProxy`; import reels helpers; `pickBestReel`; `triggerReel`; rewire the new-match FT selection; add the backfill pass.
- **Modify** `_handoff/supabase/functions/wc-goal-bot/match-reel-background.mjs` — accept `proxyUrl` + `maxHeight` in the body, thread into `downloadYouTube`.
- **Secret** `RESI_PROXY_GEO` — country-tagged proxy list.

**Run deno from:** `cd /Users/dschminkey/Repos/Soccer-Picks/_handoff/supabase/functions/wc-goal-bot`. deno binary: `/Users/dschminkey/.deno/bin/deno`. Git from repo root `/Users/dschminkey/Repos/Soccer-Picks`; `_handoff/` is gitignored → `git add -f`. Deploy from `_handoff/`: `supabase functions deploy wc-goal-bot --project-ref ckldrmyzmwnujzpxxjpt --no-verify-jwt`. Do NOT push to GitHub (deploy gate). The known `deno check` realtime-js npm error is pre-existing and unrelated.

---

## Task 1: `isFullReel` in reels.ts (TDD)

**Files:**
- Create: `_handoff/supabase/functions/wc-goal-bot/reels.ts`
- Test: `_handoff/supabase/functions/wc-goal-bot/reels_test.ts`

- [ ] **Step 1: Write the failing test**

`reels_test.ts`:
```ts
import { assert, assertEquals } from "jsr:@std/assert@1";
import { isFullReel } from "./reels.ts";

Deno.test("isFullReel: FIFA full-match reel", () => {
  assert(isFullReel("Highlights | USA 4-1 Paraguay | FIFA World Cup 2026™"));
});
Deno.test("isFullReel: ITV reel with 'v' and no scoreline", () => {
  assert(isFullReel("HIGHLIGHTS - Norway v Senegal | Goals Galore! | FIFA World Cup 2026"));
});
Deno.test("isFullReel: per-goal clip is NOT a reel", () => {
  assertEquals(isFullReel("Erling Haaland Goal | Norway 3-2 Senegal"), false);
});
Deno.test("isFullReel: press conference is NOT a reel", () => {
  assertEquals(isFullReel("Post-Match Press Conference: Norway's Ståle Solbakken"), false);
});
Deno.test("isFullReel: gamified/alt-cast excluded", () => {
  assertEquals(isFullReel("Gamified Highlights: Uruguay v Cabo Verde"), false);
  assertEquals(isFullReel("Alt Cast Highlights: Jordan v Algeria"), false);
});
Deno.test("isFullReel: reaction excluded", () => {
  assertEquals(isFullReel("Reaction to Kylian Mbappe's brace in France's win"), false);
});
Deno.test("isFullReel: needs a reel word", () => {
  assertEquals(isFullReel("Norway 🆚 Senegal #FIFAWorldCupOnYT"), false);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/dschminkey/.deno/bin/deno test reels_test.ts`
Expected: FAIL — `./reels.ts` not found / `isFullReel` not exported.

- [ ] **Step 3: Write minimal implementation**

Create `reels.ts`:
```ts
// Pure helpers for classifying Highlightly highlights. No side effects.

// A "full-match reel" = has a highlights/resumen word AND is not a per-goal or auxiliary
// clip (goal, interview, press conference, reaction, preview, training, shorts, etc.).
export function isFullReel(title: string): boolean {
  const t = (title || "").toLowerCase();
  if (!/highlights|resumen|résumé|resume|resumo/.test(t)) return false;
  if (/\bgoal\b|interview|press|conference|reaction|preview|pre-?match|training|\btrain\b|#?shorts\b|gamified|alt cast|anthem/.test(t)) return false;
  return true;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/dschminkey/.deno/bin/deno test reels_test.ts`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
cd /Users/dschminkey/Repos/Soccer-Picks
git add -f _handoff/supabase/functions/wc-goal-bot/reels.ts _handoff/supabase/functions/wc-goal-bot/reels_test.ts
git commit -m "feat(reels): isFullReel classifier + tests"
```

---

## Task 2: `channelCountry` in reels.ts (TDD)

**Files:**
- Modify: `_handoff/supabase/functions/wc-goal-bot/reels.ts`
- Test: `_handoff/supabase/functions/wc-goal-bot/reels_test.ts`

- [ ] **Step 1: Write the failing test**

Append to `reels_test.ts`:
```ts
import { channelCountry } from "./reels.ts";

Deno.test("channelCountry: known geo channels", () => {
  assertEquals(channelCountry("ITV Sport"), "gb");
  assertEquals(channelCountry("DAZN ES"), "es");
  assertEquals(channelCountry("DAZN Italia"), "it");
  assertEquals(channelCountry("beIN SPORTS France"), "fr");
});
Deno.test("channelCountry: unknown/US channel returns null", () => {
  assertEquals(channelCountry("ESPN FC"), null);
  assertEquals(channelCountry("FIFA"), null);
  assertEquals(channelCountry(""), null);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/dschminkey/.deno/bin/deno test reels_test.ts`
Expected: FAIL — `channelCountry` not exported.

- [ ] **Step 3: Write minimal implementation**

Append to `reels.ts`:
```ts
// Maps a geo-locked broadcaster channel name to an ISO country code (for region-proxy download).
const CHANNEL_COUNTRY: Array<[string, string]> = [
  ["itv", "gb"], ["dazn es", "es"], ["dazn espana", "es"], ["dazn italia", "it"],
  ["bein sports france", "fr"], ["bein france", "fr"], ["dazn de", "de"],
  ["sportdigital", "de"], ["viaplay", "se"], ["supersport", "za"], ["t sports", "bd"],
  ["arena sport", "rs"], ["tnt sports", "br"], ["optus", "au"],
];
export function channelCountry(channel: string): string | null {
  const c = (channel || "").toLowerCase();
  for (const [k, v] of CHANNEL_COUNTRY) if (c.includes(k)) return v;
  return null;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/dschminkey/.deno/bin/deno test reels_test.ts`
Expected: PASS (9 passed total).

- [ ] **Step 5: Commit**

```bash
cd /Users/dschminkey/Repos/Soccer-Picks
git add -f _handoff/supabase/functions/wc-goal-bot/reels.ts _handoff/supabase/functions/wc-goal-bot/reels_test.ts
git commit -m "feat(reels): channelCountry map + tests"
```

---

## Task 3: Converter accepts `proxyUrl` + `maxHeight`

**Files:**
- Modify: `_handoff/supabase/functions/wc-goal-bot/match-reel-background.mjs`

- [ ] **Step 1: Read the file** to locate the current `downloadYouTube` function, its call site, and the body destructuring (`const { matchId, goalId, clipId, clips, uploadToken } = body;`). The exact lines may differ slightly from this plan due to prior diagnostic edits; match on the substrings below.

- [ ] **Step 2: Parameterize `downloadYouTube`** — change its signature and the two lines that use the format string and the proxy. Find the format-string line (contains `bv*[height<=720][ext=mp4]+ba[ext=m4a]`) and the proxy line (contains `args.push("--proxy"`). Change the function so it accepts `proxyUrl` and `maxH`:

Change the signature line `async function downloadYouTube(url, ffmpegPath, work, idx) {` to:
```js
async function downloadYouTube(url, ffmpegPath, work, idx, proxyUrl, maxH) {
```
Change the format-string argument from `"bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720]/b"` to:
```js
    `bv*[height<=${maxH || 720}][ext=mp4]+ba[ext=m4a]/b[height<=${maxH || 720}]/b`,
```
Change the proxy line `if (RESI_PROXY_URL) args.push("--proxy", RESI_PROXY_URL);` to:
```js
  const px = proxyUrl || RESI_PROXY_URL;
  if (px) args.push("--proxy", px);
```

- [ ] **Step 3: Thread body params to the call site.** After the body destructuring line `const { matchId, goalId, clipId, clips, uploadToken } = body;`, add:
```js
  const proxyUrl = typeof body.proxyUrl === "string" ? body.proxyUrl : "";
  const maxH = Number(body.maxHeight) || 720;
```
Find the YouTube download call (contains `await downloadYouTube(clips[i].url, ffmpegPath, work, i`) and change it to:
```js
        const yf = await downloadYouTube(clips[i].url, ffmpegPath, work, i, proxyUrl, maxH);
```

- [ ] **Step 4: Syntax check**

Run: `node --check /Users/dschminkey/Repos/Soccer-Picks/_handoff/supabase/functions/wc-goal-bot/match-reel-background.mjs`
Expected: no output (valid).

- [ ] **Step 5: Commit**

```bash
cd /Users/dschminkey/Repos/Soccer-Picks
git add -f _handoff/supabase/functions/wc-goal-bot/match-reel-background.mjs
git commit -m "feat(converter): accept proxyUrl + maxHeight for region/360p reel download"
```

- [ ] **Step 6: Push to deploy the converter** (Netlify auto-deploys from main; this is the one component that needs a GitHub push). REQUIRES explicit user OK per the deploy gate — pause and confirm before:
```bash
cd /Users/dschminkey/Repos/Soccer-Picks && git push origin main
```
Then confirm the deploy is `ready` (poll `netlify api listSiteDeploys` for the new commit, as in the project's prior deploys).

---

## Task 4: Set `RESI_PROXY_GEO` secret

**Files:** none (Supabase CLI).

- [ ] **Step 1: Set the country-tagged proxy list** (same creds, country codes from the pool: us/gb/es/jp). From `_handoff/`:
```bash
cd /Users/dschminkey/Repos/Soccer-Picks/_handoff
supabase secrets set RESI_PROXY_GEO="gb:http://rpnyfewh:4y219u5ypntr@31.59.20.176:6754,gb:http://rpnyfewh:4y219u5ypntr@45.38.107.97:6014,gb:http://rpnyfewh:4y219u5ypntr@198.105.121.200:6462,es:http://rpnyfewh:4y219u5ypntr@64.137.96.74:6641,us:http://rpnyfewh:4y219u5ypntr@31.56.127.193:7684,us:http://rpnyfewh:4y219u5ypntr@38.154.203.95:5863,us:http://rpnyfewh:4y219u5ypntr@198.23.243.226:6361,us:http://rpnyfewh:4y219u5ypntr@38.154.185.97:6370,us:http://rpnyfewh:4y219u5ypntr@191.96.254.138:6185,jp:http://rpnyfewh:4y219u5ypntr@142.111.67.146:5611" --project-ref ckldrmyzmwnujzpxxjpt
```
Expected: `Finished supabase secrets set.`

- [ ] **Step 2: No git commit** (secret only).

---

## Task 5: Worker — geo-proxy parsing + imports + proxy helpers

**Files:**
- Modify: `_handoff/supabase/functions/wc-goal-bot/index.ts`

- [ ] **Step 1: Extend the reels-helper import.** At the top of `index.ts`, after the existing `import { deriveHostId, parseGoalPostsFromFeed, teamMatchesTitle } from "./reddit.ts";` line, add:
```ts
import { isFullReel, channelCountry } from "./reels.ts";
```

- [ ] **Step 2: Add geo-proxy parsing + helpers.** Find the line `const RESI_PROXIES = (Deno.env.get("RESI_PROXY_URLS") || "").split(",").map((s) => s.trim()).filter(Boolean);` and add immediately after it:
```ts
// Country-tagged proxy pool for geo-locked reel downloads: "gb:http://...,es:http://...,us:..."
const GEO_PROXIES: Record<string, string[]> = {};
for (const part of (Deno.env.get("RESI_PROXY_GEO") || "").split(",").map((s) => s.trim()).filter(Boolean)) {
  const i = part.indexOf(":");
  if (i <= 0) continue;
  const cc = part.slice(0, i), url = part.slice(i + 1);
  (GEO_PROXIES[cc] ||= []).push(url);
}
const proxyForCountry = (cc: string | null): string | null => (cc && GEO_PROXIES[cc]?.length) ? GEO_PROXIES[cc][0] : null;
const anyProxy = (): string | null => Object.values(GEO_PROXIES).flat()[0] || RESI_PROXIES[0] || RESI_PROXY || null;
```

- [ ] **Step 3: Type-check**

Run: `cd /Users/dschminkey/Repos/Soccer-Picks/_handoff/supabase/functions/wc-goal-bot && /Users/dschminkey/.deno/bin/deno check index.ts`
Expected: no new errors (only the known pre-existing realtime-js npm error).

- [ ] **Step 4: Commit**

```bash
cd /Users/dschminkey/Repos/Soccer-Picks
git add -f _handoff/supabase/functions/wc-goal-bot/index.ts
git commit -m "feat(reels): geo-proxy pool parsing + proxyForCountry/anyProxy"
```

---

## Task 6: Worker — `pickBestReel(match)`

**Files:**
- Modify: `_handoff/supabase/functions/wc-goal-bot/index.ts` (add after the `reelSources` function, near line ~181)

- [ ] **Step 1: Add the function.** Insert immediately after the `reelSources` function's closing brace:
```ts
// Choose the best available full-game highlight for a finished match, by priority:
// global official reel (download) > geo-locked official reel (download via region proxy) >
// stitch (>=2 downloadable clips) > US-only embed link. Returns a tagged result.
async function pickBestReel(m: any): Promise<
  { type: "global" | "geo" | "stitch" | "embed" | "none"; url?: string; proxyUrl?: string | null; clips?: any[] }
> {
  let globalUrl: string | null = null, geo: { url: string; proxyUrl: string } | null = null, embedUrl: string | null = null;
  if (HL_KEY) {
    try {
      const mid = await hlMatchId(m.match_id, m.home, m.away, String(m.kickoff).slice(0, 10));
      const hl = mid ? await hlHighlights(mid) : [];
      for (const c of hl) {
        if (String(c.source || "").toLowerCase() !== "youtube") continue;
        const title = String(c.title || ""), ch = String(c.channel || "").toLowerCase();
        if (!isFullReel(title)) continue;
        const url = c.embedUrl || c.url;
        if (!url) continue;
        const blocked = YT_BLOCK.some((b) => ch.includes(b));
        if (!blocked && YT_PREF.some((p) => ch.includes(p.toLowerCase()))) {
          globalUrl ||= url; embedUrl ||= url;                          // US/global full reel
        } else if (blocked) {
          const px = proxyForCountry(channelCountry(ch));               // geo-locked: need region proxy
          if (px && !geo) geo = { url, proxyUrl: px };
        }
      }
    } catch (_) {}
  }
  if (globalUrl) return { type: "global", url: globalUrl, proxyUrl: anyProxy() };
  if (geo) return { type: "geo", url: geo.url, proxyUrl: geo.proxyUrl };
  // stitch: >=2 downloadable clips already collected in the clips table for this match
  const cl = await sb.from("clips").select("src_url,descr").eq("match_id", m.match_id).limit(12);
  const clips = (cl.data || []).filter((x: any) => x.src_url);
  if (clips.length >= 2) return { type: "stitch", clips: clips.map((x: any) => ({ label: x.descr, url: x.src_url })) };
  if (embedUrl) return { type: "embed", url: embedUrl };
  return { type: "none" };
}
```

- [ ] **Step 2: Type-check**

Run: `cd /Users/dschminkey/Repos/Soccer-Picks/_handoff/supabase/functions/wc-goal-bot && /Users/dschminkey/.deno/bin/deno check index.ts`
Expected: no new errors.

- [ ] **Step 3: Commit**

```bash
cd /Users/dschminkey/Repos/Soccer-Picks
git add -f _handoff/supabase/functions/wc-goal-bot/index.ts
git commit -m "feat(reels): pickBestReel selection (global/geo/stitch/embed)"
```

---

## Task 7: Worker — `triggerReel` helper + rewire new-match FT selection

**Files:**
- Modify: `_handoff/supabase/functions/wc-goal-bot/index.ts`

- [ ] **Step 1: Add `triggerReel`.** Insert immediately after `pickBestReel` (from Task 6):
```ts
// Kick the Netlify converter to render reels/<matchId>.mp4 from a reel result. For YouTube
// (global/geo) we send the single URL + a proxy (region proxy for geo) at <=360p; for stitch
// we send the clip list. Returns true if the render was accepted.
async function triggerReel(matchId: string, pick: { type: string; url?: string; proxyUrl?: string | null; clips?: any[] }): Promise<boolean> {
  let token: any = null;
  try { const s = await sb.storage.from("reels").createSignedUploadUrl(`${matchId}.mp4`, { upsert: true }); token = (s as any)?.data?.token; } catch (_) {}
  if (!token) return false;
  const secret = await getVault("reel_trigger_secret");
  const body: any = { secret, matchId, uploadToken: token };
  if (pick.type === "stitch") { body.clips = pick.clips; }
  else { body.clips = [{ url: pick.url }]; body.proxyUrl = pick.proxyUrl || anyProxy(); body.maxHeight = 360; }
  try {
    const r = await fetch(REEL_FN, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
    return r.ok || r.status === 202;
  } catch (_) { return false; }
}
```

- [ ] **Step 2: Rewire the new-match selection.** In the full-time reel section, find this block (currently `index.ts:538-558`):
```ts
        const src = await reelSources(m.match_id, m.home, m.away, String(m.kickoff).slice(0, 10));
        if (src.streamff.length >= 2) {
          // ad-free path: stitch our own short reel from streamff clips
          let token = null;
          try { const s = await sb.storage.from("reels").createSignedUploadUrl(`${m.match_id}.mp4`, { upsert: true }); token = (s as any)?.data?.token; } catch (_) {}
          if (!token) continue;
          const secret = await getVault("reel_trigger_secret");
          let ok = false;
          try {
            const r = await fetch(REEL_FN, { method: "POST", headers: { "content-type": "application/json" },
              body: JSON.stringify({ secret, matchId: m.match_id, uploadToken: token, clips: src.streamff.map((c) => ({ label: c.label, url: c.url })) }) });
            ok = r.ok || r.status === 202;
          } catch (_) {}
          if (ok) { await sb.from("match_reels").insert({ match_id: m.match_id, status: "rendering", attempts: 1 }); out.reelsQueued++; }
        } else if (src.youtube) {
          // no streamff reel: embed a US-available YouTube highlight (no download/storage)
          await sb.from("match_reels").insert({ match_id: m.match_id, status: "embed", url: src.youtube, attempts: 1 });
          out.embeds++;
        } else {
          await sb.from("match_reels").insert({ match_id: m.match_id, status: "noclips", attempts: 1 });
        }
```
Replace it with:
```ts
        const pick = await pickBestReel(m);
        if (pick.type === "global" || pick.type === "geo" || pick.type === "stitch") {
          if (await triggerReel(m.match_id, pick)) {
            await sb.from("match_reels").insert({ match_id: m.match_id, status: "rendering", attempts: 1 });
            out.reelsQueued++;
          }
        } else if (pick.type === "embed") {
          await sb.from("match_reels").insert({ match_id: m.match_id, status: "embed", url: pick.url, attempts: 1 });
          out.embeds++;
        } else {
          await sb.from("match_reels").insert({ match_id: m.match_id, status: "noclips", attempts: 1 });
        }
```

- [ ] **Step 3: Type-check**

Run: `cd /Users/dschminkey/Repos/Soccer-Picks/_handoff/supabase/functions/wc-goal-bot && /Users/dschminkey/.deno/bin/deno check index.ts`
Expected: no new errors.

- [ ] **Step 4: Commit**

```bash
cd /Users/dschminkey/Repos/Soccer-Picks
git add -f _handoff/supabase/functions/wc-goal-bot/index.ts
git commit -m "feat(reels): triggerReel + new-match selection via pickBestReel"
```

---

## Task 8: Worker — board-only backfill pass

**Files:**
- Modify: `_handoff/supabase/functions/wc-goal-bot/index.ts`

- [ ] **Step 1: Replace the old fallback loop with a real backfill.** Find the current fallback block (`index.ts:583-592`, begins with the comment `// fallback: backfill matches that have no usable stitched reel`):
```ts
      // fallback: backfill matches that have no usable stitched reel (noclips / failed render) with a
      // US-available YouTube embed if one exists — also recovers future stitch failures. Throttled.
      const fb = await sb.from("match_reels").select("match_id").in("status", ["noclips", "error"]).limit(8);
      for (const row of (fb.data || [])) {
        const mm = await sb.from("matches").select("home,away,kickoff").eq("match_id", row.match_id).maybeSingle();
        if (!mm.data) continue;
        const src = await reelSources(row.match_id, mm.data.home, mm.data.away, String(mm.data.kickoff).slice(0, 10));
        if (src.youtube) { await sb.from("match_reels").update({ status: "embed", url: src.youtube }).eq("match_id", row.match_id); out.embeds++; }
        else { await sb.from("match_reels").update({ status: "nohl" }).eq("match_id", row.match_id); } // terminal: no US-available source, stop re-checking
      }
```
Replace it with:
```ts
      // BACKFILL (board-only, never notifies): upgrade past matches that lack a downloaded MP4 reel
      // to the best obtainable reel. Throttled, oldest-first, capped attempts so dead matches stop.
      const BACKFILL_N = 2, BACKFILL_MAX_ATTEMPTS = 3;
      const bf = await sb.from("match_reels")
        .select("match_id,attempts")
        .in("status", ["embed", "noclips", "error"])
        .lt("attempts", BACKFILL_MAX_ATTEMPTS)
        .limit(40);
      const bfRows = bf.data || [];
      // join to matches for oldest-first ordering + team names
      const bfMatches: any[] = [];
      for (const row of bfRows) {
        const mm = await sb.from("matches").select("match_id,home,away,kickoff").eq("match_id", row.match_id).maybeSingle();
        if (mm.data) bfMatches.push({ ...mm.data, attempts: row.attempts ?? 0 });
      }
      bfMatches.sort((a, b) => new Date(a.kickoff).getTime() - new Date(b.kickoff).getTime());
      let bfDone = 0;
      for (const m of bfMatches) {
        if (bfDone >= BACKFILL_N) break;
        bfDone++;
        const pick = await pickBestReel(m);
        if (pick.type === "global" || pick.type === "geo" || pick.type === "stitch") {
          if (await triggerReel(m.match_id, pick)) {
            await sb.from("match_reels").update({ status: "rendering", attempts: (m.attempts ?? 0) + 1 }).eq("match_id", m.match_id);
            (out as any).backfilled = ((out as any).backfilled || 0) + 1;
            (out as any).reelType = pick.type;
          } else {
            await sb.from("match_reels").update({ attempts: (m.attempts ?? 0) + 1 }).eq("match_id", m.match_id);
          }
        } else if (pick.type === "embed") {
          await sb.from("match_reels").update({ status: "embed", url: pick.url, attempts: (m.attempts ?? 0) + 1 }).eq("match_id", m.match_id);
        } else {
          // nothing obtainable this pass; bump attempts so it eventually drops out of the backfill set
          await sb.from("match_reels").update({ attempts: (m.attempts ?? 0) + 1 }).eq("match_id", m.match_id);
        }
      }
```

(Note: a rendered reel that later flips to `ready` is sent to subscribers ONLY by the existing fresh-window check at lines ~562-571 — old backfilled matches fail that freshness test and are archived board-only, so backfill never notifies. No change needed there.)

- [ ] **Step 2: Type-check**

Run: `cd /Users/dschminkey/Repos/Soccer-Picks/_handoff/supabase/functions/wc-goal-bot && /Users/dschminkey/.deno/bin/deno check index.ts`
Expected: no new errors.

- [ ] **Step 3: Commit**

```bash
cd /Users/dschminkey/Repos/Soccer-Picks
git add -f _handoff/supabase/functions/wc-goal-bot/index.ts
git commit -m "feat(reels): board-only throttled backfill pass (oldest-first, attempts cap)"
```

---

## Task 9: Deploy + live verify

**Files:** none.

- [ ] **Step 1: Confirm the converter (Task 3) is deployed on Netlify** (it was pushed + verified ready in Task 3 Step 6). If not, do that first — the worker's reel downloads depend on it.

- [ ] **Step 2: Deploy the worker** from `_handoff/`:
```bash
cd /Users/dschminkey/Repos/Soccer-Picks/_handoff
supabase functions deploy wc-goal-bot --project-ref ckldrmyzmwnujzpxxjpt --no-verify-jwt
```
Expected: `Deployed Functions on project ckldrmyzmwnujzpxxjpt: wc-goal-bot`.

- [ ] **Step 3: Seed a backfill candidate (USA-Paraguay) and force ticks.** Ensure USA-Paraguay is eligible (it has an official FIFA reel). Via Supabase MCP `execute_sql`, set/insert its `match_reels` to a backfillable state:
```sql
insert into worldcup.match_reels (match_id, status, attempts)
  values ('<usa_paraguay_match_id>', 'noclips', 0)
  on conflict (match_id) do update set status='noclips', attempts=0;
```
(Find the ESPN `match_id` for USA-Paraguay in `worldcup.matches` where home/away ilike USA/Paraguay.) Then force two ticks ~90s apart:
```bash
curl -s -X POST "https://ckldrmyzmwnujzpxxjpt.supabase.co/functions/v1/wc-goal-bot" -H "x-cron-secret: <wc_cron_secret>" | python3 -c "import sys,json;d=json.load(sys.stdin);print('backfilled',d.get('backfilled'),'reelType',d.get('reelType'),'reelsQueued',d.get('reelsQueued'))"
```
Expected: a tick reports `backfilled: 1 reelType: global` (USA-Paraguay selected → FIFA reel download triggered).

- [ ] **Step 4: Verify the MP4 landed on the board, board-only.** After ~1–2 min for the render:
```sql
select match_id, status, our_url, url, attempts from worldcup.match_reels where match_id='<usa_paraguay_match_id>';
```
Expected: `status='ready'` (or `sent`/`archived`) with a stored `reels/<id>.mp4` URL. Because USA-Paraguay finished >1h ago, it must NOT be sent — confirm `status` is `archived` (board-only), NOT `sent`, and that `out.reelsSent` did not increment for it.

- [ ] **Step 5: Confirm no subscriber notifications fired for backfilled (old) matches** — check the tick responses across Step 3: `reelsSent`/`embedsSent` should stay 0 for old matches (only the board is populated). Spot-check `wc_reels()` shows the new MP4 for USA-Paraguay on the board.

- [ ] **Step 6: (If a geo-locked-only match exists, e.g. an ITV-only game) seed it the same way and confirm `reelType: geo`** and a stored MP4 (downloaded via the GB proxy). If none is available, note it and rely on the global-reel verification.

- [ ] **Step 7: Report** the backfill telemetry (counts, reelType breakdown) and confirm: board populated, zero old-match sends.

---

## Self-Review Notes (completed by plan author)

- **Spec coverage:** priority order → `pickBestReel` (T6); global download + geo region-proxy download + 360p → `triggerReel` (T7) + converter `proxyUrl`/`maxHeight` (T3); geo channel→country→proxy → `channelCountry` (T2) + `RESI_PROXY_GEO`/`proxyForCountry` (T4/T5); full-reel classifier → `isFullReel` (T1); board-only throttled oldest-first backfill w/ attempts cap → T8; "geo download-only, embed US-only" → enforced in `pickBestReel` (geo never enters the `embed` branch; embed only from `YT_PREF`); telemetry → `backfilled`/`reelType` (T8); no old-match notifications → unchanged fresh-window gate (T8 note).
- **Placeholder scan:** none — all code/SQL/commands concrete. `<usa_paraguay_match_id>`, `<wc_cron_secret>` are runtime values the executor supplies (the cron secret is in Vault `wc_cron_secret`; the match_id is looked up in Step 3).
- **Type consistency:** `pickBestReel` returns `{type,url?,proxyUrl?,clips?}`; `triggerReel(matchId, pick)` consumes exactly those fields; `isFullReel(title)`/`channelCountry(channel)` signatures match their imports and call sites; `proxyForCountry`/`anyProxy` return `string|null` consistent with `triggerReel` usage.
- **Deploy-gate note:** only Task 3 Step 6 pushes to GitHub (converter → Netlify) and is explicitly gated on user OK; everything else is local commits + Supabase CLI deploy.
