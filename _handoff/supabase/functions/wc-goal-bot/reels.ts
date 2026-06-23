// Pure helpers for classifying Highlightly highlights. No side effects.

// A "full-match reel" = has a highlights/resumen word AND is not a per-goal or auxiliary
// clip (goal, interview, press conference, reaction, preview, training, shorts, etc.).
export function isFullReel(title: string): boolean {
  const t = (title || "").toLowerCase();
  if (!/highlights|resumen|résumé|resume|resumo/.test(t)) return false;
  if (/\bgoal\b|interview|press|conference|reaction|preview|pre-?match|training|\btrain\b|#?shorts\b|gamified|alt cast|anthem/.test(t)) return false;
  return true;
}
