// Full-time match highlight reel AND single per-goal clip compression. Keyless design: the worker
// (which holds the service role) mints a one-time signed upload URL and passes it in; this function
// only needs the trigger secret + the public publishable key. Resolves the real media URL DYNAMICALLY
// (streamff keeps changing its CDN/host), transcodes with ffmpeg (also shrinks oversized clips so they
// fit Telegram's 20MB send-by-URL limit), uploads to the signed URL, marks via a code-gated RPC. (15-min.)
//   Reel mode:  { matchId, clips:[{url}], uploadToken }            -> reels/<matchId>.mp4, wc_reel_done
//   Clip mode:  { clipId|goalId, outName, clips:[{url}], uploadToken } -> reels/<outName>, wc_clipq_done/wc_clip_done
// clips[].url may be a streamff PAGE url (e.g. streamff.pro/v/<id>) or a direct media url; resolveMedia() figures it out.
import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const SB_URL = "https://ckldrmyzmwnujzpxxjpt.supabase.co";
const PUB = "sb_publishable_bsmzithS3xRk2_VLdBKFKg_97YqazB6";
const SECRET = process.env.REEL_TRIGGER_SECRET || "";
const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36";

async function rpc(name, payload) {
  try {
    await fetch(`${SB_URL}/rest/v1/rpc/${name}`, {
      method: "POST",
      headers: { apikey: PUB, Authorization: `Bearer ${PUB}`, "Content-Type": "application/json", "Content-Profile": "worldcup" },
      body: JSON.stringify(payload),
    });
  } catch (_) {}
}

// Does this URL serve real media (not an HTML error page)?
async function isMedia(u) {
  try {
    const r = await fetch(u, { headers: { range: "bytes=0-3", "user-agent": UA } });
    if (!(r.ok || r.status === 206)) return false;
    const ct = (r.headers.get("content-type") || "").toLowerCase();
    if (ct.includes("text/html")) return false;
    if (ct.includes("video") || ct.includes("mpegurl") || ct.includes("octet-stream")) return true;
    if (/\.m3u8(\?|$)/i.test(u)) return true;
    const b = new Uint8Array(await r.arrayBuffer());
    return b.length > 0;
  } catch (_) { return false; }
}

// Resolve a highlight share URL to a downloadable mp4/m3u8 — fully self-healing, NO reliance on a fixed
// host. The share page URL comes live from Highlightly each run, so we just read whatever it currently
// points to: scrape the page for a direct media URL or CDN base, then (only if needed) its referenced
// scripts (covers JS-gated pages), then a hardcoded fast-path as last resort. Every candidate is verified
// by fetching bytes. If the provider switches host/domain again, the page references the new one → it resolves.
async function resolveMedia(input) {
  if (/\.(mp4|m3u8)(\?|$)/i.test(input) && await isMedia(input)) return input;
  const idm = String(input).match(/\/v\/([a-z0-9]+)/i);
  const id = idm ? idm[1] : null;
  let origin = ""; try { origin = new URL(input).origin; } catch (_) {}
  const cand = [], tried = new Set();
  const add = (x) => {
    if (!x) return;
    x = x.replace(/\\u002f/gi, "/").replace(/\\\//g, "/").replace(/&amp;/g, "&");
    if (/^https?:\/\//i.test(x) && !tried.has(x)) { tried.add(x); cand.push(x); }
  };
  // discover media URLs + CDN bases from any text (page HTML or a script body)
  const scrape = (txt) => {
    for (const m of txt.matchAll(/https?:\\?\/\\?\/[^"'\s\\)#]+\.(?:mp4|m3u8)/gi)) add(m[0]);
    if (id) for (const m of txt.matchAll(/https?:\/\/[a-z0-9.-]*(?:cdn|stream|video|media|bunny|wasabi|backblaze|b2|r2|cloudflarestorage)[a-z0-9.-]*/gi)) {
      const b = m[0].replace(/\/+$/, ""); add(b + "/uploads/" + id + ".mp4"); add(b + "/" + id + ".mp4");
    }
  };
  const verify = async () => { for (const c of cand) { if (await isMedia(c)) return c; } return null; };
  try {
    const r = await fetch(String(input), { headers: { "user-agent": UA } });
    if (r.ok) {
      const html = await r.text();
      scrape(html);
      let hit = await verify(); if (hit) return hit;        // common case: page has the media URL
      // JS-gated pages: scrape the page's own referenced scripts, then re-verify
      const scripts = [...html.matchAll(/<script[^>]+src="([^"]+\.js)"/gi)].map((m) => m[1]).slice(0, 14);
      for (const s of scripts) {
        if (cand.length > 12) break;
        const su = /^https?:\/\//i.test(s) ? s : origin + (s.startsWith("/") ? "" : "/") + s;
        try { const sr = await fetch(su, { headers: { "user-agent": UA } }); if (sr.ok) scrape(await sr.text()); } catch (_) {}
      }
      hit = await verify(); if (hit) return hit;
    }
  } catch (_) {}
  // last-resort fast-path (safe if stale): current provider hosts + legacy
  if (id) { for (const h of ["c-cdn", "b-cdn", "w-cdn"]) add(`https://${h}.streamin.top/uploads/${id}.mp4`); add(`https://cdn.streamff.one/${id}.mp4`); }
  return await verify();
}

export default async (req) => {
  let body = {};
  try { body = await req.json(); } catch (_) {}
  if (!SECRET || body.secret !== SECRET) return new Response("unauthorized", { status: 401 });
  const { matchId, goalId, clipId, clips, uploadToken } = body;
  const single = !!(goalId || clipId);
  const outName = body.outName || `${matchId}.mp4`;
  if (!uploadToken || !Array.isArray(clips) || !clips.length || (!matchId && !goalId && !clipId)) return new Response("bad request", { status: 400 });

  const finish = (url) => clipId
    ? rpc("wc_clipq_done", { p_secret: SECRET, p_clip: clipId, p_url: url })
    : goalId
    ? rpc("wc_clip_done", { p_secret: SECRET, p_goal: goalId, p_url: url })
    : rpc("wc_reel_done", { p_secret: SECRET, p_match: matchId, p_url: url, p_status: "ready" });
  const fail = (msg) => single ? Promise.resolve() : rpc("wc_reel_done", { p_secret: SECRET, p_match: matchId, p_url: msg, p_status: "error" });

  const work = mkdtempSync(join(tmpdir(), "reel-"));
  try {
    const ffmpegPath = (await import("ffmpeg-static")).default;
    if (!ffmpegPath || !existsSync(ffmpegPath)) { await fail("ERR: ffmpeg missing"); return new Response("no ffmpeg", { status: 200 }); }

    // resolve every clip to a real media URL (dynamic — survives streamff CDN changes)
    const media = [];
    for (const c of clips) { const u = await resolveMedia(c.url); if (u) media.push(u); }
    if (!media.length) { await fail("ERR: no media resolved"); return new Response("no media", { status: 200 }); }

    // ffmpeg reads the remote URLs directly (handles mp4 + m3u8); transcode to a small, uniform reel
    const out = join(work, "reel.mp4");
    const inputs = [], filt = [], maps = [];
    media.forEach((u, i) => {
      inputs.push("-user_agent", UA, "-i", u);
      filt.push(`[${i}:v]scale=640:360:force_original_aspect_ratio=decrease,pad=640:360:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v${i}];[${i}:a]aresample=48000[a${i}]`);
      maps.push(`[v${i}][a${i}]`);
    });
    const fc = filt.join(";") + ";" + maps.join("") + `concat=n=${media.length}:v=1:a=1[v][a]`;
    const args = ["-y", "-loglevel", "error", ...inputs, "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
      "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-maxrate", "1400k", "-bufsize", "2800k",
      "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", out];
    const res = spawnSync(ffmpegPath, args, { maxBuffer: 1024 * 1024 * 64, timeout: 12 * 60 * 1000 });
    if (res.status !== 0 || !existsSync(out)) {
      await fail(`ERR: ffmpeg ${(res.error && String(res.error)) || (res.stderr && res.stderr.toString().slice(-200)) || res.status}`);
      return new Response("ffmpeg failed", { status: 200 });
    }

    const mp4 = readFileSync(out);
    const up = await fetch(`${SB_URL}/storage/v1/object/upload/sign/reels/${outName}?token=${encodeURIComponent(uploadToken)}`, {
      method: "PUT", headers: { "Content-Type": "video/mp4", "x-upsert": "true" }, body: mp4 });
    if (!up.ok) { await fail(`ERR: upload ${up.status} ${(await up.text()).slice(0, 120)}`); return new Response("upload failed", { status: 200 }); }

    // cache-bust the public URL so Telegram never serves a stale failure cached against a reused path
    await finish(`${SB_URL}/storage/v1/object/public/reels/${outName}?c=${Date.now()}`);
    return new Response("ok", { status: 200 });
  } catch (e) {
    await fail(`ERR: ${String(e).slice(0, 200)}`);
    return new Response("error", { status: 200 });
  } finally {
    try { rmSync(work, { recursive: true, force: true }); } catch (_) {}
  }
};
