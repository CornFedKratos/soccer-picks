// Full-time match highlight reel: download the match's clips, stitch with ffmpeg,
// upload to Supabase Storage, mark the row ready (or 'error' with the reason). Background (15-min).
import { spawnSync } from "node:child_process";
import { mkdtempSync, writeFileSync, readFileSync, rmSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const SB_URL = process.env.SUPABASE_URL || "https://ckldrmyzmwnujzpxxjpt.supabase.co";
const SVC = process.env.SUPABASE_SERVICE_ROLE_KEY || "";
const SECRET = process.env.REEL_TRIGGER_SECRET || "";

async function mark(matchId, status, url) {
  try {
    await fetch(`${SB_URL}/rest/v1/match_reels?match_id=eq.${encodeURIComponent(matchId)}`, {
      method: "PATCH",
      headers: { Authorization: `Bearer ${SVC}`, apikey: SVC, "Content-Type": "application/json", "Content-Profile": "worldcup", Prefer: "return=minimal" },
      body: JSON.stringify({ status, url, updated_at: new Date().toISOString() }),
    });
  } catch (_) {}
}

export default async (req) => {
  let body = {};
  try { body = await req.json(); } catch (_) {}
  if (body && body.matchId) await mark(body.matchId, "debug", `envLen=${SECRET.length} gotLen=${String((body && body.secret) || "").length} match=${(body && body.secret) === SECRET}`);
  if (!SECRET || body.secret !== SECRET) return new Response("unauthorized", { status: 401 });
  const { matchId, clips } = body;
  if (!matchId || !Array.isArray(clips) || !clips.length) return new Response("bad request", { status: 400 });

  const work = mkdtempSync(join(tmpdir(), "reel-"));
  try {
    const ffmpegPath = (await import("ffmpeg-static")).default;
    if (!ffmpegPath || !existsSync(ffmpegPath)) { await mark(matchId, "error", `ERR: ffmpeg missing (${ffmpegPath})`); return new Response("no ffmpeg", { status: 200 }); }

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
    if (!files.length) { await mark(matchId, "error", "ERR: no clips downloaded"); return new Response("no clips", { status: 200 }); }

    const out = join(work, "reel.mp4");
    const inputs = [];
    const filt = [];
    const maps = [];
    files.forEach((f, i) => {
      inputs.push("-i", f);
      filt.push(`[${i}:v]scale=640:360:force_original_aspect_ratio=decrease,pad=640:360:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v${i}];[${i}:a]aresample=48000[a${i}]`);
      maps.push(`[v${i}][a${i}]`);
    });
    const fc = filt.join(";") + ";" + maps.join("") + `concat=n=${files.length}:v=1:a=1[v][a]`;
    const args = ["-y", "-loglevel", "error", ...inputs, "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
      "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", out];
    const res = spawnSync(ffmpegPath, args, { maxBuffer: 1024 * 1024 * 64 });
    if (res.status !== 0 || !existsSync(out)) {
      const why = (res.error && String(res.error)) || (res.stderr && res.stderr.toString().slice(-300)) || `exit ${res.status}`;
      await mark(matchId, "error", `ERR: ffmpeg ${why}`);
      return new Response("ffmpeg failed", { status: 200 });
    }

    const mp4 = readFileSync(out);
    const path = `${matchId}.mp4`;
    const up = await fetch(`${SB_URL}/storage/v1/object/reels/${path}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${SVC}`, apikey: SVC, "Content-Type": "video/mp4", "x-upsert": "true" },
      body: mp4,
    });
    if (!up.ok) { await mark(matchId, "error", `ERR: upload ${up.status} ${(await up.text()).slice(0, 120)}`); return new Response("upload failed", { status: 200 }); }

    await mark(matchId, "ready", `${SB_URL}/storage/v1/object/public/reels/${path}`);
    return new Response("ok", { status: 200 });
  } catch (e) {
    await mark(matchId, "error", `ERR: ${String(e).slice(0, 200)}`);
    return new Response("error", { status: 200 });
  } finally {
    try { rmSync(work, { recursive: true, force: true }); } catch (_) {}
  }
};
