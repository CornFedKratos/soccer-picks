// Temporary diagnostic: returns env/secret/ffmpeg state directly (synchronous, not background).
export default async (req) => {
  let b = {};
  try { b = await req.json(); } catch (_) {}
  const SECRET = process.env.REEL_TRIGGER_SECRET || "";
  const SVC = process.env.SUPABASE_SERVICE_ROLE_KEY || "";
  let ffmpeg = "?";
  try { ffmpeg = ((await import("ffmpeg-static")).default) || "null"; } catch (e) { ffmpeg = "IMPORT_ERR:" + String(e).slice(0, 140); }
  return new Response(JSON.stringify({
    envSecretLen: SECRET.length,
    gotLen: String(b.secret || "").length,
    match: b.secret === SECRET,
    svcLen: SVC.length,
    ffmpeg,
  }), { headers: { "content-type": "application/json" } });
};
