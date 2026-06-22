// YouTube highlight reel. Some Highlightly highlights are YouTube videos rather than streamff
// clips; this function downloads one with yt-dlp, transcodes to our standard reel format, uploads
// to the signed URL, and marks the row via wc_reel_done. Keyless design like match-reel-background:
// only needs the trigger secret + the public publishable key. Background (15-min).
import { spawnSync } from "node:child_process";
import { mkdtempSync, writeFileSync, readFileSync, rmSync, existsSync, chmodSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const SB_URL = "https://ckldrmyzmwnujzpxxjpt.supabase.co";
const PUB = "sb_publishable_bsmzithS3xRk2_VLdBKFKg_97YqazB6";
const SECRET = process.env.REEL_TRIGGER_SECRET || "";
const YTDLP_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_linux";
const YTDLP_PATH = join(tmpdir(), "yt-dlp_linux");
const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36";

async function mark(matchId, status, url) {
  try {
    await fetch(`${SB_URL}/rest/v1/rpc/wc_reel_done`, {
      method: "POST",
      headers: { apikey: PUB, Authorization: `Bearer ${PUB}`, "Content-Type": "application/json", "Content-Profile": "worldcup" },
      body: JSON.stringify({ p_secret: SECRET, p_match: matchId, p_url: url, p_status: status }),
    });
  } catch (_) {}
}

// Fetch the standalone yt-dlp binary once per cold start; reuse on warm invocations.
async function ensureYtdlp() {
  if (existsSync(YTDLP_PATH)) { try { if (statSync(YTDLP_PATH).size > 1_000_000) return YTDLP_PATH; } catch (_) {} }
  const r = await fetch(YTDLP_URL, { redirect: "follow" });
  if (!r.ok) throw new Error(`fetch ${r.status}`);
  writeFileSync(YTDLP_PATH, Buffer.from(await r.arrayBuffer()));
  chmodSync(YTDLP_PATH, 0o755);
  return YTDLP_PATH;
}

export default async (req) => {
  let body = {};
  try { body = await req.json(); } catch (_) {}
  if (!SECRET || body.secret !== SECRET) return new Response("unauthorized", { status: 401 });
  const { matchId, youtubeUrl, uploadToken, probe } = body;
  if (!youtubeUrl) return new Response("bad request", { status: 400 });
  if (!probe && (!matchId || !uploadToken)) return new Response("bad request", { status: 400 });
  const jsonRes = (obj) => new Response(JSON.stringify(obj), { status: 200, headers: { "content-type": "application/json" } });

  const work = mkdtempSync(join(tmpdir(), "ytreel-"));
  try {
    const ffmpegPath = (await import("ffmpeg-static")).default;
    if (!ffmpegPath || !existsSync(ffmpegPath)) { if (probe) return jsonRes({ ok: false, why: "ffmpeg missing" }); await mark(matchId, "error", "ERR: ffmpeg missing"); return new Response("no ffmpeg", { status: 200 }); }

    let ytdlp;
    try { ytdlp = await ensureYtdlp(); } catch (e) { if (probe) { await mark("__ytprobe__", "probe_fail", `ytdlp fetch ${String(e).slice(0, 120)}`); return jsonRes({ ok: false }); } await mark(matchId, "error", `ERR: ytdlp fetch ${String(e).slice(0, 80)}`); return new Response("no ytdlp", { status: 200 }); }

    // PROBE: list formats only (no download) to verify YouTube is reachable from this IP. Result -> DB row.
    if (probe) {
      const lf = spawnSync(ytdlp, [youtubeUrl, "-F", "--no-warnings", "--no-cache-dir", "--force-ipv4",
        "--user-agent", UA, "--extractor-args", "youtube:player_client=android,web_safari,web"],
        { maxBuffer: 1024 * 1024 * 32, timeout: 90 * 1000, env: { ...process.env, HOME: work } });
      const okp = lf.status === 0 && /\b(mp4|webm|m4a|audio only|video only|\d+x\d+)\b/.test((lf.stdout || "").toString());
      const tail = okp
        ? ("OK " + (lf.stdout || "").toString().split("\n").filter((l) => /\d+x\d+/.test(l)).length + " video formats").slice(0, 400)
        : ("FAIL: " + ((lf.error && String(lf.error)) || (lf.stderr && lf.stderr.toString().slice(-380)) || `status ${lf.status}`)).slice(0, 600);
      await mark("__ytprobe__", okp ? "probe_ok" : "probe_fail", tail);
      return jsonRes({ ok: okp });
    }

    // Download best <=720p as a single mp4. Try multiple player clients to dodge datacenter-IP blocks.
    const raw = join(work, "src.mp4");
    const dl = spawnSync(ytdlp, [
      youtubeUrl,
      "-f", "bv*[height<=720]+ba/b[height<=720]/b",
      "--merge-output-format", "mp4",
      "--ffmpeg-location", ffmpegPath,
      "--no-playlist", "--no-progress", "--no-warnings", "--no-cache-dir", "--force-ipv4",
      "--user-agent", UA,
      "--extractor-args", "youtube:player_client=android,web_safari,web",
      "--retries", "3", "--fragment-retries", "3",
      "-o", raw,
    ], { maxBuffer: 1024 * 1024 * 64, timeout: 8 * 60 * 1000, env: { ...process.env, HOME: work } });
    if (dl.status !== 0 || !existsSync(raw)) {
      const why = (dl.error && String(dl.error)) || (dl.stderr && dl.stderr.toString().slice(-260)) || `status ${dl.status}`;
      await mark(matchId, "error", `ERR: ytdlp ${why}`);
      return new Response("ytdlp failed", { status: 200 });
    }

    // Transcode to the same spec as stitched reels so it plays in the same inline player and stays small.
    const out = join(work, "reel.mp4");
    const args = ["-y", "-loglevel", "error", "-i", raw,
      "-vf", "scale=640:360:force_original_aspect_ratio=decrease,pad=640:360:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30",
      "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", out];
    const res = spawnSync(ffmpegPath, args, { maxBuffer: 1024 * 1024 * 64, timeout: 6 * 60 * 1000 });
    if (res.status !== 0 || !existsSync(out)) {
      await mark(matchId, "error", `ERR: ffmpeg ${(res.error && String(res.error)) || (res.stderr && res.stderr.toString().slice(-200)) || res.status}`);
      return new Response("ffmpeg failed", { status: 200 });
    }

    const mp4 = readFileSync(out);
    const up = await fetch(`${SB_URL}/storage/v1/object/upload/sign/reels/${matchId}.mp4?token=${encodeURIComponent(uploadToken)}`, {
      method: "PUT", headers: { "Content-Type": "video/mp4", "x-upsert": "true" }, body: mp4 });
    if (!up.ok) { await mark(matchId, "error", `ERR: upload ${up.status} ${(await up.text()).slice(0, 120)}`); return new Response("upload failed", { status: 200 }); }

    await mark(matchId, "ready", `${SB_URL}/storage/v1/object/public/reels/${matchId}.mp4`);
    return new Response("ok", { status: 200 });
  } catch (e) {
    await mark(matchId, "error", `ERR: ${String(e).slice(0, 200)}`);
    return new Response("error", { status: 200 });
  } finally {
    try { rmSync(work, { recursive: true, force: true }); } catch (_) {}
  }
};
