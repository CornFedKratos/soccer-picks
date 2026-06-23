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
  (s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
// longest alphabetic token in a team name (e.g. "DR Congo" -> "congo")
const longestTok = (s: string) =>
  rnorm(s).split(/[^a-z]+/).filter((w) => w.length >= 3).sort((a, b) => b.length - a.length)[0] || rnorm(s);

// Parse r/soccer's Atom submissions feed into clip-host posts. Goal posts are titled
// "Team [score] - score Team - Scorer min'" and their <content> HTML links to a clip host.
export function parseGoalPostsFromFeed(xml: string): { title: string; url: string; hostId: string }[] {
  const out: { title: string; url: string; hostId: string }[] = [];
  const seen = new Set<string>();
  const unesc = (s: string) =>
    s.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"')
     .replace(/&#39;/g, "'").replace(/&#(\d+);/g, (_, n) => String.fromCharCode(+n))
     .replace(/&amp;/g, "&");
  const entries = String(xml || "").split(/<entry[\s>]/i).slice(1);
  for (const e of entries) {
    const tm = e.match(/<title[^>]*>([\s\S]*?)<\/title>/i);
    const title = unesc(tm ? tm[1].trim() : "");
    const cm = e.match(/<content[^>]*>([\s\S]*?)<\/content>/i);
    const content = unesc(cm ? cm[1] : "");
    const links = extractClipLinks(content);
    if (links.length && !seen.has(links[0].hostId)) {
      seen.add(links[0].hostId);
      out.push({ title, url: links[0].url, hostId: links[0].hostId });
    }
  }
  return out;
}

// True if a post title references BOTH teams (longest token of each), word-boundary safe.
export function teamMatchesTitle(title: string, home: string, away: string): boolean {
  const t = " " + rnorm(title).replace(/[^a-z0-9]+/g, " ").trim() + " ";
  const h = longestTok(home), a = longestTok(away);
  return t.includes(" " + h + " ") && t.includes(" " + a + " ");
}
