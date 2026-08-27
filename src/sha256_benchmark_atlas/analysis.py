from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


def _load_bench(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def summarize_files(paths: list[Path]) -> dict[str, Any]:
    """Aggregate ns/hash and GB/s by (impl, size) across result files / runner blocks."""
    by_key: dict[tuple[str, int], list[float]] = defaultdict(list)
    by_key_gb: dict[tuple[str, int], list[float]] = defaultdict(list)
    blocks = 0
    for path in paths:
        data = _load_bench(path)
        blocks += 1
        for obs in data.get("observations", []):
            if not obs.get("ok", False):
                continue
            key = (obs["impl"], int(obs["size"]))
            by_key[key].append(float(obs["ns_per_hash"]))
            by_key_gb[key].append(float(obs["gb_per_s"]))

    rows: list[dict[str, Any]] = []
    for (impl, size), vals in sorted(by_key.items(), key=lambda x: (x[0][1], x[0][0])):
        gb = by_key_gb[(impl, size)]
        rows.append(
            {
                "impl": impl,
                "size": size,
                "n": len(vals),
                "ns_per_hash_median": statistics.median(vals),
                "ns_per_hash_mean": statistics.fmean(vals),
                "gb_per_s_median": statistics.median(gb),
                "gb_per_s_mean": statistics.fmean(gb),
            }
        )

    # Within each size, rank by median ns/hash (lower is better)
    rankings: dict[str, list[dict[str, Any]]] = {}
    sizes = sorted({r["size"] for r in rows})
    for size in sizes:
        subset = [r for r in rows if r["size"] == size]
        subset.sort(key=lambda r: r["ns_per_hash_median"])
        rankings[str(size)] = [
            {
                "rank": i + 1,
                "impl": r["impl"],
                "ns_per_hash_median": r["ns_per_hash_median"],
                "gb_per_s_median": r["gb_per_s_median"],
            }
            for i, r in enumerate(subset)
        ]

    # Pairwise ratios vs first production-ish baseline if present
    baselines = ["c-openssl", "rust-sha2", "go-stdlib"]
    ratios: list[dict[str, Any]] = []
    for size in sizes:
        subset = {r["impl"]: r for r in rows if r["size"] == size}
        base = next((b for b in baselines if b in subset), None)
        if not base:
            continue
        base_ns = subset[base]["ns_per_hash_median"]
        for impl, r in subset.items():
            ratios.append(
                {
                    "size": size,
                    "impl": impl,
                    "baseline": base,
                    "ratio_ns": r["ns_per_hash_median"] / base_ns if base_ns else None,
                }
            )

    return {
        "blocks": blocks,
        "rows": rows,
        "rankings_by_size": rankings,
        "ratios_vs_baseline": ratios,
    }


# Re-export for `sha256-atlas summarize`
summarize = summarize_files
