# Reddit Clip Source (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Source near-real-time goal clips directly from r/soccer match threads and feed them into the existing clip pipeline, beating Highlightly's latency.

**Architecture:** Add a fail-safe `redditSources(match)` to the `wc-goal-bot` Deno edge function, called each cron tick (1/min) alongside `reelSources()`. It finds the r/soccer match thread, scans new comments for known-host clip links, and upserts them into the `clips` table — where the existing resolver → converter → caption → relay take over. Pure parsing helpers live in a new `reddit.ts` (unit-tested with `deno test`); IO glue lives in `index.ts`.

**Tech Stack:** Deno, TypeScript, Supabase (Postgres `worldcup` schema + Vault), Reddit OAuth API (client-credentials), `deno test`.

**Spec:** `docs/superpowers/specs/2026-06-23-reddit-clip-source-design.md`

---

## File Structure

- **Create** `_handoff/supabase/functions/wc-goal-bot/reddit.ts` — pure, testable helpers: `deriveHostId`, `CLIP_HOST_RE`, `extractClipLinks`, `parseThreadFromSearch`, `parseClipsFromComments`. No top-level side effects, no env access.
- **Create** `_handoff/supabase/functions/wc-goal-bot/reddit_test.ts` — `deno test` unit tests for the pure helpers.
- **Create** `_handoff/supabase/functions/wc-goal-bot/verify_reddit.ts` — standalone local script (NOT imported by `index.ts`, so excluded from the deployed bundle) that hits live Reddit to verify the spec's assumptions before wiring into the worker.
- **Modify** `_handoff/supabase/functions/wc-goal-bot/index.ts` — import `deriveHostId` (refactor `reelSources` to use it for dedupe alignment); add `redditAuth`, `findMatchThread`, `scanThreadForClips`, `redditSources`; add the call site in the discovery loop; ensure `reddit_thread_id` is selected on match rows.
- **DB migration** — add `worldcup.matches.reddit_thread_id text`.
- **Vault** — add `reddit_client_id`, `reddit_secret`.

**Note on deno availability:** `deno` is installed at `/Users/dschminkey/.deno/bin/deno`. Run all `deno` commands from the function directory: `cd /Users/dschminkey/Repos/Soccer-Picks/_handoff/supabase/functions/wc-goal-bot`.

---

## Task 0: Create the Reddit app (MANUAL — user action, prerequisite)

This cannot be automated. The user must do this once and provide three values.

- [ ] **Step 1: Create a Reddit "script" app**

Go to https://www.reddit.com/prefs/apps → "create another app" → choose **script** type → name `soccer-picks` → redirect uri `http://localhost:8080` (unused but required). After creating, record:
- **client_id** — the string under the app name (just under "personal use script")
- **secret** — the `secret` field
- **reddit username** — the account that owns the app (used in the required User-Agent)

- [ ] **Step 2: Hand the three values to the implementer** (client_id, secret, username). These go into Vault in Task 7 and into the local env for Task 5's verification run. Do NOT commit them to any file.

---

## Task 1: `deriveHostId` in reddit.ts (TDD)

Extracts the dedupe id from a clip URL — identical algorithm to `index.ts:163-164` so Reddit and Highlightly clips collapse to the same `clip_id`.

**Files:**
- Create: `_handoff/supabase/functions/wc-goal-bot/reddit.ts`
- Test: `_handoff/supabase/functions/wc-goal-bot/reddit_test.ts`

- [ ] **Step 1: Write the failing test**

In `reddit_test.ts`:
```ts
import { assertEquals } from "jsr:@std/assert@1";
import { deriveHostId } from "./reddit.ts";

Deno.test("deriveHostId: streamin.link/v/<id>", () => {
  assertEquals(deriveHostId("https://streamin.link/v/aB3dEf9k"), "aB3dEf9k");
});
Deno.test("deriveHostId: streamain watch URL skips 'watch'", () => {
  assertEquals(deriveHostId("https://streamain.com/HVGs0IIgcnH2WTd/watch"), "HVGs0IIgcnH2WTd");
});
Deno.test("deriveHostId: strips query and hash", () => {
  assertEquals(deriveHostId("https://streamff.live/v/Xy12Zk90?t=3#x"), "Xy12Zk90");
});
Deno.test("deriveHostId: no id-like segment returns null", () => {
  assertEquals(deriveHostId("https://example.com/a/b"), null);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `deno test reddit_test.ts`
Expected: FAIL — module `./reddit.ts` not found / `deriveHostId` not exported.

- [ ] **Step 3: Write minimal implementation**

Create `reddit.ts`:
```ts
// Pure, testable helpers for sourcing clips from r/soccer match threads.
// No top-level side effects and no env access — safe to import in tests.

// Dedupe id from a clip page URL. MUST match index.ts reelSources so Reddit and
// Highlightly clips for the same goal collapse to one clips row.
export function deriveHostId(url: string): string | null {
  const segs = String(url || "").split("?")[0].split("#")[0].split("/").filter(Boolean);
  const id = segs.reverse().find((s) =>
    /^[A-Za-z0-9_-]{6,}$/.test(s) &&
    !["watch", "embed", "video", "http:", "https:"].includes(s.toLowerCase()));
  return id || null;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `deno test reddit_test.ts`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
cd /Users/dschminkey/Repos/Soccer-Picks
git add _handoff/supabase/functions/wc-goal-bot/reddit.ts _handoff/supabase/functions/wc-goal-bot/reddit_test.ts
git commit -m "feat(reddit): deriveHostId pure helper + tests"
```
(Note: `_handoff/` is gitignored for deploy purposes, but these source files should be committed for history. If `git add` reports the path is ignored, use `git add -f` for the two files.)

---

## Task 2: `CLIP_HOST_RE` + `extractClipLinks` in reddit.ts (TDD)

Finds known-video-host links in arbitrary comment text and dedupes them by host id.

**Files:**
- Modify: `_handoff/supabase/functions/wc-goal-bot/reddit.ts`
- Test: `_handoff/supabase/functions/wc-goal-bot/reddit_test.ts`

- [ ] **Step 1: Write the failing test**

Append to `reddit_test.ts`:
```ts
import { extractClipLinks } from "./reddit.ts";

Deno.test("extractClipLinks: finds a streamin link", () => {
  const r = extractClipLinks("GOAL Ronaldo! https://streamin.link/v/aB3dEf9k great finish");
  assertEquals(r.length, 1);
  assertEquals(r[0].hostId, "aB3dEf9k");
  assertEquals(r[0].url, "https://streamin.link/v/aB3dEf9k");
});
Deno.test("extractClipLinks: adds https:// when missing", () => {
  const r = extractClipLinks("mirror: streamja.com/abcdef");
  assertEquals(r[0].url, "https://streamja.com/abcdef");
});
Deno.test("extractClipLinks: dedupes same host id", () => {
  const r = extractClipLinks("https://streamin.link/v/aB3dEf9k and https://streamin.link/v/aB3dEf9k");
  assertEquals(r.length, 1);
});
Deno.test("extractClipLinks: ignores non-allowlisted hosts", () => {
  assertEquals(extractClipLinks("https://youtube.com/watch?v=zzzzzz https://example.com/x").length, 0);
});
Deno.test("extractClipLinks: multiple distinct hosts", () => {
  const r = extractClipLinks("https://streamin.link/v/aaaaaa1 https://dubz.link/v/bbbbbb2");
  assertEquals(r.length, 2);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `deno test reddit_test.ts`
Expected: FAIL — `extractClipLinks` not exported.

- [ ] **Step 3: Write minimal implementation**

Append to `reddit.ts`:
```ts
// Known fan-clip video hosts seen in r/soccer match threads. The Netlify resolver
// already turns these pages into mp4s (or falls back to the ad link).
export const CLIP_HOST_RE =
  /((?:https?:\/\/)?(?:www\.)?(?:streamin\.[a-z]+|streamain\.[a-z]+|streamff\.[a-z]+|streamja\.com|dubz\.(?:link|co)|streamable\.com|streamwo\.[a-z]+|streamvi\.[a-z]+)\/[^\s)\]>"']+)/gi;

export function extractClipLinks(text: string): { url: string; hostId: string }[] {
  const out: { url: string; hostId: string }[] = [];
  const seen = new Set<string>();
  const body = String(text || "");
  CLIP_HOST_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = CLIP_HOST_RE.exec(body)) !== null) {
    let url = m[1].replace(/[.,);\]]+$/, ""); // strip trailing punctuation
    if (!/^https?:\/\//i.test(url)) url = "https://" + url;
    const hostId = deriveHostId(url);
    if (hostId && !seen.has(hostId)) { seen.add(hostId); out.push({ url, hostId }); }
  }
  return out;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `deno test reddit_test.ts`
Expected: PASS (9 passed total).

- [ ] **Step 5: Commit**

```bash
cd /Users/dschminkey/Repos/Soccer-Picks
git add -f _handoff/supabase/functions/wc-goal-bot/reddit.ts _handoff/supabase/functions/wc-goal-bot/reddit_test.ts
git commit -m "feat(reddit): extractClipLinks host-allowlist parser + tests"
```

---

## Task 3: `parseThreadFromSearch` in reddit.ts (TDD)

Picks the match thread out of a Reddit search listing by matching "match thread" + the longest token of each team name (robust to "Congo DR" vs "DR Congo" ordering).

**Files:**
- Modify: `_handoff/supabase/functions/wc-goal-bot/reddit.ts`
- Test: `_handoff/supabase/functions/wc-goal-bot/reddit_test.ts`

- [ ] **Step 1: Write the failing test**

Append to `reddit_test.ts`:
```ts
import { parseThreadFromSearch } from "./reddit.ts";

const searchJson = {
  data: { children: [
    { data: { id: "zz111", title: "Post Match Thread: Portugal 3-0 Uzbekistan" } },
    { data: { id: "ab222", title: "Match Thread: Portugal vs Uzbekistan | FIFA World Cup" } },
    { data: { id: "cd333", title: "Match Thread: France vs Iraq" } },
  ] },
};

Deno.test("parseThreadFromSearch: matches by team tokens, ignores post-match", () => {
  const r = parseThreadFromSearch(searchJson, "Portugal", "Uzbekistan");
  assertEquals(r?.id, "ab222");
});
Deno.test("parseThreadFromSearch: token match handles name ordering", () => {
  const j = { data: { children: [
    { data: { id: "ee444", title: "Match Thread: Portugal vs DR Congo" } },
  ] } };
  assertEquals(parseThreadFromSearch(j, "Congo DR", "Portugal")?.id, "ee444");
});
Deno.test("parseThreadFromSearch: no match returns null", () => {
  assertEquals(parseThreadFromSearch(searchJson, "Brazil", "Spain"), null);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `deno test reddit_test.ts`
Expected: FAIL — `parseThreadFromSearch` not exported.

- [ ] **Step 3: Write minimal implementation**

Append to `reddit.ts`:
```ts
const rnorm = (s: string) =>
  (s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
// longest alphabetic token in a team name (e.g. "DR Congo" -> "congo")
const longestTok = (s: string) =>
  rnorm(s).split(/[^a-z]+/).filter((w) => w.length >= 3).sort((a, b) => b.length - a.length)[0] || rnorm(s);

export function parseThreadFromSearch(
  json: any, home: string, away: string,
): { id: string; title: string } | null {
  const h = longestTok(home), a = longestTok(away);
  const kids = json?.data?.children || [];
  for (const k of kids) {
    const title = String(k?.data?.title || "");
    const t = rnorm(title);
    if (t.includes("match thread") && !t.includes("post match") && !t.includes("pre match")
        && t.includes(h) && t.includes(a)) {
      return { id: String(k.data.id), title };
    }
  }
  return null;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `deno test reddit_test.ts`
Expected: PASS (12 passed total).

- [ ] **Step 5: Commit**

```bash
cd /Users/dschminkey/Repos/Soccer-Picks
git add -f _handoff/supabase/functions/wc-goal-bot/reddit.ts _handoff/supabase/functions/wc-goal-bot/reddit_test.ts
git commit -m "feat(reddit): parseThreadFromSearch + tests"
```

---

## Task 4: `parseClipsFromComments` in reddit.ts (TDD)

Pulls clip links + a short caption out of a Reddit comments listing (the `[post, comments]` two-element array Reddit returns).

**Files:**
- Modify: `_handoff/supabase/functions/wc-goal-bot/reddit.ts`
- Test: `_handoff/supabase/functions/wc-goal-bot/reddit_test.ts`

- [ ] **Step 1: Write the failing test**

Append to `reddit_test.ts`:
```ts
import { parseClipsFromComments } from "./reddit.ts";

const commentsJson = [
  { data: { children: [] } }, // [0] = the post (t3)
  { data: { children: [      // [1] = comments (t1)
    { data: { body: "GOAL! Ronaldo 1-0\nhttps://streamin.link/v/aaaaaa1" } },
    { data: { body: "no link here, just chat" } },
    { data: { body: "mirror https://dubz.link/v/bbbbbb2" } },
    { data: { body: "repost https://streamin.link/v/aaaaaa1" } },
  ] } },
];

Deno.test("parseClipsFromComments: extracts deduped clips with captions", () => {
  const r = parseClipsFromComments(commentsJson);
  assertEquals(r.length, 2);
  assertEquals(r[0].hostId, "aaaaaa1");
  assertEquals(r[0].descr, "GOAL! Ronaldo 1-0");
  assertEquals(r[1].hostId, "bbbbbb2");
});
Deno.test("parseClipsFromComments: empty/garbage returns []", () => {
  assertEquals(parseClipsFromComments(null).length, 0);
  assertEquals(parseClipsFromComments([{}, {}]).length, 0);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `deno test reddit_test.ts`
Expected: FAIL — `parseClipsFromComments` not exported.

- [ ] **Step 3: Write minimal implementation**

Append to `reddit.ts`:
```ts
export function parseClipsFromComments(
  json: any,
): { url: string; hostId: string; descr: string }[] {
  const out: { url: string; hostId: string; descr: string }[] = [];
  const seen = new Set<string>();
  const listing = Array.isArray(json) ? json[1] : json; // [t3 post, t1 comments]
  const kids = listing?.data?.children || [];
  for (const k of kids) {
    const body = String(k?.data?.body || "");
    const firstLine = body.split("\n").map((s) => s.trim()).find(Boolean) || "";
    for (const { url, hostId } of extractClipLinks(body)) {
      if (!seen.has(hostId)) { seen.add(hostId); out.push({ url, hostId, descr: firstLine.slice(0, 200) }); }
    }
  }
  return out;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `deno test reddit_test.ts`
Expected: PASS (14 passed total).

- [ ] **Step 5: Commit**

```bash
cd /Users/dschminkey/Repos/Soccer-Picks
git add -f _handoff/supabase/functions/wc-goal-bot/reddit.ts _handoff/supabase/functions/wc-goal-bot/reddit_test.ts
git commit -m "feat(reddit): parseClipsFromComments + tests"
```

---

## Task 5: Standalone live verification (ASSUMPTION GATE)

Before touching the worker, prove against live Reddit that (a) OAuth works, (b) we can find a World Cup match thread, and (c) its comments actually contain clip links. If (c) fails, STOP and revisit the spec (fall back to r/footballhighlights or advance to Phase B).

**Files:**
- Create: `_handoff/supabase/functions/wc-goal-bot/verify_reddit.ts`

- [ ] **Step 1: Write the verification script**

Create `verify_reddit.ts`:
```ts
// Local-only. Run: REDDIT_CLIENT_ID=.. REDDIT_SECRET=.. REDDIT_UA=.. \
//   deno run --allow-net --allow-env verify_reddit.ts "Portugal" "Uzbekistan"
import { parseThreadFromSearch, parseClipsFromComments } from "./reddit.ts";

const [home, away] = Deno.args;
const id = Deno.env.get("REDDIT_CLIENT_ID")!, secret = Deno.env.get("REDDIT_SECRET")!;
const UA = Deno.env.get("REDDIT_UA") || "soccer-picks/1.0 (verify)";

const tr = await fetch("https://www.reddit.com/api/v1/access_token", {
  method: "POST",
  headers: { Authorization: "Basic " + btoa(`${id}:${secret}`), "Content-Type": "application/x-www-form-urlencoded", "User-Agent": UA },
  body: "grant_type=client_credentials",
});
console.log("auth status", tr.status);
const tok = (await tr.json()).access_token;
if (!tok) { console.log("NO TOKEN — check creds"); Deno.exit(1); }

const q = encodeURIComponent(`Match Thread ${home} ${away}`);
const sr = await fetch(`https://oauth.reddit.com/r/soccer/search?q=${q}&restrict_sr=1&sort=new&limit=15&t=week`,
  { headers: { Authorization: `Bearer ${tok}`, "User-Agent": UA } });
console.log("search status", sr.status);
const thread = parseThreadFromSearch(await sr.json(), home, away);
console.log("thread:", thread);
if (!thread) { console.log("NO THREAD FOUND"); Deno.exit(2); }

const cr = await fetch(`https://oauth.reddit.com/comments/${thread.id}?sort=new&limit=200&depth=1`,
  { headers: { Authorization: `Bearer ${tok}`, "User-Agent": UA } });
console.log("comments status", cr.status);
const clips = parseClipsFromComments(await cr.json());
console.log(`CLIPS FOUND: ${clips.length}`);
for (const c of clips.slice(0, 10)) console.log(" -", c.hostId, "|", c.url, "|", c.descr.slice(0, 50));
```

- [ ] **Step 2: Run it against a recent/live WC match** (use the creds from Task 0; pick a match that played in the last few days)

Run:
```bash
cd /Users/dschminkey/Repos/Soccer-Picks/_handoff/supabase/functions/wc-goal-bot
REDDIT_CLIENT_ID=<id> REDDIT_SECRET=<secret> REDDIT_UA="soccer-picks/1.0 (by /u/<username>)" \
  /Users/dschminkey/.deno/bin/deno run --allow-net --allow-env verify_reddit.ts "Norway" "Senegal"
```
Expected: `auth status 200`, `search status 200`, a `thread:` object, `comments status 200`, and **`CLIPS FOUND: N` with N ≥ 1** plus sample host links.

- [ ] **Step 3: Decision gate**

If `CLIPS FOUND` ≥ 1 with real clip hosts → assumption holds, proceed to Task 6.
If 0 clips across two or three recent matches → STOP. The r/soccer comment-link assumption is false; do not wire into the worker. Report to the user and revisit the spec (try `restrict_sr` off, a clip subreddit, or Phase B).

- [ ] **Step 4: Commit the script** (creds were only in env, never in the file)

```bash
cd /Users/dschminkey/Repos/Soccer-Picks
git add -f _handoff/supabase/functions/wc-goal-bot/verify_reddit.ts
git commit -m "chore(reddit): local live-verification script"
```

---

## Task 6: DB migration — add `matches.reddit_thread_id`

**Files:** none (run via Supabase MCP `apply_migration` against project `ckldrmyzmwnujzpxxjpt`).

- [ ] **Step 1: Apply the migration**

Use the Supabase MCP `apply_migration` tool, name `add_reddit_thread_id`, query:
```sql
alter table worldcup.matches add column if not exists reddit_thread_id text;
```

- [ ] **Step 2: Verify the column exists**

Run via MCP `execute_sql`:
```sql
select column_name from information_schema.columns
where table_schema='worldcup' and table_name='matches' and column_name='reddit_thread_id';
```
Expected: one row, `reddit_thread_id`.

- [ ] **Step 3: No git commit** (schema change is in the DB, not the repo).

---

## Task 7: Vault — add Reddit credentials + verify `app_secret` exposure

**Files:** none (Supabase MCP `execute_sql`). Uses the values from Task 0.

- [ ] **Step 1: Insert the secrets** (replace placeholders with Task 0 values)

```sql
select vault.create_secret('<client_id>', 'reddit_client_id');
select vault.create_secret('<secret>',    'reddit_secret');
```

- [ ] **Step 2: Verify `getVault` (app_secret RPC) can read them**

The worker reads secrets via `select app_secret(p_name := 'reddit_client_id')`. Confirm it returns the value (some `app_secret` definitions filter by an allowlist):
```sql
select app_secret(p_name := 'reddit_client_id') is not null as ok_id,
       app_secret(p_name := 'reddit_secret')    is not null as ok_secret;
```
Expected: both `true`. If either is `false`/null, inspect the function and extend its allowlist:
```sql
select pg_get_functiondef(oid) from pg_proc where proname='app_secret';
```
If it has a hardcoded `name in (...)` allowlist, add `'reddit_client_id'` and `'reddit_secret'` to it via `apply_migration`, then re-run Step 2.

- [ ] **Step 3: No git commit** (secrets live only in Vault — never in the repo).

---

## Task 8: Refactor `reelSources` to use shared `deriveHostId` (DRY + dedupe alignment)

Guarantees Reddit and Highlightly produce identical `clip_id`s by sharing one function.

**Files:**
- Modify: `_handoff/supabase/functions/wc-goal-bot/index.ts` (top import + lines ~163-164)

- [ ] **Step 1: Add the import** at the top of `index.ts` (after the existing `createClient` import, line 5):
```ts
import { deriveHostId } from "./reddit.ts";
```

- [ ] **Step 2: Replace the inline id derivation** in `reelSources` (currently `index.ts:163-164`):

Find:
```ts
        const segs = u.split("?")[0].split("#")[0].split("/").filter(Boolean);
        const id = segs.reverse().find((s) => /^[A-Za-z0-9_-]{6,}$/.test(s) && !["watch", "embed", "video", "http:", "https:"].includes(s.toLowerCase()));
```
Replace with:
```ts
        const id = deriveHostId(u);
```

- [ ] **Step 3: Type-check the function bundle**

Run:
```bash
cd /Users/dschminkey/Repos/Soccer-Picks/_handoff/supabase/functions/wc-goal-bot
/Users/dschminkey/.deno/bin/deno check index.ts
```
Expected: no errors (downloads jsr deps on first run; that's fine).

- [ ] **Step 4: Commit**

```bash
cd /Users/dschminkey/Repos/Soccer-Picks
git add -f _handoff/supabase/functions/wc-goal-bot/index.ts
git commit -m "refactor(worker): reelSources uses shared deriveHostId"
```

---

## Task 9: Add `redditAuth` + `findMatchThread` + `scanThreadForClips` to index.ts

**Files:**
- Modify: `_handoff/supabase/functions/wc-goal-bot/index.ts` (add functions after `reelSources`, before the YouTube section / `Deno.serve`)

- [ ] **Step 1: Add the import for the parsers** — extend the Task 8 import line to:
```ts
import { deriveHostId, parseThreadFromSearch, parseClipsFromComments } from "./reddit.ts";
```

- [ ] **Step 2: Add the IO functions** (place immediately after the `reelSources` function, ~line 181):
```ts
// --- Reddit clip source (Phase 1): pull near-real-time goal clips from r/soccer match threads ---
// Reddit requires a unique, descriptive User-Agent or it 429/403s. Update the username if the app owner changes.
const RDT_UA = "soccer-picks/1.0 (by /u/Soccer_Picks_Bot)";
let redditTok: { token: string; exp: number } | null = null;

async function redditAuth(): Promise<string | null> {
  if (redditTok && redditTok.exp > Date.now() + 30000) return redditTok.token;
  const id = await getVault("reddit_client_id"), secret = await getVault("reddit_secret");
  if (!id || !secret) return null;
  try {
    const r = await fetch("https://www.reddit.com/api/v1/access_token", {
      method: "POST",
      headers: {
        "Authorization": "Basic " + btoa(`${id}:${secret}`),
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": RDT_UA,
      },
      body: "grant_type=client_credentials",
    });
    if (!r.ok) return null;
    const j = await r.json();
    if (!j?.access_token) return null;
    redditTok = { token: j.access_token, exp: Date.now() + (j.expires_in || 3600) * 1000 };
    return redditTok.token;
  } catch (_) { return null; }
}

// Find (and cache on the match row) the r/soccer match thread id for a live match.
async function findMatchThread(m: any): Promise<string | null> {
  if (m.reddit_thread_id) return m.reddit_thread_id;
  const tok = await redditAuth(); if (!tok) return null;
  try {
    const q = encodeURIComponent(`Match Thread ${m.home} ${m.away}`);
    const r = await fetch(
      `https://oauth.reddit.com/r/soccer/search?q=${q}&restrict_sr=1&sort=new&limit=15&t=day`,
      { headers: { "Authorization": `Bearer ${tok}`, "User-Agent": RDT_UA } });
    if (!r.ok) return null;
    const found = parseThreadFromSearch(await r.json(), m.home, m.away);
    if (found) {
      await sb.from("matches").update({ reddit_thread_id: found.id }).eq("match_id", m.match_id);
      return found.id;
    }
  } catch (_) {}
  return null;
}

// Scan the newest comments of a thread for known-host clip links.
async function scanThreadForClips(threadId: string): Promise<{ url: string; hostId: string; descr: string }[]> {
  const tok = await redditAuth(); if (!tok) return [];
  try {
    const r = await fetch(
      `https://oauth.reddit.com/comments/${threadId}?sort=new&limit=200&depth=1`,
      { headers: { "Authorization": `Bearer ${tok}`, "User-Agent": RDT_UA } });
    if (!r.ok) return [];
    return parseClipsFromComments(await r.json());
  } catch (_) { return []; }
}
```

- [ ] **Step 3: Type-check**

Run:
```bash
cd /Users/dschminkey/Repos/Soccer-Picks/_handoff/supabase/functions/wc-goal-bot
/Users/dschminkey/.deno/bin/deno check index.ts
```
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
cd /Users/dschminkey/Repos/Soccer-Picks
git add -f _handoff/supabase/functions/wc-goal-bot/index.ts
git commit -m "feat(reddit): worker auth + thread discovery + comment scan"
```

---

## Task 10: Add `redditSources` orchestrator + wire into the discovery loop

**Files:**
- Modify: `_handoff/supabase/functions/wc-goal-bot/index.ts` (add `redditSources` after `scanThreadForClips`; add call in the discovery loop ~lines 366-373; ensure `reddit_thread_id` is selected on match rows)

- [ ] **Step 1: Add the orchestrator** (immediately after `scanThreadForClips`):
```ts
// Upsert every clip found in the match thread into the same clips table reelSources feeds.
// Deduped by clip_id = hostId (shared with Highlightly), so the converter/relay handle it unchanged.
async function redditSources(m: any) {
  const threadId = await findMatchThread(m); if (!threadId) return;
  const clips = await scanThreadForClips(threadId);
  for (const c of clips) {
    await sb.from("clips").upsert(
      { clip_id: c.hostId, match_id: m.match_id, descr: c.descr, src_url: c.url },
      { onConflict: "clip_id", ignoreDuplicates: true });
  }
}
```

- [ ] **Step 2: Wire it into the discovery loop.** Find (`index.ts` ~366-373):
```ts
      for (const m of liveish) {
        const src = await reelSources(m.match_id, m.home, m.away, String(m.kickoff).slice(0, 10));
        for (const c of src.streamff) {
          await sb.from("clips").upsert({ clip_id: c.id, match_id: m.match_id, descr: c.label, src_url: c.url }, { onConflict: "clip_id", ignoreDuplicates: true });
        }
      }
```
Replace with (adds the Reddit call; Reddit runs even when `HL_KEY` is unset, but this block is already gated by `HL_KEY` — see Step 3):
```ts
      for (const m of liveish) {
        const src = await reelSources(m.match_id, m.home, m.away, String(m.kickoff).slice(0, 10));
        for (const c of src.streamff) {
          await sb.from("clips").upsert({ clip_id: c.id, match_id: m.match_id, descr: c.label, src_url: c.url }, { onConflict: "clip_id", ignoreDuplicates: true });
        }
        await redditSources(m); // also pull clips straight from the r/soccer match thread
      }
```

- [ ] **Step 3: Make the discovery block run independent of `HL_KEY`.** The loop is currently inside `if (!firstRun && HL_KEY) {`. Reddit must run even if Highlightly is later cancelled. Find:
```ts
    if (!firstRun && HL_KEY) {
      const liveish = matchRows.filter((m) => (m.state === "in" || m.state === "post") && (Date.now() - new Date(m.kickoff).getTime()) <= 4 * 3600 * 1000);
```
Replace with:
```ts
    if (!firstRun) {
      const liveish = matchRows.filter((m) => (m.state === "in" || m.state === "post") && (Date.now() - new Date(m.kickoff).getTime()) <= 4 * 3600 * 1000);
```
(`reelSources` already returns empty when `HL_KEY` is falsy, so this is safe.)

- [ ] **Step 4: Ensure `reddit_thread_id` is loaded on match rows.** Locate where `matchRows` is selected (search for `.from("matches").select(`). If it uses `select("*")`, no change is needed. If it lists explicit columns, add `reddit_thread_id` to the list. Verify with:
```bash
cd /Users/dschminkey/Repos/Soccer-Picks/_handoff/supabase/functions/wc-goal-bot
grep -n '.from("matches").select(' index.ts
```
If the matched select is column-explicit and lacks `reddit_thread_id`, add it. If `select("*")`, leave as-is.

- [ ] **Step 5: Type-check**

Run:
```bash
cd /Users/dschminkey/Repos/Soccer-Picks/_handoff/supabase/functions/wc-goal-bot
/Users/dschminkey/.deno/bin/deno check index.ts
```
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
cd /Users/dschminkey/Repos/Soccer-Picks
git add -f _handoff/supabase/functions/wc-goal-bot/index.ts
git commit -m "feat(reddit): redditSources orchestrator wired into discovery loop"
```

---

## Task 11: Deploy and live-verify in test mode

Confirms the worker discovers Reddit clips end-to-end without spamming subscribers.

**Files:** none (deploy + DB checks).

- [ ] **Step 1: Confirm test mode is ON (operator-only)** via MCP `execute_sql`:
```sql
select decrypted_secret from vault.decrypted_secrets where name='test_mode';
```
If not `'1'`, set it: `select vault.update_secret(id, '1') from vault.secrets where name='test_mode';`
(Capture the prior value to restore later.)

- [ ] **Step 2: Deploy the worker**

Run:
```bash
cd /Users/dschminkey/Repos/Soccer-Picks/_handoff
supabase functions deploy wc-goal-bot --project-ref ckldrmyzmwnujzpxxjpt --no-verify-jwt
```
Expected: `Deployed Functions on project ckldrmyzmwnujzpxxjpt: wc-goal-bot`.

- [ ] **Step 3: Force a tick during or shortly after a live WC match**

Run (cron secret is in Vault `wc_cron_secret`):
```bash
curl -s -X POST "https://ckldrmyzmwnujzpxxjpt.supabase.co/functions/v1/wc-goal-bot" \
  -H "x-cron-secret: <wc_cron_secret>"
```
Expected: HTTP 200 JSON with `"testMode":true`.

- [ ] **Step 4: Verify a thread id was cached and Reddit clips were discovered**

Via MCP `execute_sql`:
```sql
select match_id, home, away, reddit_thread_id from worldcup.matches
  where state='in' or finished_at > now() - interval '4 hours';
select clip_id, match_id, left(descr,40) descr, src_url, our_url is null as pending, detected_at
  from worldcup.clips where detected_at > now() - interval '20 min' order by detected_at desc;
```
Expected: live match has a non-null `reddit_thread_id`; if the thread had clip links, new `clips` rows appear (clip_id = host id). With `test_mode='1'`, any resulting send goes to the operator only.

- [ ] **Step 5: Measure latency vs Highlightly (success criterion)**

After a match where both sources ran, compare first-seen times. Reddit-sourced clips should appear at or before Highlightly's for the same goal:
```sql
select clip_id, match_id, descr, detected_at from worldcup.clips
  where match_id = '<match_id>' order by detected_at;
```
Record findings for the user.

- [ ] **Step 6: Restore test mode if it was changed**, and report results. (Flipping `test_mode` to `'0'` for real subscribers is the user's call — do not do it without explicit approval.)

---

## Self-Review Notes (completed by plan author)

- **Spec coverage:** all spec components mapped — `redditAuth` (T9), `findMatchThread` (T9), `scanThreadForClips` (T9), `extractClipLinks` (T2), `redditSources` (T10); parallel+dedupe via shared `deriveHostId` (T1/T8) and `clip_id=hostId` (T10); Vault secrets (T7); `matches.reddit_thread_id` (T6); fail-safe error handling (try/catch + empty returns, T9); HL-independence (T10 Step 3); assumption gate (T5); success-criterion measurement (T11 Step 5).
- **Placeholder scan:** none — every code/SQL/command step is concrete. Bracketed `<...>` tokens are runtime secrets/ids intentionally supplied at execution.
- **Type consistency:** `deriveHostId`, `extractClipLinks`, `parseThreadFromSearch` (`{id,title}`), `parseClipsFromComments` (`{url,hostId,descr}`) used identically across tasks; `clip_id=hostId` matches `reelSources`' `clip_id=c.id` (both bare host ids).
