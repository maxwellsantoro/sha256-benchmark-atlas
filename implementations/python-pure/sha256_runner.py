#!/usr/bin/env python3
"""Pure-Python SHA-256 (pedagogical / abstraction-boundary contrast)."""
from __future__ import annotations

import json
import struct
import sys
import time

_K = [
    0x428A2F98,
    0x71374491,
    0xB5C0FBCF,
    0xE9B5DBA5,
    0x3956C25B,
    0x59F111F1,
    0x923F82A4,
    0xAB1C5ED5,
    0xD807AA98,
    0x12835B01,
    0x243185BE,
    0x550C7DC3,
    0x72BE5D74,
    0x80DEB1FE,
    0x9BDC06A7,
    0xC19BF174,
    0xE49B69C1,
    0xEFBE4786,
    0x0FC19DC6,
    0x240CA1CC,
    0x2DE92C6F,
    0x4A7484AA,
    0x5CB0A9DC,
    0x76F988DA,
    0x983E5152,
    0xA831C66D,
    0xB00327C8,
    0xBF597FC7,
    0xC6E00BF3,
    0xD5A79147,
    0x06CA6351,
    0x14292967,
    0x27B70A85,
    0x2E1B2138,
    0x4D2C6DFC,
    0x53380D13,
    0x650A7354,
    0x766A0ABB,
    0x81C2C92E,
    0x92722C85,
    0xA2BFE8A1,
    0xA81A664B,
    0xC24B8B70,
    0xC76C51A3,
    0xD192E819,
    0xD6990624,
    0xF40E3585,
    0x106AA070,
    0x19A4C116,
    0x1E376C08,
    0x2748774C,
    0x34B0BCB5,
    0x391C0CB3,
    0x4ED8AA4A,
    0x5B9CCA4F,
    0x682E6FF3,
    0x748F82EE,
    0x78A5636F,
    0x84C87814,
    0x8CC70208,
    0x90BEFFFA,
    0xA4506CEB,
    0xBEF9A3F7,
    0xC67178F2,
]


def _rotr(x: int, n: int) -> int:
    return ((x >> n) | (x << (32 - n))) & 0xFFFFFFFF


def sha256(data: bytes) -> bytes:
    h0, h1, h2, h3 = 0x6A09E667, 0xBB67AE85, 0x3C6EF372, 0xA54FF53A
    h4, h5, h6, h7 = 0x510E527F, 0x9B05688C, 0x1F83D9AB, 0x5BE0CD19
    bit_len = len(data) * 8
    msg = data + b"\x80"
    msg += b"\x00" * ((56 - (len(msg) % 64)) % 64)
    msg += struct.pack(">Q", bit_len)
    for i in range(0, len(msg), 64):
        chunk = msg[i : i + 64]
        w = list(struct.unpack(">16I", chunk)) + [0] * 48
        for t in range(16, 64):
            s0 = _rotr(w[t - 15], 7) ^ _rotr(w[t - 15], 18) ^ (w[t - 15] >> 3)
            s1 = _rotr(w[t - 2], 17) ^ _rotr(w[t - 2], 19) ^ (w[t - 2] >> 10)
            w[t] = (w[t - 16] + s0 + w[t - 7] + s1) & 0xFFFFFFFF
        a, b, c, d, e, f, g, h = h0, h1, h2, h3, h4, h5, h6, h7
        for t in range(64):
            s1 = _rotr(e, 6) ^ _rotr(e, 11) ^ _rotr(e, 25)
            ch = (e & f) ^ ((~e) & g)
            temp1 = (h + s1 + ch + _K[t] + w[t]) & 0xFFFFFFFF
            s0 = _rotr(a, 2) ^ _rotr(a, 13) ^ _rotr(a, 22)
            maj = (a & b) ^ (a & c) ^ (b & c)
            temp2 = (s0 + maj) & 0xFFFFFFFF
            h, g, f, e, d, c, b, a = g, f, e, (d + temp1) & 0xFFFFFFFF, c, b, a, (
                temp1 + temp2
            ) & 0xFFFFFFFF
        h0 = (h0 + a) & 0xFFFFFFFF
        h1 = (h1 + b) & 0xFFFFFFFF
        h2 = (h2 + c) & 0xFFFFFFFF
        h3 = (h3 + d) & 0xFFFFFFFF
        h4 = (h4 + e) & 0xFFFFFFFF
        h5 = (h5 + f) & 0xFFFFFFFF
        h6 = (h6 + g) & 0xFFFFFFFF
        h7 = (h7 + h) & 0xFFFFFFFF
    return struct.pack(">8I", h0, h1, h2, h3, h4, h5, h6, h7)


def fill_buf(size: int, seed: int) -> bytes:
    s = seed or 0xC0FFEE
    out = bytearray(size)
    for i in range(size):
        s = (s * 6364136223846793005 + 1) & 0xFFFFFFFFFFFFFFFF
        out[i] = (s >> 56) & 0xFF
    return bytes(out)


def cmd_hash() -> None:
    data = sys.stdin.buffer.read()
    print(sha256(data).hex())


def cmd_verify() -> None:
    inp = sys.stdin.buffer
    while True:
        hdr = inp.read(4)
        if len(hdr) < 4:
            break
        n = int.from_bytes(hdr, "big")
        data = inp.read(n) if n else b""
        if len(data) != n:
            raise SystemExit("truncated verify message")
        print(sha256(data).hex(), flush=True)


def cmd_bench(size: int, iters: int, seed: int) -> None:
    buf = fill_buf(size, seed)
    last = sha256(buf)
    for _ in range(3):
        last = sha256(buf)
    t0 = time.perf_counter_ns()
    for _ in range(iters):
        last = sha256(buf)
    ns = time.perf_counter_ns() - t0
    print(json.dumps({"ns_total": ns, "hashes": iters, "size": size, "digest": last.hex()}))


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: sha256_runner.py hash | verify | bench SIZE ITERS [SEED]", file=sys.stderr)
        sys.exit(2)
    if sys.argv[1] == "hash":
        cmd_hash()
        return
    if sys.argv[1] == "verify":
        cmd_verify()
        return
    if sys.argv[1] == "bench" and len(sys.argv) >= 4:
        size = int(sys.argv[2])
        iters = int(sys.argv[3])
        seed = int(sys.argv[4]) if len(sys.argv) >= 5 else 1
        cmd_bench(size, iters, seed)
        return
    print("usage: sha256_runner.py hash | verify | bench SIZE ITERS [SEED]", file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
