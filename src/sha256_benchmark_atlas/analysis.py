from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml


def _load_bench(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _find_root(start: Path) -> Path | None:
    for candidate in [start, *start.parents]:
        if (candidate / "registry" / "implementations.yaml").is_file():
            return candidate
    return None


def _load_backends(root: Path | None) -> dict[str, str]:
    if root is None:
        return {}
    data = yaml.safe_load((root / "registry" / "implementations.yaml").read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for item in data.get("implementations", []):
        out[str(item["id"])] = str(item.get("backend", "unknown"))
    return out


def _backend_clusters(
    rows: list[dict[str, Any]],
    backends: dict[str, str],
    *,
    size: int = 1_048_576,
) -> list[dict[str, Any]]:
    """Summarize spread within each backend cluster at a given message size."""
    by_backend: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if int(row["size"]) != size:
            continue
        impl = str(row["impl"])
        backend = backends.get(impl, "unknown")
        by_backend[backend].append(row)

    clusters: list[dict[str, Any]] = []
    for backend, members in sorted(by_backend.items()):
        members_sorted = sorted(members, key=lambda r: r["ns_per_hash_median"])
        ns_vals = [float(m["ns_per_hash_median"]) for m in members_sorted]
        gb_vals = [float(m["gb_per_s_median"]) for m in members_sorted]
        spread = (max(ns_vals) / min(ns_vals)) if ns_vals and min(ns_vals) else None
        clusters.append(
            {
                "backend": backend,
                "size": size,
                "members": [m["impl"] for m in members_sorted],
                "count": len(members_sorted),
                "ns_per_hash_median_min": min(ns_vals) if ns_vals else None,
                "ns_per_hash_median_max": max(ns_vals) if ns_vals else None,
                "ns_spread_ratio": spread,
                "gb_per_s_median_best": max(gb_vals) if gb_vals else None,
                "fastest_member": members_sorted[0]["impl"] if members_sorted else None,
            }
        )
    return clusters


def summarize_files(paths: list[Path]) -> dict[str, Any]:
    """Aggregate ns/hash and GB/s by (impl, size) across result files / runner blocks."""
    by_key: dict[tuple[str, int], list[float]] = defaultdict(list)
    by_key_gb: dict[tuple[str, int], list[float]] = defaultdict(list)
    blocks = 0
    root = _find_root(paths[0].resolve()) if paths else None
    backends = _load_backends(root)

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
                "backend": backends.get(impl),
                "size": size,
                "n": len(vals),
                "ns_per_hash_median": statistics.median(vals),
                "ns_per_hash_mean": statistics.fmean(vals),
                "gb_per_s_median": statistics.median(gb),
                "gb_per_s_mean": statistics.fmean(gb),
            }
        )

    rankings: dict[str, list[dict[str, Any]]] = {}
    sizes = sorted({r["size"] for r in rows})
    for size in sizes:
        subset = [r for r in rows if r["size"] == size]
        subset.sort(key=lambda r: r["ns_per_hash_median"])
        rankings[str(size)] = [
            {
                "rank": i + 1,
                "impl": r["impl"],
                "backend": r.get("backend"),
                "ns_per_hash_median": r["ns_per_hash_median"],
                "gb_per_s_median": r["gb_per_s_median"],
            }
            for i, r in enumerate(subset)
        ]

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
                    "backend": r.get("backend"),
                    "baseline": base,
                    "ratio_ns": r["ns_per_hash_median"] / base_ns if base_ns else None,
                }
            )

    return {
        "blocks": blocks,
        "rows": rows,
        "rankings_by_size": rankings,
        "ratios_vs_baseline": ratios,
        "backend_clusters_1mib": _backend_clusters(rows, backends, size=1_048_576),
        "backend_clusters_64b": _backend_clusters(rows, backends, size=64),
    }


summarize = summarize_files
