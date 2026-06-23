import { assert, assertEquals } from "jsr:@std/assert@1";
import { isFullReel } from "./reels.ts";

Deno.test("isFullReel: FIFA full-match reel", () => {
  assert(isFullReel("Highlights | USA 4-1 Paraguay | FIFA World Cup 2026™"));
});
Deno.test("isFullReel: ITV reel with 'v' and no scoreline", () => {
  assert(isFullReel("HIGHLIGHTS - Norway v Senegal | Goals Galore! | FIFA World Cup 2026"));
});
Deno.test("isFullReel: per-goal clip is NOT a reel", () => {
  assertEquals(isFullReel("Erling Haaland Goal | Norway 3-2 Senegal"), false);
});
Deno.test("isFullReel: press conference is NOT a reel", () => {
  assertEquals(isFullReel("Post-Match Press Conference: Norway's Ståle Solbakken"), false);
});
Deno.test("isFullReel: gamified/alt-cast excluded", () => {
  assertEquals(isFullReel("Gamified Highlights: Uruguay v Cabo Verde"), false);
  assertEquals(isFullReel("Alt Cast Highlights: Jordan v Algeria"), false);
});
Deno.test("isFullReel: reaction excluded", () => {
  assertEquals(isFullReel("Reaction to Kylian Mbappe's brace in France's win"), false);
});
Deno.test("isFullReel: needs a reel word", () => {
  assertEquals(isFullReel("Norway 🆚 Senegal #FIFAWorldCupOnYT"), false);
});

import { channelCountry } from "./reels.ts";

Deno.test("channelCountry: known geo channels", () => {
  assertEquals(channelCountry("ITV Sport"), "gb");
  assertEquals(channelCountry("DAZN ES"), "es");
  assertEquals(channelCountry("DAZN Italia"), "it");
  assertEquals(channelCountry("beIN SPORTS France"), "fr");
});
Deno.test("channelCountry: unknown/US channel returns null", () => {
  assertEquals(channelCountry("ESPN FC"), null);
  assertEquals(channelCountry("FIFA"), null);
  assertEquals(channelCountry(""), null);
});
