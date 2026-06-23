// Throwaway diagnostic: fetch a URL from Netlify's egress and report status/content-type/size.
// Used to determine whether Netlify's datacenter IPs are blocked by streamain's Cloudflare.
export default async (req) => {
  const u = new URL(req.url).searchParams.get("u");
  if (!u) return new Response("missing u", { status: 400 });
  try {
    const r = await fetch(u, {
      headers: {
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "referer": "https://streamain.com/", "accept": "*/*",
      },
    });
    const ct = r.headers.get("content-type") || "";
    const buf = new Uint8Array(await r.arrayBuffer());
    return new Response(JSON.stringify({ status: r.status, ct, bytes: buf.length }), { headers: { "content-type": "application/json" } });
  } catch (e) {
    return new Response(JSON.stringify({ error: String(e) }), { status: 200 });
  }
};
