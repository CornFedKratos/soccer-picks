// Pure helpers for classifying Highlightly highlights. No side effects.

// A "full-match reel" = has a highlights/resumen word AND is not a per-goal or auxiliary
// clip (goal, interview, press conference, reaction, preview, training, shorts, etc.).
export function isFullReel(title: string): boolean {
  const t = (title || "").toLowerCase();
  if (!/highlights|resumen|résumé|resume|resumo/.test(t)) return false;
  if (/\bgoal\b|interview|press|conference|reaction|preview|pre-?match|training|\btrain\b|#?shorts\b|gamified|alt cast|anthem/.test(t)) return false;
  return true;
}

// Maps a geo-locked broadcaster channel name to an ISO country code (for region-proxy download).
const CHANNEL_COUNTRY: Array<[string, string]> = [
  ["itv", "gb"], ["dazn es", "es"], ["dazn espana", "es"], ["dazn italia", "it"],
  ["bein sports france", "fr"], ["bein france", "fr"], ["dazn de", "de"],
  ["sportdigital", "de"], ["viaplay", "se"], ["supersport", "za"], ["t sports", "bd"],
  ["arena sport", "rs"], ["tnt sports", "br"], ["optus", "au"],
];
export function channelCountry(channel: string): string | null {
  const c = (channel || "").toLowerCase();
  for (const [k, v] of CHANNEL_COUNTRY) if (c.includes(k)) return v;
  return null;
}
