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
