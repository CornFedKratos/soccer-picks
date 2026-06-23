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
