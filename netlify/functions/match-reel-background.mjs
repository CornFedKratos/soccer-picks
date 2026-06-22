// Full-time match highlight reel AND single per-goal clip compression. Keyless design: the worker
// (which holds the service role) mints a one-time signed upload URL and passes it in; this function
// only needs the trigger secret + the public publishable key. Downloads clip(s), transcodes with
// ffmpeg (also shrinks oversized clips so they fit Telegram's 20MB send-by-URL limit), uploads to
// the signed URL, and marks the row via a code-gated RPC. Background (15-min).
//   Reel mode:  { matchId, clips:[...], uploadToken }            -> reels/<matchId>.mp4, wc_reel_done
//   Clip mode:  { goalId, outName, clips:[{url}], uploadToken }  -> reels/<outName>,   wc_clip_done
import { spawnSync } from "node:child_process";
import { mkdtempSync, writeFileSync, readFileSync, rmSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const SB_URL = "https://ckldrmyzmwnujzpxxjpt.supabase.co";
const PUB = "sb_publishable_bsmzithS3xRk2_VLdBKFKg_97YqazB6";
const SECRET = process.env.REEL_TRIGGER_SECRET || "";

async function rpc(name, payload) {
  try {
    await fetch(`${SB_URL}/rest/v1/rpc/${name}`, {
      method: "POST",
      headers: { apikey: PUB, Authorization: `Bearer ${PUB}`, "Content-Type": "application/json", "Content-Profile": "worldcup" },
      body: JSON.stringify(payload),
    });
  } catch (_) {}
}

export default async (req) => {
  let body = {};
  try { body = await req.json(); } catch (_) {}
  if (!SECRET || body.secret !== SECRET) return new Response("unauthorized", { status: 401 });
  const { matchId, goalId, clips, uploadToken } = body;
  const isClip = !!goalId;
  const outName = body.outName || `${matchId}.mp4`;
  if (!uploadToken || !Array.isArray(clips) || !clips.length || (!matchId && !goalId)) return new Response("bad request", { status: 400 });

  // success/failure marking routes to the right RPC; clip failures leave the row null so the worker retries.
  const finish = (url) => isClip
    ? rpc("wc_clip_done", { p_secret: SECRET, p_goal: goalId, p_url: url })
    : rpc("wc_reel_done", { p_secret: SECRET, p_match: matchId, p_url: url, p_status: "ready" });
  const fail = (msg) => isClip ? Promise.resolve() : rpc("wc_reel_done", { p_secret: SECRET, p_match: matchId, p_url: msg, p_status: "error" });

  const work = mkdtempSync(join(tmpdir(), "reel-"));
  try {
    const ffmpegPath = (await import("ffmpeg-static")).default;
    if (!ffmpegPath || !existsSync(ffmpegPath)) { await fail("ERR: ffmpeg missing"); return new Response("no ffmpeg", { status: 200 }); }

    const files = [];
    for (let i = 0; i < clips.length; i++) {
      try {
        const r = await fetch(clips[i].url);
        if (!r.ok) continue;
        const buf = Buffer.from(await r.arrayBuffer());
        if (buf.length < 1000) continue;
        const f = join(work, `c${i}.mp4`);
        writeFileSync(f, buf);
        files.push(f);
      } catch (_) {}
    }
    if (!files.length) { await fail("ERR: no clips downloaded"); return new Response("no clips", { status: 200 }); }

    const out = join(work, "reel.mp4");
    const inputs = [], filt = [], maps = [];
    files.forEach((f, i) => {
      inputs.push("-i", f);
      filt.push(`[${i}:v]scale=640:360:force_original_aspect_ratio=decrease,pad=640:360:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v${i}];[${i}:a]aresample=48000[a${i}]`);
      maps.push(`[v${i}][a${i}]`);
    });
    const fc = filt.join(";") + ";" + maps.join("") + `concat=n=${files.length}:v=1:a=1[v][a]`;
    const args = ["-y", "-loglevel", "error", ...inputs, "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
      "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-maxrate", "1400k", "-bufsize", "2800k",
      "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", out];
    const res = spawnSync(ffmpegPath, args, { maxBuffer: 1024 * 1024 * 64 });
    if (res.status !== 0 || !existsSync(out)) {
      await fail(`ERR: ffmpeg ${(res.error && String(res.error)) || (res.stderr && res.stderr.toString().slice(-200)) || res.status}`);
      return new Response("ffmpeg failed", { status: 200 });
    }

    const mp4 = readFileSync(out);
    const up = await fetch(`${SB_URL}/storage/v1/object/upload/sign/reels/${outName}?token=${encodeURIComponent(uploadToken)}`, {
      method: "PUT", headers: { "Content-Type": "video/mp4", "x-upsert": "true" }, body: mp4 });
    if (!up.ok) { await fail(`ERR: upload ${up.status} ${(await up.text()).slice(0, 120)}`); return new Response("upload failed", { status: 200 }); }

    await finish(`${SB_URL}/storage/v1/object/public/reels/${outName}`);
    return new Response("ok", { status: 200 });
  } catch (e) {
    await fail(`ERR: ${String(e).slice(0, 200)}`);
    return new Response("error", { status: 200 });
  } finally {
    try { rmSync(work, { recursive: true, force: true }); } catch (_) {}
  }
};
