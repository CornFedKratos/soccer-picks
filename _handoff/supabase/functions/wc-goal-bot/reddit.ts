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

// Known fan-clip video hosts seen in r/soccer match threads. The Netlify resolver
// already turns these pages into mp4s (or falls back to the ad link).
/** Global regex — reset lastIndex before manual use, or prefer extractClipLinks(). */
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

const rnorm = (s: string) =>
  (s || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036F]/g, "");
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
    const t = " " + rnorm(title).replace(/[^a-z0-9]+/g, " ").trim() + " "; // collapse hyphens/punct so "Post-Match" == "post match"
    if (t.includes(" match thread ") && !t.includes(" post match ") && !t.includes(" pre match ")
        && t.includes(" " + h + " ") && t.includes(" " + a + " ")) {
      return { id: String(k.data.id), title };
    }
  }
  return null;
}

export function parseClipsFromComments(
  json: any,
): { url: string; hostId: string; descr: string }[] {
  const out: { url: string; hostId: string; descr: string }[] = [];
  const seen = new Set<string>();
  const listing = Array.isArray(json) ? json[1] : json; // [t3 post, t1 comments]
  const kids = listing?.data?.children || [];
  for (const k of kids) {
    const body = String(k?.data?.body || "");
    const firstLine = body.split("\n").map((s) => s.trim())
      .find((s) => s && !/^https?:\/\//i.test(s)) || "";
    for (const { url, hostId } of extractClipLinks(body)) {
      if (!seen.has(hostId)) { seen.add(hostId); out.push({ url, hostId, descr: firstLine.slice(0, 200) }); }
    }
  }
  return out;
}
