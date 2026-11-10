import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

test("favicon contains valid 16px and 32px ICO frames using the existing Vektor brand colors", async () => {
  const icon = await readFile(new URL("../src/app/favicon.ico", import.meta.url));
  assert.equal(icon.readUInt16LE(0), 0);
  assert.equal(icon.readUInt16LE(2), 1);
  assert.equal(icon.readUInt16LE(4), 2);
  for (const [index, size] of [16, 32].entries()) {
    const entry = 6 + index * 16, length = icon.readUInt32LE(entry + 8), offset = icon.readUInt32LE(entry + 12);
    assert.equal(icon[entry], size); assert.equal(icon[entry + 1], size);
    assert.equal(icon.readUInt16LE(entry + 6), 32);
    assert.equal(icon.readUInt32LE(offset), 40);
    assert.equal(icon.readInt32LE(offset + 4), size);
    assert.equal(icon.readInt32LE(offset + 8), size * 2);
    assert.ok(offset + length <= icon.length);
    const pixels = icon.subarray(offset + 40, offset + 40 + size * size * 4);
    assert.ok(pixels.includes(Buffer.from([0xc1, 0xd5, 0x86, 0xff])));
    assert.ok(pixels.includes(Buffer.from([0x16, 0x15, 0x11, 0xff])));
  }
});
