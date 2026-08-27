from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .registry import load_registry
from .runner import bench_once


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
    reg = load_registry(root)
    impls = reg.by_id(ids)
    all_sizes = sizes if sizes is not None else reg.message_sizes
    sizes_f = [s for s in all_sizes if s <= max_size]
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
                ns_total = int(raw["ns_total"])
                hashes = int(raw["hashes"])
                ns_per_hash = ns_total / hashes if hashes else float("nan")
                bytes_total = size * hashes
                gb_per_s = (bytes_total / 1e9) / (ns_total / 1e9) if ns_total else float("nan")
                observations.append(
                    {
                        "impl": iid,
                        "size": size,
                        "rep": rep,
                        "iters": iters,
                        "ns_total": ns_total,
                        "ns_per_hash": ns_per_hash,
                        "gb_per_s": gb_per_s,
                        "digest": raw.get("digest"),
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

    result: dict[str, Any] = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "seed": seed,
        "reps": reps,
        "sizes": sizes_f,
        "implementations": [i.as_dict() for i in impls],
        "observations": observations,
    }
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        result["path"] = str(output)
    return result
