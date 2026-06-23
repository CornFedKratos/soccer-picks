// wc-goal-bot: detect World Cup events from ESPN, post to Telegram, backfill per-goal clips,
// pregame odds, card alerts, and a full-time stitched highlight reel.
// Hardening: TEST MODE routes every send to the operator only; clips/reels are only marked
// delivered after a confirmed ok send (otherwise they retry).
import { createClient } from "jsr:@supabase/supabase-js@2";
import { deriveHostId, parseGoalPostsFromFeed, teamMatchesTitle } from "./reddit.ts";

const SB_URL = Deno.env.get("SUPABASE_URL")!;
const SB_SERVICE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const sb = createClient(SB_URL, SB_SERVICE, { db: { schema: "worldcup" }, auth: { persistSession: false } });
async function getVault(name: string) { try { const { data } = await sb.rpc("app_secret", { p_name: name }); return (data as string) || ""; } catch (_) { return ""; } }

const BOT  = Deno.env.get("TELEGRAM_BOT_TOKEN") || await getVault("tg_bot_token");
const CRON = Deno.env.get("CRON_SECRET")        || await getVault("wc_cron_secret");
const HL_KEY  = Deno.env.get("HIGHLIGHTLY_KEY")  || await getVault("highlightly_key");
const TG_CHAT = Deno.env.get("TELEGRAM_CHAT_ID") ?? "";
const REEL_FN = "https://soccer-picks.netlify.app/.netlify/functions/match-reel-background";
const REEL_DELAY_MIN = 10;
const RESI_PROXY = Deno.env.get("RESI_PROXY_URL") || await getVault("resi_proxy_url");

const ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard";
const SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/summary?event=";
const CORE_ODDS = (id: string) => `https://sports.core.api.espn.com/v2/sports/soccer/leagues/fifa.world/events/${id}/competitions/${id}/odds`;
const SCOREBAT = "https://www.scorebat.com/video-api/v3/";
const HL_BASE = "https://sports.highlightly.net";
const CLIP_WINDOW_MIN = 45;
const HL_MAX_CHECKS = 12;
const TZ = "America/Chicago";
const SUMMARY_DELAY_MIN = 2;
const norm = (s: string) => (s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]/g, "");

// Country flags for post-game summaries (keyed by ESPN displayName; aliases normalize variants).
const FLAGS: Record<string, string> = {"Mexico":"🇲🇽","South Korea":"🇰🇷","Czechia":"🇨🇿","South Africa":"🇿🇦","Switzerland":"🇨🇭","Canada":"🇨🇦","Qatar":"🇶🇦","Bosnia and Herzegovina":"🇧🇦","Brazil":"🇧🇷","Morocco":"🇲🇦","Haiti":"🇭🇹","USA":"🇺🇸","Australia":"🇦🇺","Turkiye":"🇹🇷","Paraguay":"🇵🇾","Germany":"🇩🇪","Ivory Coast":"🇨🇮","Ecuador":"🇪🇨","Curacao":"🇨🇼","Japan":"🇯🇵","Netherlands":"🇳🇱","Sweden":"🇸🇪","Tunisia":"🇹🇳","Belgium":"🇧🇪","Egypt":"🇪🇬","Iran":"🇮🇷","New Zealand":"🇳🇿","Cape Verde":"🇨🇻","Saudi Arabia":"🇸🇦","Spain":"🇪🇸","Uruguay":"🇺🇾","France":"🇫🇷","Iraq":"🇮🇶","Norway":"🇳🇴","Senegal":"🇸🇳","Algeria":"🇩🇿","Argentina":"🇦🇷","Austria":"🇦🇹","Jordan":"🇯🇴","Colombia":"🇨🇴","DR Congo":"🇨🇩","Portugal":"🇵🇹","Uzbekistan":"🇺🇿","Croatia":"🇭🇷","Ghana":"🇬🇭","Panama":"🇵🇦","Scotland":"🏴󠁧󠁢󠁳󠁣󠁴󠁿","England":"🏴󠁧󠁢󠁥󠁮󠁧󠁿"};
const FLAG_ALIAS: Record<string, string> = {"Turkey":"Turkiye","Türkiye":"Turkiye","Curaçao":"Curacao","United States":"USA","Korea Republic":"South Korea","Bosnia-Herzegovina":"Bosnia and Herzegovina","Congo DR":"DR Congo"};
const flagFor = (t: string) => FLAGS[FLAG_ALIAS[t] || t] || "🏳️";
const minOrd = (s: string) => { const m = String(s || "").match(/(\d+)(?:\D+(\d+))?/); if (!m) return 9999; return parseInt(m[1], 10) + (m[2] ? parseInt(m[2], 10) / 100 : 0); };
const ml2p = (m: number) => { m = Number(m); return m < 0 ? (-m) / (-m + 100) : 100 / (m + 100); };

async function tg(method: string, body: unknown) {
  if (!BOT) return null;
  try {
    const r = await fetch(`https://api.telegram.org/bot${BOT}/${method}`, {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body),
    });
    return await r.json();
  } catch (_) { return null; }
}
function goalText(g: any) {
  const og = g.og ? " (OG)" : "";
  const assist = g.assist ? `\n🅰 Assist: ${g.assist}` : "";
  return `⚽ ${g.home} ${g.score} ${g.away}\n${g.scorer || "Goal"}${og} ${g.minute}${assist}\nFIFA World Cup\nMatch: https://www.espn.com/soccer/match/_/gameId/${g.match_id}`;
}
function geText(ge: any) {
  return `⚽ ${ge.home} ${ge.score} ${ge.away}\n${ge.scorer || "Goal"} ${ge.minute}\nFIFA World Cup`;
}

const summaryCache = new Map<string, any>();
async function assistFor(match_id: string, scorer: string) {
  try {
    if (!summaryCache.has(match_id)) { const r = await fetch(SUMMARY + match_id); summaryCache.set(match_id, await r.json()); }
    const ke = summaryCache.get(match_id)?.keyEvents || [];
    const sn = norm(scorer);
    for (const p of ke) {
      const isGoal = p.scoringPlay || /goal/i.test((p.type?.text) || "");
      if (!isGoal) continue;
      const txt = String(p.text || "");
      if (sn && norm(txt).includes(sn)) { const m = txt.match(/Assisted by ([^.]+)\./i); if (m) return m[1].trim(); }
    }
  } catch (_) {}
  return null;
}

async function scorebatClip(home: string, away: string) {
  try {
    const r = await fetch(SCOREBAT); const d = await r.json();
    const list = (d?.response || d || []) as any[];
    const h = norm(home), a = norm(away);
    const hit = list.find((it) => {
      const hn = norm(typeof it.homeTeam === "object" ? it.homeTeam?.name : it.homeTeam);
      const an = norm(typeof it.awayTeam === "object" ? it.awayTeam?.name : it.awayTeam);
      const t = norm(it.title);
      const has = (x: string) => x && (hn.includes(x) || an.includes(x) || t.includes(x));
      return has(h) && has(a);
    });
    if (hit) return hit.matchviewUrl || null;
  } catch (_) {}
  return null;
}
const hlMatchCache = new Map<string, string | null>();
async function hlMatchId(match_id: string, home: string, away: string, ymd?: string) {
  let mid = hlMatchCache.get(match_id);
  if (mid !== undefined) return mid;
  const headers = { "x-rapidapi-key": HL_KEY };
  const base = ymd || new Date().toISOString().slice(0, 10);
  const d0 = new Date(base + "T12:00:00Z").getTime();
  const dates = [0, -1, 1].map((o) => new Date(d0 + o * 864e5).toISOString().slice(0, 10));
  const h = norm(home), a = norm(away);
  mid = null;
  for (const d of dates) {
    try {
      const mr = await fetch(`${HL_BASE}/football/matches?date=${d}&leagueName=World%20Cup&limit=100`, { headers });
      const md = await mr.json(); const arr = (md?.data || md || []) as any[];
      const m = arr.find((x) => { const xh = norm(x.homeTeam?.name || x.homeTeam), xa = norm(x.awayTeam?.name || x.awayTeam); return (xh.includes(h) || h.includes(xh)) && (xa.includes(a) || a.includes(xa)); });
      if (m?.id != null) { mid = String(m.id); break; }
    } catch (_) {}
  }
  hlMatchCache.set(match_id, mid);
  return mid;
}
async function hlHighlights(mid: string) {
  const headers = { "x-rapidapi-key": HL_KEY };
  const hr = await fetch(`${HL_BASE}/football/highlights?matchId=${mid}&limit=40`, { headers });
  const hd = await hr.json(); return (hd?.data || hd || []) as any[];
}
function clipMp4(url: string) { const m = String(url || "").match(/\/v\/([a-z0-9]+)/i); return m ? `https://cdn.streamff.one/${m[1]}.mp4` : null; }
async function highlightlyClip(match_id: string, home: string, away: string, scorer: string, minute: string, ymd?: string) {
  if (!HL_KEY) return null;
  try {
    const mid = await hlMatchId(match_id, home, away, ymd); if (!mid) return null;
    const hl = await hlHighlights(mid); if (!hl.length) return null;
    const goalMin = parseInt(String(minute || "").match(/\d+/)?.[0] ?? "", 10);
    const parts = String(scorer || "").trim().split(/\s+/);
    const sur = norm(parts[parts.length - 1] || "");
    let best: any = null, bestScore = 0;
    for (const c of hl) {
      const desc = String(c.description || c.title || "");
      const dn = norm(desc);
      // skip non-goal moments (penalty miss, save, foul, card, offside, VAR, disallowed)
      if (/(penaltymiss|missedpenalty|missed|saved|save|foul|booking|yellowcard|redcard|sentoff|offside|disallowed|ruledout|\bvar\b)/.test(dn)) continue;
      const hMin = parseInt(desc.match(/\d+/)?.[0] ?? "", 10);
      const minOk = !isNaN(goalMin) && !isNaN(hMin) && Math.abs(goalMin - hMin) <= 2;
      let s = 0;
      if (minOk) s += 3;                                            // the goal minute must line up
      if (sur && sur.length >= 3 && dn.includes(sur)) s += 2;       // scorer surname present
      if (/(goal|scores|score)/.test(dn)) s += 2;                   // explicitly a goal
      if (s > bestScore) { bestScore = s; best = c; }
    }
    // require two strong signals (e.g. minute + scorer) so a same-name non-goal can't win
    if (best && bestScore >= 4) return best.url || best.embedUrl || best.source || null;
  } catch (_) {}
  return null;
}
// US-available YouTube channels we allow, in preference order (Don: ESPN/FIFA/CBS/FOX/NBC/Telemundo).
const YT_PREF = ["ESPN FC", "ESPN", "FIFA", "CBS Sports Golazo", "CBS Sports", "FOX Soccer", "NBC Sports", "Telemundo", "beIN SPORTS USA"];
// Hard block: geo-locked / non-US channels that won't play for our audience. Never selected even if seen.
const YT_BLOCK = ["dazn", "itv", "arena sport", "t sports", "sky sport", "sportdigital", "viaplay", "supersport", "bein sports xtra", "tnt sports", "optus"];

// Returns both reel sources for a match: streamff mp4 clips (to stitch) and the best US-available
// YouTube highlight (to embed). Single Highlightly lookup serves both.
async function reelSources(match_id: string, home: string, away: string, ymd?: string) {
  const empty = { streamff: [] as any[], youtube: null as string | null };
  if (!HL_KEY) return empty;
  try {
    const mid = await hlMatchId(match_id, home, away, ymd); if (!mid) return empty;
    const hl = await hlHighlights(mid);
    const seen = new Set<string>(); const streamff: any[] = [];
    let youtube: string | null = null, bestRank = 999;
    for (const c of hl) {
      // Capture EVERY non-YouTube highlight, whatever the host (streamin.link/v/<id>, streamain.com/<tok>/watch,
      // streamff, future rebrands). Keep the page URL — the Netlify resolver derives the real mp4 dynamically;
      // hosts it can't download (e.g. bot-protected) still go out as the ad-supported link via the relay fallback.
      const u = String(c.url || "");
      const isYt = String(c.source || "").toLowerCase() === "youtube" || /youtu\.?be|youtube\.com/i.test(u);
      if (u && !isYt) {
        const id = deriveHostId(u);
        if (id && !seen.has(id)) {
          seen.add(id);
          const min = parseInt(String(c.description || "").match(/\d+/)?.[0] ?? "", 10);
          streamff.push({ url: u, id, min: isNaN(min) ? 9999 : min, label: String(c.description || "") });
        }
      }
      if (String(c.source || "").toLowerCase() === "youtube") {
        const ch = String(c.channel || "").toLowerCase();
        if (YT_BLOCK.some((b) => ch.includes(b))) continue;                 // never use geo-locked channels (ITV/DAZN/etc.)
        const rank = YT_PREF.findIndex((p) => ch.includes(p.toLowerCase()));
        if (rank >= 0 && rank < bestRank) { bestRank = rank; youtube = c.embedUrl || c.url; }
      }
    }
    streamff.sort((a, b) => a.min - b.min);
    return { streamff, youtube };
  } catch (_) { return empty; }
}

// Pull goal-clip posts from r/soccer's public submissions RSS (no OAuth) via the residential
// proxy — datacenter IPs get 403/429 hitting Reddit directly. Fail-safe: returns [] on ANY error
// (incl. runtimes without Deno.createHttpClient), so a Reddit/proxy problem never breaks the tick.
async function redditClipPosts(): Promise<{ title: string; url: string; hostId: string }[]> {
  if (!RESI_PROXY) { console.log("[reddit] no RESI_PROXY"); return []; }
  try {
    const client = (Deno as any).createHttpClient({ proxy: { url: RESI_PROXY } });
    const r = await fetch("https://www.reddit.com/r/soccer/new/.rss?limit=50",
      { client, headers: { "user-agent": "soccer-picks/1.0 (clip discovery)" } } as any);
    const posts = r.ok ? parseGoalPostsFromFeed(await r.text()) : [];
    console.log("[reddit] rss status", r.status, "clip-posts", posts.length);
    return posts;
  } catch (e) { console.log("[reddit] ERR", String(e).slice(0, 160)); return []; }
}

// Kick off ffmpeg compression of one streamff clip via the Netlify function -> reels/clips/<m>_<clipId>.mp4.
// The function marks the clip done (wc_clipq_done sets our_url) and keeps it under Telegram's 20MB URL limit.
async function triggerClipCompress(matchId: string, clipId: string, srcUrl: string) {
  const path = `clips/${matchId}_${clipId}.mp4`;
  let token: any = null;
  try { const s = await sb.storage.from("reels").createSignedUploadUrl(path, { upsert: true }); token = (s as any)?.data?.token; } catch (_) {}
  if (!token) return;
  const secret = await getVault("reel_trigger_secret");
  try {
    await fetch(REEL_FN, { method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ secret, clipId, outName: path, uploadToken: token, clips: [{ url: srcUrl }] }) });
  } catch (_) {}
}

// Caption for a relayed highlight clip: Highlightly's own context + our narration. If the clip matches a
// detected goal (scorer surname in the description, and it's not a miss/save), label it a Goal and add the assist.
async function clipCaption(cl: any, matchRows: any[]) {
  const m = matchRows.find((x) => x.match_id === cl.match_id);
  const head = m ? `${m.home} ${m.home_score}-${m.away_score} ${m.away}` : "FIFA World Cup";
  const dn = norm(cl.descr || "");
  let goalRow: any = null;
  if (!/(miss|saved|save)/.test(dn)) {
    const gz = await sb.from("goal_events").select("scorer,minute").eq("match_id", cl.match_id);
    for (const g of (gz.data || [])) {
      const parts = String(g.scorer || "").trim().split(/\s+/);
      const sur = norm(parts[parts.length - 1] || "");
      if (sur && sur.length >= 3 && dn.includes(sur)) { goalRow = g; break; }
    }
  }
  if (goalRow) {
    const assist = await assistFor(cl.match_id, goalRow.scorer);
    return `⚽ ${head}\nGoal — ${goalRow.scorer} ${goalRow.minute}` + (assist ? `\n🅰 Assist: ${assist}` : "") + `\nFIFA World Cup`;
  }
  const label = (cl.descr || "").trim() || "Highlight";
  return `🎬 ${head}\n${label}\nFIFA World Cup`;
}

// Pull per-player stats for one match from ESPN's rosters boxscore (authoritative, fresher than the
// aggregate leaders endpoint). Returns one row per player with the categories the board shows.
async function fetchMatchPlayerStats(matchId: string) {
  try {
    const r = await fetch(SUMMARY + matchId); const d = await r.json();
    const out: any[] = [];
    for (const t of (d.rosters || [])) {
      const tm = t.team?.displayName || ""; const ab = t.team?.abbreviation || "";
      for (const p of (t.roster || [])) {
        const ath = p.athlete || {}; const id = String(ath.id || ""); if (!id) continue;
        const sx: Record<string, number> = {};
        for (const s of (p.stats || [])) sx[s.name] = Number(s.value) || 0;
        out.push({ id, n: ath.displayName || ath.shortName || ("#" + id), pos: p.position?.abbreviation || "", tm, ab,
          g: sx.totalGoals || 0, a: sx.goalAssists || 0, sot: sx.shotsOnTarget || 0, sh: sx.totalShots || 0, sv: sx.saves || 0,
          fc: sx.foulsCommitted || 0, fs: sx.foulsSuffered || 0, y: sx.yellowCards || 0, r: sx.redCards || 0 });
      }
    }
    return out.length ? out : null;
  } catch (_) { return null; }
}

Deno.serve(async (req) => {
  if (CRON && req.headers.get("x-cron-secret") !== CRON) return new Response("unauthorized", { status: 401 });
  const out: any = { matches: 0, newGoals: 0, alerted: 0, clipsFound: 0, cards: 0, pregame: 0, summaries: 0, brief: false, reelsQueued: 0, reelsSent: 0, embeds: 0, embedsSent: 0, statsPlayers: 0, subs: 0, testMode: false, firstRun: false };
  try {
    const res = await fetch(ESPN); const data = await res.json();
    const events = data?.events || [];
    const head = await sb.from("goal_events").select("id", { count: "exact", head: true });
    const firstRun = (head.count ?? 0) === 0;
    const cardHead = await sb.from("card_events").select("id", { count: "exact", head: true });
    const cardFirstRun = (cardHead.count ?? 0) === 0;
    out.firstRun = firstRun;
    const subRes = await sb.from("tg_subscribers").select("chat_id").eq("active", true);
    const subs = (subRes.data || []).map((r: any) => r.chat_id);
    out.subs = subs.length;

    // TEST MODE: route every Telegram send to the operator only
    const TEST_MODE = (await getVault("test_mode")) === "1";
    const TEST_CHAT = TEST_MODE ? await getVault("tg_test_chat") : "";
    const sendSubs = TEST_MODE ? (TEST_CHAT ? [TEST_CHAT] : []) : subs;
    const groupChat = TEST_MODE ? "" : TG_CHAT;
    out.testMode = TEST_MODE;
    const sendText = async (text: string, preview: boolean) => {
      let ok = (sendSubs.length === 0 && !groupChat);
      if (groupChat) { const r = await tg("sendMessage", { chat_id: groupChat, text, disable_web_page_preview: !preview }); if (r && r.ok) ok = true; }
      for (const cid of sendSubs) { const r = await tg("sendMessage", { chat_id: cid, text, disable_web_page_preview: !preview }); if (r && r.ok) ok = true; }
      return ok;
    };
    const sendVid = async (url: string, caption: string) => {
      let ok = (sendSubs.length === 0 && !groupChat);
      if (groupChat) { const r = await tg("sendVideo", { chat_id: groupChat, video: url, caption }); if (r && r.ok) ok = true; }
      for (const cid of sendSubs) { const r = await tg("sendVideo", { chat_id: cid, video: url, caption }); if (r && r.ok) ok = true; }
      return ok;
    };

    const matchRows: any[] = [];
    const detected: any[] = [];
    const detectedCards: any[] = [];
    for (const e of events) {
      const c = e.competitions?.[0]; if (!c) continue;
      const cs = c.competitors || [];
      const home = cs[0]?.team?.displayName ?? ""; const away = cs[1]?.team?.displayName ?? "";
      const hsc = Number(cs[0]?.score ?? 0); const asc = Number(cs[1]?.score ?? 0);
      const state = e.status?.type?.state ?? "";
      matchRows.push({ match_id: e.id, home, away, kickoff: e.date, state, home_score: hsc, away_score: asc, updated_at: new Date().toISOString() });
      if (state !== "in" && state !== "post") continue;
      const homeId = cs[0]?.team?.id;
      let rh = 0, ra = 0;
      for (const p of (c.details || [])) {
        const clock = p.clock?.displayValue ?? "";
        const who = p.athletesInvolved?.[0]?.displayName ?? "";
        const side = String(p.team?.id) === String(homeId) ? "h" : "a";
        if (p.scoringPlay) {
          if (side === "h") rh++; else ra++;
          const ev_key = `${e.id}:${clock}:${norm(who)}:${side}`;
          detected.push({ match_id: e.id, ev_key, home, away, minute: clock, scorer: who, og: !!p.ownGoal, score: `${rh}-${ra}`, state, kickoff: e.date });
        } else if (p.yellowCard || p.redCard) {
          const kind = p.redCard ? "red" : "yellow";
          const ev_key = `${e.id}:card:${clock}:${norm(who)}:${kind}`;
          detectedCards.push({ match_id: e.id, ev_key, kind, player: who, side, minute: clock, home, away, state, kickoff: e.date });
        }
      }
    }
    if (matchRows.length) {
      await sb.from("matches").upsert(matchRows, { onConflict: "match_id" }); out.matches = matchRows.length;
      await sb.from("matches").update({ finished_at: new Date().toISOString() }).eq("state", "post").is("finished_at", null);
    }

    for (const g of detected) {
      const ins = await sb.from("goal_events").upsert({
        match_id: g.match_id, ev_key: g.ev_key, home: g.home, away: g.away,
        minute: g.minute, scorer: g.scorer, score: g.score, alerted: firstRun ? true : false,
      }, { onConflict: "ev_key", ignoreDuplicates: true }).select("id").maybeSingle();
      if (ins.error || !ins.data) continue;
      out.newGoals++;
      const recent = (Date.now() - new Date(g.kickoff).getTime()) < 3 * 3600 * 1000;
      const shouldAlert = !firstRun && (g.state === "in" || (g.state === "post" && recent));
      if (shouldAlert) {
        g.assist = await assistFor(g.match_id, g.scorer);
        await sendText(goalText(g), false);
        await sb.from("goal_events").update({ alerted: true }).eq("id", ins.data.id);
        out.alerted++;
      }
    }

    for (const cv of detectedCards) {
      const ins = await sb.from("card_events").upsert({
        match_id: cv.match_id, ev_key: cv.ev_key, kind: cv.kind, player: cv.player, team_side: cv.side,
        minute: cv.minute, home: cv.home, away: cv.away, alerted: cardFirstRun ? true : false,
      }, { onConflict: "ev_key", ignoreDuplicates: true }).select("id").maybeSingle();
      if (ins.error || !ins.data) continue;
      const recent = (Date.now() - new Date(cv.kickoff).getTime()) < 3 * 3600 * 1000;
      if (cardFirstRun || !(cv.state === "in" || (cv.state === "post" && recent))) continue;
      const team = cv.side === "h" ? cv.home : cv.away;
      const icon = cv.kind === "red" ? "🟥" : "🟨";
      const label = cv.kind === "red" ? "Red card" : "Yellow card";
      await sendText(`${icon} ${label} — ${cv.player || "Player"} (${team}) ${cv.minute}\n${cv.home} v ${cv.away}`, false);
      await sb.from("card_events").update({ alerted: true }).eq("id", ins.data.id);
      out.cards++;
    }

    for (const m of matchRows) {
      if (m.state !== "pre") continue;
      const ms = new Date(m.kickoff).getTime() - Date.now();
      if (ms <= 0 || ms > 5 * 60 * 1000) continue;
      const ex = await sb.from("pregame_alerts").select("match_id").eq("match_id", m.match_id).maybeSingle();
      if (ex.data) continue;
      let oddsLine = "";
      try {
        const or = await fetch(CORE_ODDS(m.match_id)); const od = await or.json();
        const it = (od.items || [])[0] || {};
        const hm = it.homeTeamOdds?.moneyLine, am = it.awayTeamOdds?.moneyLine, dm = it.drawOdds?.moneyLine;
        if (hm != null && am != null) {
          const ph = ml2p(hm), pa = ml2p(am), pd = dm != null ? ml2p(dm) : 0; const s = ph + pa + pd || 1;
          const favHome = ph >= pa; const favName = favHome ? m.home : m.away; const favPct = Math.round((favHome ? ph : pa) / s * 100);
          oddsLine = `\nLatest odds: ${favName} predicted to win at ${favPct}%`;
        }
      } catch (_) {}
      const t = new Intl.DateTimeFormat("en-US", { timeZone: TZ, hour: "numeric", minute: "2-digit" }).format(new Date(m.kickoff));
      const okp = await sendText(`⏰ ${m.away} vs ${m.home}\nStarting ${t} CT${oddsLine}`, false);
      if (okp) { await sb.from("pregame_alerts").insert({ match_id: m.match_id }); out.pregame++; }
    }

    // highlight clips RELAY: send EVERY Highlightly clip (goals, misses, saves, cards) with its own
    // context sentence + our narration (goal label + assist when it matches a detected goal).
    // 1) discover clips for live / recently-finished matches and queue them (deduped by streamff id)
    if (!firstRun) {
      const liveish = matchRows.filter((m) => (m.state === "in" || m.state === "post") && (Date.now() - new Date(m.kickoff).getTime()) <= 4 * 3600 * 1000);
      const redditPosts = liveish.length ? await redditClipPosts() : [];
      (out as any).redditPosts = redditPosts.length;
      for (const m of liveish) {
        const src = await reelSources(m.match_id, m.home, m.away, String(m.kickoff).slice(0, 10));
        for (const c of src.streamff) {
          await sb.from("clips").upsert({ clip_id: c.id, match_id: m.match_id, descr: c.label, src_url: c.url }, { onConflict: "clip_id", ignoreDuplicates: true });
        }
        // Reddit goal-clip posts (RSS) that name BOTH of this match's teams
        for (const p of redditPosts) {
          if (teamMatchesTitle(p.title, m.home, m.away)) {
            await sb.from("clips").upsert({ clip_id: p.hostId, match_id: m.match_id, descr: p.title, src_url: p.url }, { onConflict: "clip_id", ignoreDuplicates: true });
          }
        }
      }
    }
    // 2) compress + deliver queued clips with confirmation; retry until sent
    const ccut = new Date(Date.now() - CLIP_WINDOW_MIN * 60 * 1000).toISOString();
    const cpend = await sb.from("clips")
      .select("clip_id,match_id,descr,src_url,our_url,sent,checks")
      .or("our_url.is.null,sent.eq.false").gte("detected_at", ccut).limit(20);
    const CLIP_COMPRESS_TRIES = 4; // try for the ad-free compressed clip this many ticks, then fall back to the link
    for (const cl of (cpend.data || [])) {
      // already delivered (video OR link fallback) — never re-send. The select still returns sent clips
      // whose our_url is null (link fallback), so without this guard the fallback re-fired every tick.
      if (cl.sent) continue;
      if (cl.our_url) {
        // preferred: our ad-free, inline-playable compressed clip
        if (!cl.sent) { const cap = await clipCaption(cl, matchRows); if (await sendVid(cl.our_url, cap)) { await sb.from("clips").update({ sent: true }).eq("clip_id", cl.clip_id); out.clipsFound++; } }
        continue;
      }
      const checks = cl.checks ?? 0;
      if (checks < CLIP_COMPRESS_TRIES) {
        await triggerClipCompress(cl.match_id, cl.clip_id, cl.src_url);
        await sb.from("clips").update({ checks: checks + 1 }).eq("clip_id", cl.clip_id);
      } else {
        // can't get a downloadable clip — ALWAYS send the highlight: fall back to the (ad-supported) page link
        const cap = await clipCaption(cl, matchRows);
        if (await sendText(`${cap}\n${cl.src_url}`, true)) { await sb.from("clips").update({ sent: true }).eq("clip_id", cl.clip_id); out.clipsFound++; }
      }
    }

    // post-game summary: winner, score, scorers sorted by minute with country flags — fires once per match
    if (!firstRun) {
      const fin = await sb.from("matches")
        .select("match_id,home,away,home_score,away_score,finished_at")
        .eq("state", "post").eq("summary_sent", false).not("finished_at", "is", null)
        .lte("finished_at", new Date(Date.now() - SUMMARY_DELAY_MIN * 60 * 1000).toISOString())
        .limit(8);
      for (const m of (fin.data || [])) {
        const gz = await sb.from("goal_events").select("ev_key,minute,scorer").eq("match_id", m.match_id);
        const goals = (gz.data || []).map((g: any) => {
          const side = String(g.ev_key).split(":").pop();
          const team = side === "h" ? m.home : m.away;
          return { minute: g.minute, scorer: g.scorer, flag: flagFor(team), ord: minOrd(g.minute) };
        }).sort((a: any, b: any) => a.ord - b.ord);
        const hs = m.home_score ?? 0, as = m.away_score ?? 0;
        const verdict = hs === as ? "Draw" : `${(hs > as ? m.home : m.away)} win`;
        const lines = goals.map((g: any) => `${g.minute} ${g.flag} ${g.scorer || "Goal"}`).join("\n");
        const text = `🏁 Full-time\n${flagFor(m.home)} ${m.home} ${hs}-${as} ${m.away} ${flagFor(m.away)}\n${verdict}` +
          (lines ? `\n\nScorers:\n${lines}` : "") + `\nFIFA World Cup`;
        if (await sendText(text, false)) { await sb.from("matches").update({ summary_sent: true }).eq("match_id", m.match_id); out.summaries++; }
      }
    }

    // Match Day brief: once per day at/after 8am CT, list the day's fixtures with flags, names, time, odds.
    // brief_force vault secret ('YYYYMMDD') previews a given day to the test chat without writing the daily guard.
    try {
      const force = await getVault("brief_force");
      const ctParts = new Intl.DateTimeFormat("en-US", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(new Date());
      const cp = (t: string) => ctParts.find((p) => p.type === t)?.value || "";
      const ctDate = `${cp("year")}-${cp("month")}-${cp("day")}`;
      const ctHour = Number(new Intl.DateTimeFormat("en-US", { timeZone: TZ, hour: "2-digit", hour12: false }).format(new Date()));
      const briefYmd = force ? `${force.slice(0, 4)}-${force.slice(4, 6)}-${force.slice(6, 8)}` : ctDate;
      let due = !!force;
      if (!force && ctHour >= 8 && ctHour < 12) {
        const ex = await sb.from("matchday_briefs").select("brief_date").eq("brief_date", briefYmd).maybeSingle();
        if (!ex.data) due = true;
      }
      if (due) {
        const br = await fetch(`${ESPN}?dates=${briefYmd.replace(/-/g, "")}`); const bd = await br.json();
        const evs = (bd?.events || []) as any[];
        if (evs.length) {
          const dateLabel = new Intl.DateTimeFormat("en-US", { timeZone: TZ, weekday: "long", month: "long", day: "numeric" }).format(new Date(briefYmd + "T18:00:00Z"));
          const blocks: string[] = [];
          for (const e of evs) {
            const c = e.competitions?.[0]; const cs = (c?.competitors || []) as any[];
            const homeC = cs.find((x) => x.homeAway === "home") || cs[0];
            const awayC = cs.find((x) => x.homeAway === "away") || cs[1];
            const home = homeC?.team?.displayName ?? ""; const away = awayC?.team?.displayName ?? "";
            const t = new Intl.DateTimeFormat("en-US", { timeZone: TZ, hour: "numeric", minute: "2-digit" }).format(new Date(e.date));
            let oddsLine = "";
            try {
              const or = await fetch(CORE_ODDS(e.id)); const od = await or.json();
              const it = (od.items || [])[0] || {};
              const hm = it.homeTeamOdds?.moneyLine, am = it.awayTeamOdds?.moneyLine, dm = it.drawOdds?.moneyLine;
              if (hm != null && am != null) {
                const ph = ml2p(hm), pa = ml2p(am), pd = dm != null ? ml2p(dm) : 0; const s = ph + pa + pd || 1;
                const favHome = ph >= pa; const favName = favHome ? home : away; const favPct = Math.round((favHome ? ph : pa) / s * 100);
                oddsLine = `\n${favName} favored ${favPct}%`;
              }
            } catch (_) {}
            blocks.push(`${flagFor(away)} ${away} at ${flagFor(home)} ${home}\n${t} CT${oddsLine}`);
          }
          const text = `📋 Match Day — ${dateLabel}\n\n${blocks.join("\n\n")}\n\nFIFA World Cup`;
          const okb = await sendText(text, false);
          if (okb && !force) { await sb.from("matchday_briefs").upsert({ brief_date: briefYmd }, { onConflict: "brief_date", ignoreDuplicates: true }); out.brief = true; }
        } else if (!force) {
          await sb.from("matchday_briefs").upsert({ brief_date: briefYmd }, { onConflict: "brief_date", ignoreDuplicates: true });
        }
      }
    } catch (_) {}

    // full-time reels: render every completed match; send fresh ones (confirmed), archive the rest
    if (!firstRun && HL_KEY) {
      const done = await sb.from("match_reels").select("match_id");
      const doneIds = new Set((done.data || []).map((r: any) => r.match_id));
      const cand = await sb.from("matches")
        .select("match_id,home,away,kickoff,finished_at")
        .eq("state", "post").not("finished_at", "is", null)
        .lte("finished_at", new Date(Date.now() - REEL_DELAY_MIN * 60 * 1000).toISOString())
        .order("finished_at", { ascending: false }).limit(60);
      let processed = 0;
      for (const m of (cand.data || [])) {
        if (doneIds.has(m.match_id)) continue;
        if (processed >= 8) break;
        processed++;
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
      }
      // full-time recap: send the stitched reel to subscribers for fresh matches (in addition to the
      // individual clip relay), then archive so the board's View Highlights keeps it.
      const ready = await sb.from("match_reels").select("match_id,url").eq("status", "ready").limit(20);
      for (const r of (ready.data || [])) {
        if (!r.url) continue;
        const mr = await sb.from("matches").select("home,away,home_score,away_score,finished_at").eq("match_id", r.match_id).maybeSingle();
        const fin = mr.data?.finished_at ? new Date(mr.data.finished_at).getTime() : 0;
        const fresh = fin && (Date.now() - fin) <= 60 * 60 * 1000;
        if (!fresh) { await sb.from("match_reels").update({ status: "archived" }).eq("match_id", r.match_id); continue; }
        const cap = `⚽ Full-time highlights\n${mr.data!.home} ${mr.data!.home_score}-${mr.data!.away_score} ${mr.data!.away}\nFIFA World Cup`;
        if (await sendVid(r.url, cap)) { await sb.from("match_reels").update({ status: "sent" }).eq("match_id", r.match_id); out.reelsSent++; }
      }
      // embed highlights: board shows them via wc_reels; send the YouTube link to subscribers for fresh matches only
      const emb = await sb.from("match_reels").select("match_id,url").eq("status", "embed").limit(20);
      for (const r of (emb.data || [])) {
        if (!r.url) continue;
        const mr = await sb.from("matches").select("home,away,finished_at").eq("match_id", r.match_id).maybeSingle();
        const fin = mr.data?.finished_at ? new Date(mr.data.finished_at).getTime() : 0;
        const fresh = fin && (Date.now() - fin) <= 60 * 60 * 1000;
        if (!fresh) continue; // historical: viewable on the board, no Telegram blast
        const cap = `🎬 Highlights: ${mr.data!.away} at ${mr.data!.home}\n${r.url}`;
        if (await sendText(cap, true)) { await sb.from("match_reels").update({ status: "embed_sent" }).eq("match_id", r.match_id); out.embedsSent++; }
      }
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
    }

    // player-stats snapshot: cache per-match boxscores (finished = final, fetched once), aggregate to
    // leaders, store one row the board reads via wc_stats(). Makes assists/shots/saves/fouls real-time.
    if (!firstRun) {
      // source from the full matches table (not just today's scoreboard) so ALL played matches aggregate.
      const cached = await sb.from("match_stat_cache").select("match_id,final");
      const finalSet = new Set((cached.data || []).filter((r: any) => r.final).map((r: any) => r.match_id));
      const allPlayed = await sb.from("matches").select("match_id,state").in("state", ["in", "post"]);
      const need = (allPlayed.data || []).filter((m: any) => !finalSet.has(m.match_id));
      let sp = 0;
      for (const m of need) {
        if (sp >= 8) break; sp++;
        const ps = await fetchMatchPlayerStats(m.match_id);
        if (ps) await sb.from("match_stat_cache").upsert({ match_id: m.match_id, data: ps, final: (m.state === "post"), updated_at: new Date().toISOString() }, { onConflict: "match_id" });
      }
      const all = await sb.from("match_stat_cache").select("data");
      const agg: Record<string, any> = {};
      for (const row of (all.data || [])) {
        for (const p of (row.data || [])) {
          const a = agg[p.id] || (agg[p.id] = { id: p.id, n: p.n, pos: p.pos, tm: p.tm, ab: p.ab, g: 0, a: 0, sot: 0, sh: 0, sv: 0, fc: 0, fs: 0, y: 0, r: 0 });
          a.g += p.g || 0; a.a += p.a || 0; a.sot += p.sot || 0; a.sh += p.sh || 0; a.sv += p.sv || 0;
          a.fc += p.fc || 0; a.fs += p.fs || 0; a.y += p.y || 0; a.r += p.r || 0;
          if (p.n && !a.n) a.n = p.n; if (p.tm && !a.tm) a.tm = p.tm; if (p.pos && !a.pos) a.pos = p.pos;
        }
      }
      const players = Object.values(agg) as any[];
      const KMAP: [string, string][] = [["goals", "g"], ["assists", "a"], ["shotsOnTarget", "sot"], ["totalShots", "sh"], ["saves", "sv"], ["foulsCommitted", "fc"], ["foulsSuffered", "fs"], ["yellowCards", "y"], ["redCards", "r"]];
      const leaders: any = {};
      for (const [cat, key] of KMAP) {
        leaders[cat] = players.filter((p) => p[key] > 0).sort((a, b) => b[key] - a[key]).slice(0, 25)
          .map((p) => ({ id: p.id, n: p.n, pos: p.pos, tm: p.tm, ab: p.ab, v: p[key] }));
      }
      await sb.from("stats_snapshot").upsert({ id: 1, data: { leaders, fetched: new Date().toISOString() }, updated_at: new Date().toISOString() }, { onConflict: "id" });
      out.statsPlayers = players.length;
    }
  } catch (e) {
    return new Response(JSON.stringify({ error: String(e), ...out }), { status: 500, headers: { "content-type": "application/json" } });
  }
  return new Response(JSON.stringify(out), { headers: { "content-type": "application/json" } });
});
