from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .registry import Implementation, load_registry
from .runner import verify_batch


def _oracle(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_nist_vectors(root: Path, *, skip_million: bool = False) -> list[tuple[str, bytes, str]]:
    path = root / "vectors" / "nist.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    out: list[tuple[str, bytes, str]] = []
    for v in data["vectors"]:
        vid = v["id"]
        if skip_million and vid == "million_a":
            continue
        if "msg_hex" in v:
            msg = bytes.fromhex(v["msg_hex"]) if v["msg_hex"] else b""
        elif "msg_ascii" in v:
            msg = v["msg_ascii"].encode("ascii")
        elif "msg_ascii_repeat" in v:
            ch, n = v["msg_ascii_repeat"]
            msg = ch.encode("ascii") * int(n)
        else:
            raise ValueError(f"vector {vid}: no message field")
        out.append((vid, msg, v["sha256"].lower()))
    return out


def boundary_vectors() -> list[tuple[str, bytes, str]]:
    sizes = [0, 1, 3, 32, 55, 56, 63, 64, 65, 80, 127, 128, 256]
    out: list[tuple[str, bytes, str]] = []
    for n in sizes:
        msg = bytes((i * 17 + 3) & 0xFF for i in range(n))
        out.append((f"boundary_{n}", msg, _oracle(msg)))
    return out


def make_prng_cases(n: int, seed: int = 0xA11CE) -> list[tuple[str, bytes, str]]:
    s = seed & 0xFFFFFFFFFFFFFFFF
    out: list[tuple[str, bytes, str]] = []
    for i in range(n):
        s = (s * 6364136223846793005 + 1) & 0xFFFFFFFFFFFFFFFF
        length = int(s % 4097)
        msg = bytearray(length)
        for j in range(length):
            s = (s * 6364136223846793005 + 1) & 0xFFFFFFFFFFFFFFFF
            msg[j] = (s >> 56) & 0xFF
        bmsg = bytes(msg)
        out.append((f"prng_{i}", bmsg, _oracle(bmsg)))
    return out


def streamish_cases(seed: int = 99) -> list[tuple[str, bytes, str]]:
    s = seed
    out: list[tuple[str, bytes, str]] = []
    for length in (100, 1000, 10000):
        buf = bytearray(length)
        for i in range(length):
            s = (s * 1103515245 + 12345) & 0xFFFFFFFF
            buf[i] = (s >> 16) & 0xFF
        p = bytes(buf)
        out.append((f"streamish_{len(p)}", p, _oracle(p)))
    return out


def check_impl(
    root: Path,
    impl: Implementation,
    cases: list[tuple[str, bytes, str]],
) -> dict[str, Any]:
    messages = [msg for _, msg, _ in cases]
    failures: list[dict[str, str]] = []
    try:
        got_list = verify_batch(root, impl, messages)
    except Exception as e:  # noqa: BLE001
        return {
            "id": impl.id,
            "checked": 0,
            "failed": 1,
            "failures": [{"case": "<batch>", "error": str(e)}],
            "ok": False,
        }
    for (cid, msg, exp), got in zip(cases, got_list, strict=True):
        if got != exp:
            failures.append(
                {
                    "case": cid,
                    "expected": exp,
                    "got": got,
                    "len": str(len(msg)),
                }
            )
            if len(failures) >= 5:
                break
    return {
        "id": impl.id,
        "checked": len(cases),
        "failed": len(failures),
        "failures": failures,
        "ok": len(failures) == 0,
    }


def run_correctness(
    root: Path,
    ids: list[str] | None = None,
    prng_cases: int = 10_000,
    skip_million: bool = False,
) -> dict[str, Any]:
    reg = load_registry(root)
    impls = reg.by_id(ids)
    cases = (
        load_nist_vectors(root, skip_million=skip_million)
        + boundary_vectors()
        + streamish_cases()
        + make_prng_cases(prng_cases)
    )
    results = [check_impl(root, impl, cases) for impl in impls]
    passed = all(r["ok"] for r in results) and len(results) > 0
    return {
        "passed": passed,
        "case_count": len(cases),
        "implementations": results,
    }
