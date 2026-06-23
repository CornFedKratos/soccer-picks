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
