// Temporary diagnostic: tests the exact Supabase write paths the reel uses.
export default async (req) => {
  let b = {};
  try { b = await req.json(); } catch (_) {}
  const SB_URL = process.env.SUPABASE_URL || "https://ckldrmyzmwnujzpxxjpt.supabase.co";
  const SVC = process.env.SUPABASE_SERVICE_ROLE_KEY || "";
  const SECRET = process.env.REEL_TRIGGER_SECRET || "";
  let patch = "?", upload = "?";
  try {
    const r = await fetch(`${SB_URL}/rest/v1/match_reels?match_id=eq.760450`, {
      method: "PATCH",
      headers: { Authorization: `Bearer ${SVC}`, apikey: SVC, "Content-Type": "application/json", "Content-Profile": "worldcup", Prefer: "return=minimal" },
      body: JSON.stringify({ status: "diagtest" }),
    });
    patch = r.status + " " + (await r.text()).slice(0, 150);
  } catch (e) { patch = "ERR:" + String(e).slice(0, 150); }
  try {
    const r = await fetch(`${SB_URL}/storage/v1/object/reels/diag.txt`, {
      method: "POST",
      headers: { Authorization: `Bearer ${SVC}`, apikey: SVC, "Content-Type": "text/plain", "x-upsert": "true" },
      body: "hi",
    });
    upload = r.status + " " + (await r.text()).slice(0, 150);
  } catch (e) { upload = "ERR:" + String(e).slice(0, 150); }
  return new Response(JSON.stringify({ envSecretLen: SECRET.length, match: b.secret === SECRET, svcLen: SVC.length, patch, upload }), { headers: { "content-type": "application/json" } });
};
