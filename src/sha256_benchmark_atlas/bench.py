from __future__ import annotations

import json
import platform
import random
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .analysis import check_timed_path_digests
from .fingerprint import collect_fingerprint, normalize_arch
from .registry import load_registry
from .runner import bench_once

_DIGEST_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def _validate_bench_args(
    *, ids: list[str] | None, sizes: list[int] | None, reps: int, max_size: int
) -> None:
    if type(reps) is not int or reps <= 0:
        raise ValueError("reps must be a positive integer")
    if type(max_size) is not int or max_size < 0:
        raise ValueError("max_size must be a nonnegative integer")
    if ids is not None and not ids:
        raise ValueError("ids selection must not be empty")
    if sizes is not None:
        if not sizes:
            raise ValueError("sizes selection must not be empty")
        if any(type(size) is not int or size < 0 for size in sizes):
            raise ValueError("sizes must contain only nonnegative integers")


def bench_result_success(result: dict[str, Any]) -> bool:
    observations = result.get("observations")
    return bool(
        isinstance(observations, list)
        and observations
        and all(observation.get("ok") is True for observation in observations)
        and result.get("digest_agreement", {}).get("ok") is True
    )


def _validated_raw_result(raw: Any, *, size: int, iters: int) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise TypeError("runner result must be a JSON object")
    required = ("ns_total", "hashes", "size", "digest")
    if any(key not in raw for key in required):
        raise ValueError("runner result is missing a required field")
    if any(type(raw[key]) is not int for key in ("ns_total", "hashes", "size")):
        raise ValueError("ns_total, hashes, and size must be integers")
    if raw["ns_total"] <= 0:
        raise ValueError("ns_total must be positive")
    if raw["hashes"] != iters:
        raise ValueError(f"hashes must equal requested iterations ({iters})")
    if raw["size"] != size:
        raise ValueError(f"reported size must equal requested size ({size})")
    if not isinstance(raw["digest"], str) or not _DIGEST_RE.fullmatch(raw["digest"]):
        raise ValueError("digest must be a 64-character hexadecimal string")
    return raw


def choose_iters(size: int, *, slow: bool = False) -> int:
    """Keep wall time roughly bounded across message sizes."""
    if slow:
        if size <= 64:
            return 200
        if size <= 1024:
            return 50
        if size <= 65536:
            return 10
        if size <= 1_048_576:
            return 2
        return 1
    if size <= 64:
        return 50_000
    if size <= 1024:
        return 20_000
    if size <= 65536:
        return 2_000
    if size <= 1_048_576:
        return 200
    return 20


def _host_facts() -> dict[str, Any]:
    """Enough host identity for a bench file to be self-describing when detached."""
    try:
        fp = collect_fingerprint()
        return {
            "arch": fp["cpu"].get("arch"),
            "cpu_model": fp["cpu"].get("model_name"),
            "sha256_hw": fp["cpu"].get("sha256_hw"),
            "openssl": (fp.get("tools") or {}).get("openssl"),
            "system": fp["platform"].get("system"),
        }
    except Exception:  # noqa: BLE001 - a fingerprint failure must not lose the bench
        return {"arch": normalize_arch(platform.machine())}


def run_interleaved_bench(
    root: Path,
    *,
    ids: list[str] | None = None,
    sizes: list[int] | None = None,
    reps: int = 5,
    seed: int = 1,
    max_size: int = 1_048_576,
    output: Path | None = None,
) -> dict[str, Any]:
    _validate_bench_args(ids=ids, sizes=sizes, reps=reps, max_size=max_size)
    reg = load_registry(root)
    impls = reg.by_id(ids)
    if not impls:
        raise ValueError("implementation selection must not be empty")
    all_sizes = sizes if sizes is not None else reg.message_sizes
    _validate_bench_args(ids=ids, sizes=all_sizes, reps=reps, max_size=max_size)
    sizes_f = [s for s in all_sizes if s <= max_size]
    if not sizes_f:
        raise ValueError("no selected sizes are within max_size")
    rng = random.Random(seed)
    by_id = {i.id: i for i in impls}

    observations: list[dict[str, Any]] = []
    for size in sizes_f:
        schedule: list[tuple[str, int]] = []
        for rep in range(reps):
            order = [impl.id for impl in impls]
            rng.shuffle(order)
            for iid in order:
                schedule.append((iid, rep))

        for iid, rep in schedule:
            impl = by_id[iid]
            slow = bool(impl.raw.get("slow"))
            iters = choose_iters(size, slow=slow)
            try:
                raw = bench_once(root, impl, size, iters, seed=seed + size + rep)
                raw = _validated_raw_result(raw, size=size, iters=iters)
                ns_total = raw["ns_total"]
                hashes = raw["hashes"]
                ns_per_hash = ns_total / hashes
                bytes_total = size * hashes
                gb_per_s = (bytes_total / 1e9) / (ns_total / 1e9)
                observations.append(
                    {
                        "impl": iid,
                        "size": size,
                        "rep": rep,
                        "iters": iters,
                        "ns_total": ns_total,
                        "ns_per_hash": ns_per_hash,
                        "gb_per_s": gb_per_s,
                        "digest": raw["digest"].lower(),
                        "backend": impl.backend,
                        "ok": True,
                        "error": None,
                    }
                )
            except Exception as e:  # noqa: BLE001
                observations.append(
                    {
                        "impl": iid,
                        "size": size,
                        "rep": rep,
                        "iters": iters,
                        "ok": False,
                        "error": str(e),
                    }
                )

    digest_agreement = check_timed_path_digests(observations)
    if not digest_agreement["ok"]:
        print(
            f"WARNING: timed-path digest disagreement in "
            f"{digest_agreement['disagreement_count']} cell(s); "
            "these measurements are not comparable."
        )

    result: dict[str, Any] = {
        "collected_at": datetime.now(UTC).isoformat(),
        "seed": seed,
        "reps": reps,
        "sizes": sizes_f,
        "host": _host_facts(),
        "digest_agreement": digest_agreement,
        "implementations": [i.as_dict() for i in impls],
        "observations": observations,
    }
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        result["path"] = str(output)
    return result
