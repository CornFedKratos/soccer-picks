import { assertEquals } from "jsr:@std/assert@1";
import { deriveHostId } from "./reddit.ts";

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

import { extractClipLinks } from "./reddit.ts";

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

import { parseThreadFromSearch } from "./reddit.ts";

const searchJson = {
  data: { children: [
    { data: { id: "zz111", title: "Post Match Thread: Portugal 3-0 Uzbekistan" } },
    { data: { id: "ab222", title: "Match Thread: Portugal vs Uzbekistan | FIFA World Cup" } },
    { data: { id: "cd333", title: "Match Thread: France vs Iraq" } },
  ] },
};

Deno.test("parseThreadFromSearch: matches by team tokens, ignores post-match", () => {
  const r = parseThreadFromSearch(searchJson, "Portugal", "Uzbekistan");
  assertEquals(r?.id, "ab222");
});
Deno.test("parseThreadFromSearch: token match handles name ordering", () => {
  const j = { data: { children: [
    { data: { id: "ee444", title: "Match Thread: Portugal vs DR Congo" } },
  ] } };
  assertEquals(parseThreadFromSearch(j, "Congo DR", "Portugal")?.id, "ee444");
});
Deno.test("parseThreadFromSearch: no match returns null", () => {
  assertEquals(parseThreadFromSearch(searchJson, "Brazil", "Spain"), null);
});

import { parseClipsFromComments } from "./reddit.ts";

const commentsJson = [
  { data: { children: [] } }, // [0] = the post (t3)
  { data: { children: [      // [1] = comments (t1)
    { data: { body: "GOAL! Ronaldo 1-0\nhttps://streamin.link/v/aaaaaa1" } },
    { data: { body: "no link here, just chat" } },
    { data: { body: "mirror https://dubz.link/v/bbbbbb2" } },
    { data: { body: "repost https://streamin.link/v/aaaaaa1" } },
  ] } },
];

Deno.test("parseClipsFromComments: extracts deduped clips with captions", () => {
  const r = parseClipsFromComments(commentsJson);
  assertEquals(r.length, 2);
  assertEquals(r[0].hostId, "aaaaaa1");
  assertEquals(r[0].descr, "GOAL! Ronaldo 1-0");
  assertEquals(r[1].hostId, "bbbbbb2");
});
Deno.test("parseClipsFromComments: empty/garbage returns []", () => {
  assertEquals(parseClipsFromComments(null).length, 0);
  assertEquals(parseClipsFromComments([{}, {}]).length, 0);
});

Deno.test("parseThreadFromSearch: excludes hyphenated Post-Match Thread", () => {
  const j = { data: { children: [
    { data: { id: "pm1", title: "Post-Match Thread: Portugal 3-0 Uzbekistan" } },
    { data: { id: "mt1", title: "Match Thread: Portugal vs Uzbekistan" } },
  ] } };
  assertEquals(parseThreadFromSearch(j, "Portugal", "Uzbekistan")?.id, "mt1");
});
Deno.test("parseThreadFromSearch: excludes hyphenated Pre-Match Thread", () => {
  const j = { data: { children: [
    { data: { id: "pre1", title: "Pre-Match Thread: Brazil vs Spain" } },
  ] } };
  assertEquals(parseThreadFromSearch(j, "Brazil", "Spain"), null);
});

Deno.test("parseThreadFromSearch: token match is word-boundary safe", () => {
  const j = { data: { children: [
    { data: { id: "bad1", title: "Match Thread: Romania vs Germany" } },
  ] } };
  // 'Oman' token 'oman' is a substring of 'romania' — must NOT match
  assertEquals(parseThreadFromSearch(j, "Oman", "Germany"), null);
});

Deno.test("parseClipsFromComments: descr skips a leading bare URL line", () => {
  const j = [ { data: { children: [] } }, { data: { children: [
    { data: { body: "https://streamin.link/v/ccccccc\nGoal by Messi" } },
  ] } } ];
  const r = parseClipsFromComments(j);
  assertEquals(r[0].descr, "Goal by Messi");
});
