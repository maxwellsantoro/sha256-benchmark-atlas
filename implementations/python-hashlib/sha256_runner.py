#!/usr/bin/env python3
"""CPython hashlib.sha256 runner (typically OpenSSL-backed)."""
from __future__ import annotations

import hashlib
import json
import sys
import time


def fill_buf(size: int, seed: int) -> bytes:
    s = seed or 0xC0FFEE
    out = bytearray(size)
    for i in range(size):
        s = (s * 6364136223846793005 + 1) & 0xFFFFFFFFFFFFFFFF
        out[i] = (s >> 56) & 0xFF
    return bytes(out)


def cmd_hash() -> None:
    data = sys.stdin.buffer.read()
    print(hashlib.sha256(data).hexdigest())


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
        print(hashlib.sha256(data).hexdigest(), flush=True)


# Warm up on a time budget instead of a fixed iteration count. A constant 3 leaves
# tiered/JIT runtimes in the interpreter for much of the timed loop, and is at the
# same time far too many iterations for a multi-second software hash of a large
# buffer. Every runner in this atlas uses the same two numbers.
WARMUP_BUDGET_NS = 200_000_000  # 200 ms
WARMUP_MAX_ITERS = 100_000


def cmd_bench(size: int, iters: int, seed: int) -> None:
    buf = fill_buf(size, seed)
    last = hashlib.sha256(buf).digest()
    w0 = time.perf_counter_ns()
    for _ in range(WARMUP_MAX_ITERS):
        last = hashlib.sha256(buf).digest()
        if time.perf_counter_ns() - w0 >= WARMUP_BUDGET_NS:
            break
    t0 = time.perf_counter_ns()
    for _ in range(iters):
        last = hashlib.sha256(buf).digest()
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
