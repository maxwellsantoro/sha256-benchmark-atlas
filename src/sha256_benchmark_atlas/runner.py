from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
from pathlib import Path

from .registry import Implementation


def runner_argv(root: Path, impl: Implementation) -> list[str]:
    binary = root / impl.binary
    interpreter = impl.interpreter
    if interpreter == "python":
        return [sys.executable, str(binary)]
    if interpreter == "node":
        return ["node", str(binary)]
    if interpreter == "ruby":
        return ["ruby", str(binary)]
    if interpreter == "php":
        return ["php", str(binary)]
    if interpreter == "bun":
        return ["bun", str(binary)]
    if interpreter == "java":
        main = impl.java_main or "Sha256Runner"
        cp = os.pathsep.join([str(binary), str(root / impl.java_cp)] if impl.java_cp else [str(binary)])
        return ["java", "-cp", cp, main]
    return [str(binary)]


def hash_bytes(root: Path, impl: Implementation, data: bytes, timeout: float = 120.0) -> str:
    cmd = runner_argv(root, impl) + ["hash"]
    r = subprocess.run(
        cmd,
        input=data,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if r.returncode != 0:
        err = (r.stderr or b"").decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"{impl.id} hash failed: {err}")
    return r.stdout.decode("utf-8").strip().lower()


def verify_batch(
    root: Path,
    impl: Implementation,
    messages: list[bytes],
    timeout: float = 600.0,
) -> list[str]:
    """Length-prefixed batch verify: [u32 BE len][bytes]... → hex digests."""
    payload = bytearray()
    for msg in messages:
        payload.extend(struct.pack(">I", len(msg)))
        payload.extend(msg)
    cmd = runner_argv(root, impl) + ["verify"]
    # Pure-Python correctness can be very slow at scale.
    if impl.raw.get("slow"):
        timeout = max(timeout, 3600.0)
    r = subprocess.run(
        cmd,
        input=bytes(payload),
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if r.returncode != 0:
        err = (r.stderr or b"").decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"{impl.id} verify failed: {err}")
    lines = [ln.strip().lower() for ln in r.stdout.decode("utf-8").splitlines() if ln.strip()]
    if len(lines) != len(messages):
        raise RuntimeError(
            f"{impl.id} verify count mismatch: got {len(lines)} expected {len(messages)}"
        )
    return lines


def bench_once(
    root: Path,
    impl: Implementation,
    size: int,
    iters: int,
    seed: int,
    timeout: float = 600.0,
) -> dict:
    if impl.raw.get("slow"):
        timeout = max(timeout, 3600.0)
    cmd = runner_argv(root, impl) + ["bench", str(size), str(iters), str(seed)]
    r = subprocess.run(cmd, capture_output=True, timeout=timeout, check=False, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{impl.id} bench failed: {(r.stderr or '')[:400]}")
    line = r.stdout.strip().splitlines()[-1]
    return json.loads(line)
