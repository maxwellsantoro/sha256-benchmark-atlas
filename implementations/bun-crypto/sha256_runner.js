#!/usr/bin/env bun
"use strict";
const crypto = require("crypto");
const fs = require("fs");

function fillBuf(size, seed) {
  let s = BigInt(seed || 0xc0ffee);
  const buf = Buffer.alloc(size);
  const mul = 6364136223846793005n;
  for (let i = 0; i < size; i++) {
    s = (s * mul + 1n) & 0xffffffffffffffffn;
    buf[i] = Number((s >> 56n) & 0xffn);
  }
  return buf;
}

function digestHex(buf) {
  return crypto.createHash("sha256").update(buf).digest("hex");
}

function cmdHash() {
  const data = fs.readFileSync(0);
  process.stdout.write(digestHex(data) + "\n");
}

function cmdVerify() {
  const fd = fs.openSync("/dev/stdin", "r");
  const hdr = Buffer.alloc(4);
  for (;;) {
    let got = 0;
    while (got < 4) {
      const n = fs.readSync(fd, hdr, got, 4 - got, null);
      if (n === 0) {
        fs.closeSync(fd);
        return;
      }
      got += n;
    }
    const len = hdr.readUInt32BE(0);
    const buf = Buffer.alloc(len);
    got = 0;
    while (got < len) {
      const n = fs.readSync(fd, buf, got, len - got, null);
      if (n === 0) throw new Error("truncated verify message");
      got += n;
    }
    process.stdout.write(digestHex(buf) + "\n");
  }
}

function cmdBench(size, iters, seed) {
  const buf = fillBuf(size, seed);
  let last = digestHex(buf);
  for (let i = 0; i < 3; i++) last = digestHex(buf);
  const t0 = process.hrtime.bigint();
  for (let i = 0; i < iters; i++) last = digestHex(buf);
  const ns = Number(process.hrtime.bigint() - t0);
  process.stdout.write(
    JSON.stringify({ ns_total: ns, hashes: iters, size, digest: last }) + "\n"
  );
}

const [cmd, a, b, c] = process.argv.slice(2);
if (cmd === "hash") {
  cmdHash();
} else if (cmd === "verify") {
  cmdVerify();
} else if (cmd === "bench" && a !== undefined && b !== undefined) {
  cmdBench(Number(a), Number(b), c !== undefined ? Number(c) : 1);
} else {
  console.error("usage: sha256_runner.js hash | verify | bench SIZE ITERS [SEED]");
  process.exit(2);
}
