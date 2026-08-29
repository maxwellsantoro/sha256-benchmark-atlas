"""Aggregation for campaign results.

Two rules shape everything here:

1. **Never pool across architectures.** A median taken over 10 x86_64 blocks and
   2 aarch64 blocks describes no machine that exists. Implementations whose
   acceleration is arch-dependent (see `arch_sensitivity`) are misreported by
   several-fold when pooled.
2. **Never discard block identity.** The interleaved design exists so that
   T_A/T_B can be formed *within* one host, where host-to-host speed variation
   cancels. That requires pairing inside a block; a ratio of two pooled medians
   is not the same quantity and supports none of the claims the atlas makes.
"""

from __future__ import annotations

import gzip
import json
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .capability_audit import cross_check
from .costmodel import aggregate_models, fit_cost_model
from .fingerprint import cpu_facts_from_fingerprint

SCHEMA_VERSION = 3

# Preference order; the first one present in a block becomes that block's baseline.
BASELINE_PREFERENCE = ("c-openssl", "rust-sha2", "go-stdlib")

# An implementation is flagged as arch-sensitive when its cross-arch ratio departs
# from the cohort's by this factor — i.e. it gains or loses acceleration that its
# peers on the same two hosts do not.
ARCH_SENSITIVITY_FACTOR = 2.0


def _read_json(path: Path) -> dict[str, Any]:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)
    return json.loads(path.read_text(encoding="utf-8"))


def _find_root(start: Path) -> Path | None:
    for candidate in [start, *start.parents]:
        if (candidate / "registry" / "implementations.yaml").is_file():
            return candidate
    return None


@dataclass
class RegistryMeta:
    backends: dict[str, str] = field(default_factory=dict)
    boards: dict[str, list[str]] = field(default_factory=dict)
    board_descriptions: dict[str, str] = field(default_factory=dict)
    impl_class: dict[str, str] = field(default_factory=dict)


def _load_registry_meta(root: Path | None) -> RegistryMeta:
    if root is None:
        return RegistryMeta()
    data = yaml.safe_load((root / "registry" / "implementations.yaml").read_text(encoding="utf-8"))
    meta = RegistryMeta()
    for board in data.get("leaderboards", []):
        meta.board_descriptions[str(board["id"])] = str(board.get("description", ""))
    for item in data.get("implementations", []):
        iid = str(item["id"])
        meta.backends[iid] = str(item.get("backend", "unknown"))
        meta.boards[iid] = [str(b) for b in (item.get("leaderboards") or [])]
        meta.impl_class[iid] = str(item.get("implementation_class", "unknown"))
    return meta


@dataclass
class Block:
    """One experimental block: all implementations benched on one host."""

    block_id: str
    path: str
    arch: str
    cpu_model: str | None
    sha256_hw: bool | None
    openssl: str | None
    observations: list[dict[str, Any]]
    audit: dict[str, Any] | None = None

    def medians(self) -> dict[tuple[str, int], float]:
        """Median ns/hash per (impl, size) within this block, across its reps."""
        acc: dict[tuple[str, int], list[float]] = defaultdict(list)
        for o in self.observations:
            if o.get("ok"):
                acc[(str(o["impl"]), int(o["size"]))].append(float(o["ns_per_hash"]))
        return {k: statistics.median(v) for k, v in acc.items() if v}


def _block_arch(path: Path, data: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Resolve a block's architecture and host facts.

    Preference: the bench file's own record, then a sibling fingerprint.json, then
    the directory name. Anything unresolved is reported as "unknown" rather than
    being folded into a default, so a mislabelled block cannot silently join the
    wrong stratum.
    """
    host: dict[str, Any] = dict(data.get("host") or {})
    arch = str(host.get("arch") or "") or None

    fp_path = next(
        (
            p
            for p in (path.parent / "fingerprint.json", path.parent / "fingerprint.json.gz")
            if p.is_file()
        ),
        path.parent / "fingerprint.json",
    )
    if fp_path.is_file():
        try:
            fp = _read_json(fp_path)
        except (OSError, ValueError):
            fp = {}
        if fp:
            facts = cpu_facts_from_fingerprint(fp)
            arch = arch or facts["arch"]
            if host.get("cpu_model") is None:
                host["cpu_model"] = facts["model_name"]
            if host.get("sha256_hw") is None:
                host["sha256_hw"] = facts["sha256_hw"]
            host.setdefault("openssl", (fp.get("tools") or {}).get("openssl"))

    if not arch:
        name = path.parent.name.lower()
        if "arm" in name or "aarch64" in name:
            arch = "aarch64"
        elif "x64" in name or "x86" in name or "ubuntu" in name:
            arch = "x86_64"

    host["arch"] = arch or "unknown"
    return host["arch"], host


def load_blocks(paths: list[Path]) -> list[Block]:
    blocks: list[Block] = []
    for path in paths:
        data = _read_json(path)
        arch, host = _block_arch(path, data)
        audit_path = next(
            (
                p
                for p in (path.parent / "audit.json", path.parent / "audit.json.gz")
                if p.is_file()
            ),
            None,
        )
        audit = None
        if audit_path is not None:
            try:
                audit = _read_json(audit_path)
            except (OSError, ValueError):
                audit = None
        blocks.append(
            Block(
                block_id=host.get("block_id") or path.parent.name or path.stem,
                path=str(path),
                arch=arch,
                cpu_model=host.get("cpu_model"),
                sha256_hw=host.get("sha256_hw"),
                openssl=host.get("openssl"),
                observations=list(data.get("observations", [])),
                audit=audit,
            )
        )
    return blocks


def _dispersion(vals: list[float]) -> dict[str, Any]:
    vals = sorted(vals)
    n = len(vals)
    if n == 0:
        return {}
    med = statistics.median(vals)
    mean = statistics.fmean(vals)
    if n >= 4:
        q = statistics.quantiles(vals, n=4, method="inclusive")
        p25, p75 = q[0], q[2]
    else:
        p25, p75 = vals[0], vals[-1]
    stdev = statistics.stdev(vals) if n >= 2 else 0.0
    return {
        "n": n,
        "min": vals[0],
        "p25": p25,
        "median": med,
        "p75": p75,
        "max": vals[-1],
        "mean": mean,
        "stdev": stdev,
        "cv": (stdev / mean) if mean else None,
        "iqr_ratio": (p75 / p25) if p25 else None,
    }


def check_timed_path_digests(observations: list[dict[str, Any]]) -> dict[str, Any]:
    """Cross-check the digests produced *inside the timed loop*.

    Every runner fills its bench buffer from the same seeded PRNG, so within one
    block all implementations at a given (size, rep) must return the same digest.
    The correctness gate exercises `verify`, an entirely separate code path; without
    this check a bench loop that hashed the wrong bytes — or one the optimiser
    hoisted away — would be timed and published unchallenged.
    """
    cells: dict[tuple[int, int], dict[str, str]] = defaultdict(dict)
    for o in observations:
        if o.get("ok") and o.get("digest"):
            cells[(int(o["size"]), int(o["rep"]))][str(o["impl"])] = str(o["digest"])

    checked = 0
    disagreements: list[dict[str, Any]] = []
    for (size, rep), by_impl in sorted(cells.items()):
        if len(by_impl) < 2:
            continue
        checked += 1
        counts: dict[str, int] = defaultdict(int)
        for digest in by_impl.values():
            counts[digest] += 1
        if len(counts) > 1:
            majority = max(counts, key=lambda d: counts[d])
            disagreements.append(
                {
                    "size": size,
                    "rep": rep,
                    "majority_digest": majority,
                    "dissenting": {i: d for i, d in sorted(by_impl.items()) if d != majority},
                }
            )
    return {
        "cells_checked": checked,
        "disagreement_count": len(disagreements),
        "ok": not disagreements,
        "disagreements": disagreements[:20],
    }


def _check_digest_agreement(blocks: list[Block]) -> dict[str, Any]:
    """Run the timed-path digest check across every block."""
    checked = 0
    disagreements: list[dict[str, Any]] = []
    for block in blocks:
        report = check_timed_path_digests(block.observations)
        checked += report["cells_checked"]
        for d in report["disagreements"]:
            disagreements.append({"block_id": block.block_id, **d})
    return {
        "cells_checked": checked,
        "disagreement_count": len(disagreements),
        "ok": not disagreements,
        "disagreements": disagreements[:20],
    }


def _rows_for_arch(
    blocks: list[Block], meta: RegistryMeta, arch: str
) -> list[dict[str, Any]]:
    ns: dict[tuple[str, int], list[float]] = defaultdict(list)
    gb: dict[tuple[str, int], list[float]] = defaultdict(list)
    seen_blocks: dict[tuple[str, int], set[str]] = defaultdict(set)

    for block in blocks:
        for o in block.observations:
            if not o.get("ok"):
                continue
            key = (str(o["impl"]), int(o["size"]))
            ns[key].append(float(o["ns_per_hash"]))
            gb[key].append(float(o["gb_per_s"]))
            seen_blocks[key].add(block.block_id)

    rows: list[dict[str, Any]] = []
    for (impl, size), vals in sorted(ns.items(), key=lambda x: (x[0][1], x[0][0])):
        d = _dispersion(vals)
        gd = _dispersion(gb[(impl, size)])
        rows.append(
            {
                "impl": impl,
                "backend": meta.backends.get(impl),
                "arch": arch,
                "size": size,
                "blocks": len(seen_blocks[(impl, size)]),
                "n": d["n"],
                "ns_per_hash_median": d["median"],
                "ns_per_hash_mean": d["mean"],
                "ns_per_hash_p25": d["p25"],
                "ns_per_hash_p75": d["p75"],
                "ns_per_hash_min": d["min"],
                "ns_per_hash_max": d["max"],
                "ns_per_hash_cv": d["cv"],
                "gb_per_s_median": gd["median"],
                "gb_per_s_mean": gd["mean"],
            }
        )
    return rows


def _paired_ratios(
    blocks: list[Block], meta: RegistryMeta, arch: str
) -> list[dict[str, Any]]:
    """On-machine ratios: form T_impl/T_baseline inside each block, then aggregate.

    This is the quantity the atlas actually claims. Dividing one pooled median by
    another does not cancel host-to-host variation and cannot produce a win count.
    """
    per_block = [(b.block_id, b.medians()) for b in blocks]
    sizes = sorted({size for _, m in per_block for _, size in m})

    out: list[dict[str, Any]] = []
    for size in sizes:
        # Choose one baseline for the whole size so ratios stay comparable.
        available = {impl for _, m in per_block for impl, s in m if s == size}
        baseline = next((b for b in BASELINE_PREFERENCE if b in available), None)
        if baseline is None:
            continue

        by_impl: dict[str, list[float]] = defaultdict(list)
        wins: dict[str, int] = defaultdict(int)
        totals: dict[str, int] = defaultdict(int)
        for _bid, med in per_block:
            base_ns = med.get((baseline, size))
            if not base_ns:
                continue
            for impl in available:
                impl_ns = med.get((impl, size))
                if not impl_ns:
                    continue
                by_impl[impl].append(impl_ns / base_ns)
                totals[impl] += 1
                if impl_ns < base_ns:
                    wins[impl] += 1

        for impl, ratios in sorted(by_impl.items()):
            d = _dispersion(ratios)
            out.append(
                {
                    "size": size,
                    "impl": impl,
                    "backend": meta.backends.get(impl),
                    "arch": arch,
                    "baseline": baseline,
                    "ratio_ns_median": d["median"],
                    "ratio_ns_p25": d["p25"],
                    "ratio_ns_p75": d["p75"],
                    "ratio_ns_min": d["min"],
                    "ratio_ns_max": d["max"],
                    "blocks_faster_than_baseline": wins[impl],
                    "blocks_compared": totals[impl],
                }
            )
    return out


def _cost_models(
    blocks: list[Block], meta: RegistryMeta, arch: str
) -> list[dict[str, Any]]:
    """Split each implementation into fixed per-call cost and per-block cost.

    Fitted inside each block and then aggregated, for the same reason ratios are:
    a fit spanning hosts of different speeds would smear the very quantity it is
    trying to isolate.
    """
    per_impl: dict[str, list[Any]] = defaultdict(list)
    for block in blocks:
        by_impl_size: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
        for o in block.observations:
            if o.get("ok"):
                by_impl_size[str(o["impl"])][int(o["size"])].append(float(o["ns_per_hash"]))
        for impl, by_size in by_impl_size.items():
            model = fit_cost_model({s: statistics.median(v) for s, v in by_size.items()})
            if model is not None:
                per_impl[impl].append(model)

    rows: list[dict[str, Any]] = []
    for impl, models in sorted(per_impl.items()):
        agg = aggregate_models(models)
        if agg is None:
            continue
        rows.append({"impl": impl, "backend": meta.backends.get(impl), "arch": arch, **agg})
    rows.sort(key=lambda r: r["b_ns_per_block"]["median"])
    return rows


def _backend_clusters(
    rows: list[dict[str, Any]], meta: RegistryMeta, arch: str
) -> list[dict[str, Any]]:
    """Spread among *distinct front-ends sharing one backend*.

    Single-member "clusters" are omitted: a spread of exactly 1.0 over one member
    is not evidence of anything, and eleven such rows drown the two real ones.
    """
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(meta.backends.get(row["impl"], "unknown"), int(row["size"]))].append(row)

    clusters: list[dict[str, Any]] = []
    for (backend, size), members in sorted(grouped.items()):
        if len(members) < 2:
            continue
        members_sorted = sorted(members, key=lambda r: r["ns_per_hash_median"])
        ns_vals = [float(m["ns_per_hash_median"]) for m in members_sorted]
        clusters.append(
            {
                "backend": backend,
                "arch": arch,
                "size": size,
                "members": [m["impl"] for m in members_sorted],
                "count": len(members_sorted),
                "ns_per_hash_median_min": ns_vals[0],
                "ns_per_hash_median_max": ns_vals[-1],
                "ns_spread_ratio": ns_vals[-1] / ns_vals[0] if ns_vals[0] else None,
                "fastest_member": members_sorted[0]["impl"],
                "slowest_member": members_sorted[-1]["impl"],
            }
        )
    return clusters


def _leaderboards(
    rows: list[dict[str, Any]], meta: RegistryMeta, arch: str
) -> dict[str, Any]:
    """Rank each registry-declared board. Previously declared and never computed."""
    out: dict[str, Any] = {}
    for board, description in sorted(meta.board_descriptions.items()):
        eligible = {i for i, boards in meta.boards.items() if board in boards}
        by_size: dict[str, list[dict[str, Any]]] = {}
        for size in sorted({r["size"] for r in rows}):
            subset = [r for r in rows if r["size"] == size and r["impl"] in eligible]
            subset.sort(key=lambda r: r["ns_per_hash_median"])
            if subset:
                by_size[str(size)] = [
                    {
                        "rank": i + 1,
                        "impl": r["impl"],
                        "backend": r["backend"],
                        "ns_per_hash_median": r["ns_per_hash_median"],
                        "gb_per_s_median": r["gb_per_s_median"],
                    }
                    for i, r in enumerate(subset)
                ]
        out[board] = {"description": description, "arch": arch, "by_size": by_size}
    return out


def _arch_sensitivity(
    rows_by_arch: dict[str, list[dict[str, Any]]],
    sizes: list[int],
    block_counts: dict[str, int],
) -> list[dict[str, Any]]:
    """Find implementations whose standing depends on the architecture.

    For each size, every implementation's cross-arch ratio is compared against the
    cohort median ratio for the same pair of hosts. An implementation that loses a
    hardware datapath on one architecture — while its peers keep theirs — shows up
    here as a large departure, and its pooled median would be meaningless.
    """
    archs = [a for a in rows_by_arch if a != "unknown"]
    if len(archs) < 2:
        return []
    # Reference arch = the best-evidenced one, i.e. the most blocks. Row counts are
    # identical across strata whenever every implementation ran everywhere, so they
    # cannot break the tie.
    ref = max(archs, key=lambda a: (block_counts.get(a, 0), a))
    others = [a for a in archs if a != ref]

    out: list[dict[str, Any]] = []
    for other in others:
        ref_map = {(r["impl"], r["size"]): r for r in rows_by_arch[ref]}
        oth_map = {(r["impl"], r["size"]): r for r in rows_by_arch[other]}
        for size in sizes:
            pairs = {
                impl: (ref_map[(impl, size)], oth_map[(impl, size)])
                for impl, s in {(i, s) for i, s in ref_map}
                if s == size and (impl, size) in oth_map
            }
            if len(pairs) < 3:
                continue
            ratios = {
                impl: (o["ns_per_hash_median"] / r["ns_per_hash_median"])
                for impl, (r, o) in pairs.items()
                if r["ns_per_hash_median"]
            }
            cohort = statistics.median(ratios.values())
            for impl, ratio in sorted(ratios.items()):
                departure = ratio / cohort if cohort else None
                flagged = departure is not None and (
                    departure >= ARCH_SENSITIVITY_FACTOR
                    or departure <= 1 / ARCH_SENSITIVITY_FACTOR
                )
                if not flagged:
                    continue
                r, o = pairs[impl]
                out.append(
                    {
                        "impl": impl,
                        "size": size,
                        "reference_arch": ref,
                        "other_arch": other,
                        "reference_ns_median": r["ns_per_hash_median"],
                        "other_ns_median": o["ns_per_hash_median"],
                        "ratio_other_over_reference": ratio,
                        "cohort_ratio": cohort,
                        "departure_from_cohort": departure,
                        "direction": "slower" if departure and departure > 1 else "faster",
                    }
                )
    return out


def _claims(paired: list[dict[str, Any]], arch: str, cpu_models: list[str]) -> list[str]:
    """Render the exact claim form the atlas promises to make, from paired data.

    Only unanimous results are stated. The host population is described by how many
    CPU models it spans rather than by naming one of them, because a stratum that
    covers four models is not evidence about any single one.
    """
    if len(cpu_models) == 1:
        population = f"{arch} ({cpu_models[0]})"
    elif cpu_models:
        population = f"{arch} (across {len(cpu_models)} CPU models)"
    else:
        population = arch

    out: list[str] = []
    for row in paired:
        if row["impl"] == row["baseline"] or row["blocks_compared"] == 0:
            continue
        if row["blocks_faster_than_baseline"] != row["blocks_compared"]:
            continue
        out.append(
            f"On {population}, {row['impl']} beat {row['baseline']} at "
            f"{row['size']} B in {row['blocks_faster_than_baseline']}/"
            f"{row['blocks_compared']} blocks, median on-machine ratio "
            f"{row['ratio_ns_median']:.3f}."
        )
    return out


def summarize_files(paths: list[Path], *, root: Path | None = None) -> dict[str, Any]:
    """Aggregate campaign blocks, stratified by architecture.

    `root` locates registry/implementations.yaml, which supplies backends and
    leaderboard membership. It is auto-detected from the first result path when not
    given; result files stored outside the repository need it passed explicitly.
    """
    blocks = load_blocks(paths)
    if root is None and paths:
        root = _find_root(paths[0].resolve())
    meta = _load_registry_meta(root)

    by_arch: dict[str, list[Block]] = defaultdict(list)
    for b in blocks:
        by_arch[b.arch].append(b)

    rows_by_arch: dict[str, list[dict[str, Any]]] = {}
    strata: dict[str, Any] = {}
    all_sizes: set[int] = set()

    for arch, arch_blocks in sorted(by_arch.items()):
        rows = _rows_for_arch(arch_blocks, meta, arch)
        rows_by_arch[arch] = rows
        all_sizes.update(r["size"] for r in rows)

        rankings: dict[str, list[dict[str, Any]]] = {}
        for size in sorted({r["size"] for r in rows}):
            subset = sorted(
                (r for r in rows if r["size"] == size),
                key=lambda r: r["ns_per_hash_median"],
            )
            rankings[str(size)] = [
                {
                    "rank": i + 1,
                    "impl": r["impl"],
                    "backend": r["backend"],
                    "ns_per_hash_median": r["ns_per_hash_median"],
                    "ns_per_hash_cv": r["ns_per_hash_cv"],
                    "gb_per_s_median": r["gb_per_s_median"],
                }
                for i, r in enumerate(subset)
            ]

        paired = _paired_ratios(arch_blocks, meta, arch)
        cost_models = _cost_models(arch_blocks, meta, arch)
        audit = next((b.audit for b in arch_blocks if b.audit), None)
        model_counts: dict[str, int] = defaultdict(int)
        for b in arch_blocks:
            model_counts[b.cpu_model or "unknown"] += 1
        models = sorted(model_counts)
        strata[arch] = {
            "arch": arch,
            "block_count": len(arch_blocks),
            "block_ids": [b.block_id for b in arch_blocks],
            "cpu_models": models,
            "cpu_model_block_counts": dict(sorted(model_counts.items())),
            # One architecture is not one machine. When blocks land on several CPU
            # models, absolute ns/hash medians average over hardware that differs;
            # only the within-block paired ratios below are unaffected.
            "cpu_models_distinct": len(models),
            "absolute_medians_span_multiple_cpus": len(models) > 1,
            "sha256_hw": sorted({str(b.sha256_hw) for b in arch_blocks}),
            "openssl": sorted({b.openssl for b in arch_blocks if b.openssl}),
            "rows": rows,
            "rankings_by_size": rankings,
            "paired_ratios": paired,
            "cost_models": cost_models,
            "capability_audit": audit,
            # Two independent methods answering the same question: does this binary
            # contain a SHA-256 datapath, and does its measured per-block cost look
            # like one? Where they disagree, one of them is wrong.
            "audit_measurement_conflicts": (
                cross_check(audit, cost_models) if audit else []
            ),
            "backend_clusters": _backend_clusters(rows, meta, arch),
            "leaderboards": _leaderboards(rows, meta, arch),
            "claims": _claims(paired, arch, [m for m in models if m != "unknown"]),
        }

    return {
        "schema_version": SCHEMA_VERSION,
        # Backends and leaderboards come from the registry; without it the summary is
        # still valid but unlabelled, and saying so beats emitting silent nulls.
        "registry_root": str(root) if root else None,
        "registry_metadata_available": bool(meta.backends),
        "block_count": len(blocks),
        "blocks": [
            {
                "block_id": b.block_id,
                "arch": b.arch,
                "cpu_model": b.cpu_model,
                "sha256_hw": b.sha256_hw,
                "openssl": b.openssl,
                "observations": len(b.observations),
            }
            for b in blocks
        ],
        "arch_block_counts": {a: len(v) for a, v in sorted(by_arch.items())},
        "digest_agreement": _check_digest_agreement(blocks),
        "strata": strata,
        "arch_sensitivity": _arch_sensitivity(
            rows_by_arch,
            sorted(all_sizes),
            {a: len(v) for a, v in by_arch.items()},
        ),
    }


summarize = summarize_files


def render_markdown(summary: dict[str, Any], *, top: int = 8) -> str:
    """Compact human-readable digest for CI job summaries."""
    lines: list[str] = []
    lines.append(f"Blocks: {summary['block_count']} — {summary['arch_block_counts']}")
    da = summary["digest_agreement"]
    lines.append(
        f"Timed-path digest agreement: {'OK' if da['ok'] else 'FAILED'} "
        f"({da['cells_checked']} cells, {da['disagreement_count']} disagreements)"
    )
    for arch, s in summary["strata"].items():
        lines.append("")
        lines.append(f"### {arch} — {', '.join(s['cpu_models']) or 'unknown CPU'} ({s['block_count']} blocks)")
        for size in ("64", "1048576"):
            ranking = s["rankings_by_size"].get(size)
            if not ranking:
                continue
            lines.append(f"\n**{size} B** (ns/hash median, CV):\n")
            lines.append("| rank | impl | backend | ns/hash | CV | GB/s |")
            lines.append("|---|---|---|---|---|---|")
            for r in ranking[:top]:
                cv = f"{r['ns_per_hash_cv']:.3f}" if r["ns_per_hash_cv"] is not None else "—"
                lines.append(
                    f"| {r['rank']} | {r['impl']} | {r['backend']} | "
                    f"{r['ns_per_hash_median']:.1f} | {cv} | {r['gb_per_s_median']:.3f} |"
                )
    for arch, s in summary["strata"].items():
        models = s.get("cost_models") or []
        if not models:
            continue
        lines.append(f"\n### {arch} — fixed cost vs per-block cost\n")
        lines.append("| impl | a (ns/call) | b (ns/64B block) | asympt GB/s | hw path | steady state |")
        lines.append("|---|---|---|---|---|---|")
        audit = {
            e["id"]: e for e in ((s.get("capability_audit") or {}).get("implementations") or [])
        }
        for r in models:
            hw = audit.get(r["impl"], {}).get("hardware_sha256_present")
            hw_s = {True: "yes", False: "no", None: "?"}[hw]
            ss = "ok" if r["reached_steady_state"] else (
                f"NO ({r['steady_state_residual'] * 100:.0f}% @{r['steady_state_residual_size']}B)"
            )
            lines.append(
                f"| {r['impl']} | {r['a_ns_fixed']['median']:.0f} | "
                f"{r['b_ns_per_block']['median']:.2f} | "
                f"{r['asymptotic_gb_per_s']:.3f} | {hw_s} | {ss} |"
            )
        conflicts = s.get("audit_measurement_conflicts") or []
        if conflicts:
            lines.append(
                f"\n{len(conflicts)} audit/measurement conflict(s): "
                + ", ".join(c["impl"] for c in conflicts)
            )

    sens = summary.get("arch_sensitivity") or []
    if sens:
        lines.append("\n### Architecture-sensitive implementations\n")
        lines.append("| impl | size | ref arch ns | other arch ns | ratio | vs cohort |")
        lines.append("|---|---|---|---|---|---|")
        for e in sens:
            if e["size"] != 1_048_576:
                continue
            lines.append(
                f"| {e['impl']} | {e['size']} | {e['reference_ns_median']:.0f} | "
                f"{e['other_ns_median']:.0f} | {e['ratio_other_over_reference']:.2f}x | "
                f"{e['departure_from_cohort']:.2f}x |"
            )
    return "\n".join(lines)
