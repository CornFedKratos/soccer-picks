import { assert, assertEquals } from "jsr:@std/assert@1";
import { deriveHostId, extractClipLinks, parseGoalPostsFromFeed, teamMatchesTitle } from "./reddit.ts";

Deno.test("deriveHostId: streamin.link/v/<id>", () => {
  assertEquals(deriveHostId("https://streamin.link/v/aB3dEf9k"), "aB3dEf9k");
});
Deno.test("deriveHostId: streamain watch URL skips 'watch'", () => {
  assertEquals(deriveHostId("https://streamain.com/HVGs0IIgcnH2WTd/watch"), "HVGs0IIgcnH2WTd");
});
Deno.test("deriveHostId: strips query and hash", () => {
  assertEquals(deriveHostId("https://streamff.live/v/Xy12Zk90?t=3#x"), "Xy12Zk90");
});
Deno.test("deriveHostId: no id-like segment returns null", () => {
  assertEquals(deriveHostId("https://example.com/a/b"), null);
});

Deno.test("extractClipLinks: finds a streamin link", () => {
  const r = extractClipLinks("GOAL Ronaldo! https://streamin.link/v/aB3dEf9k great finish");
  assertEquals(r.length, 1);
  assertEquals(r[0].hostId, "aB3dEf9k");
  assertEquals(r[0].url, "https://streamin.link/v/aB3dEf9k");
});
Deno.test("extractClipLinks: adds https:// when missing", () => {
  const r = extractClipLinks("mirror: streamja.com/abcdef");
  assertEquals(r[0].url, "https://streamja.com/abcdef");
  assertEquals(r[0].hostId, "abcdef");
});
Deno.test("extractClipLinks: dedupes same host id", () => {
  const r = extractClipLinks("https://streamin.link/v/aB3dEf9k and https://streamin.link/v/aB3dEf9k");
  assertEquals(r.length, 1);
});
Deno.test("extractClipLinks: ignores non-allowlisted hosts", () => {
  assertEquals(extractClipLinks("https://youtube.com/watch?v=zzzzzz https://example.com/x").length, 0);
});
Deno.test("extractClipLinks: multiple distinct hosts", () => {
  const r = extractClipLinks("https://streamin.link/v/aaaaaa1 https://dubz.link/v/bbbbbb2");
  assertEquals(r.length, 2);
});

const feed = `<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Portugal [5] - 0 Uzbekistan - Rafael Le&#227;o 87&#39;</title>
<content type="html">&lt;a href="https://streamff.live/v/abc123"&gt;[link]&lt;/a&gt;</content></entry>
<entry><title>Some news post</title><content type="html">&lt;a href="https://example.com/x"&gt;[link]&lt;/a&gt;</content></entry>
<entry><title>Norway [1] - 0 Senegal - Haaland 58&#39;</title>
<content type="html">&lt;a href="https://streamin.link/v/zzz999"&gt;[link]&lt;/a&gt;</content></entry>
</feed>`;

Deno.test("parseGoalPostsFromFeed: returns only clip-host posts, deduped", () => {
  const r = parseGoalPostsFromFeed(feed);
  assertEquals(r.length, 2);
  assertEquals(r[0].hostId, "abc123");
  assertEquals(r[0].url, "https://streamff.live/v/abc123");
  assert(r[0].title.includes("Rafael"));
  assertEquals(r[1].hostId, "zzz999");
});
Deno.test("parseGoalPostsFromFeed: empty/garbage returns []", () => {
  assertEquals(parseGoalPostsFromFeed("").length, 0);
  assertEquals(parseGoalPostsFromFeed("<feed></feed>").length, 0);
});

Deno.test("teamMatchesTitle: matches both teams present", () => {
  assert(teamMatchesTitle("Portugal [5] - 0 Uzbekistan - Rafael Leao 87'", "Portugal", "Uzbekistan"));
});
Deno.test("teamMatchesTitle: handles name ordering (DR Congo)", () => {
  assert(teamMatchesTitle("Portugal [1] - 0 DR Congo - Neves 23'", "Congo DR", "Portugal"));
});
Deno.test("teamMatchesTitle: rejects a different match", () => {
  assertEquals(teamMatchesTitle("Portugal [5] - 0 Uzbekistan", "Brazil", "Spain"), false);
});
Deno.test("teamMatchesTitle: word-boundary safe (oman not in romania)", () => {
  assertEquals(teamMatchesTitle("Romania [1] - 0 Germany", "Oman", "Germany"), false);
});
