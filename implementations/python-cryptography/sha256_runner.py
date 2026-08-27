#!/usr/bin/env python3
"""cryptography.hazmat SHA-256 (typically OpenSSL-backed)."""
from __future__ import annotations

import json
import sys
import time

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.hashes import Hash


def fill_buf(size: int, seed: int) -> bytes:
    s = seed or 0xC0FFEE
    out = bytearray(size)
    for i in range(size):
        s = (s * 6364136223846793005 + 1) & 0xFFFFFFFFFFFFFFFF
        out[i] = (s >> 56) & 0xFF
    return bytes(out)


def digest_bytes(data: bytes) -> bytes:
    h = Hash(hashes.SHA256())
    h.update(data)
    return h.finalize()


def cmd_hash() -> None:
    data = sys.stdin.buffer.read()
    print(digest_bytes(data).hex())


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
        print(digest_bytes(data).hex(), flush=True)


def cmd_bench(size: int, iters: int, seed: int) -> None:
    buf = fill_buf(size, seed)
    last = digest_bytes(buf)
    for _ in range(3):
        last = digest_bytes(buf)
    t0 = time.perf_counter_ns()
    for _ in range(iters):
        last = digest_bytes(buf)
    ns = time.perf_counter_ns() - t0
    print(
        json.dumps(
            {
                "ns_total": ns,
                "hashes": iters,
                "size": size,
                "digest": last.hex(),
            }
        )
    )


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
