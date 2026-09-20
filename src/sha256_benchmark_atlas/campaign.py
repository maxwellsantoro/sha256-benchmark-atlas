from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from .bench import bench_result_success, run_interleaved_bench
from .build import build_all
from .capability_audit import audit_all
from .correctness import run_correctness
from .fingerprint import write_fingerprint
from .registry import load_registry


def run_campaign(
    root: Path,
    *,
    ids: list[str] | None = None,
    reps: int = 5,
    seed: int = 1,
    cases: int = 10_000,
    max_size: int = 1_048_576,
    skip_million: bool = False,
    output_dir: Path | None = None,
    shard: int = 0,
    shards: int = 1,
) -> int:
    if type(reps) is not int or reps <= 0:
        raise ValueError("reps must be a positive integer")
    if type(max_size) is not int or max_size < 0:
        raise ValueError("max_size must be a nonnegative integer")
    if type(cases) is not int or cases < 0:
        raise ValueError("cases must be a nonnegative integer")
    if ids is not None and not ids:
        raise ValueError("ids selection must not be empty")
    reg = load_registry(root)
    impls = reg.by_id(ids)
    if not impls:
        raise ValueError("implementation selection must not be empty")
    if any(type(size) is not int or size < 0 for size in reg.message_sizes):
        raise ValueError("registered sizes must contain only nonnegative integers")
    if not [size for size in reg.message_sizes if size <= max_size]:
        raise ValueError("no registered message sizes are within max_size")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = output_dir or (root / "results" / f"campaign-{stamp}-shard{shard}")
    out.mkdir(parents=True, exist_ok=True)

    # Shard only affects bench seed / output labeling; all shards run full admitted set
    # so each runner is an independent experimental block (per design doc).
    effective_seed = seed + shard * 1_000_003

    print(f"== fingerprint → {out / 'fingerprint.json'}")
    write_fingerprint(out / "fingerprint.json")

    print("== build")
    builds = build_all(root, ids=ids)
    build_report = [{"id": b.id, "ok": b.ok, "detail": b.detail} for b in builds]
    (out / "build.json").write_text(json.dumps(build_report, indent=2) + "\n", encoding="utf-8")
    for b in builds:
        print(f"  [{'ok' if b.ok else 'FAIL'}] {b.id}: {b.detail}")
    built_ids = [b.id for b in builds if b.ok]
    if not built_ids:
        print("No implementations built successfully.")
        return 1
    if ids:
        built_ids = [i for i in built_ids if i in ids]

    print("== static capability audit")
    audit = audit_all(root, reg.by_id(built_ids))
    (out / "audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(
        f"  {audit['with_hardware_path']}/{audit['audited']} audited implementations ship a "
        f"hardware SHA-256 path on {audit['arch']} ({audit['skipped']} not auditable)"
    )

    print("== correctness")
    correctness = run_correctness(
        root,
        ids=built_ids,
        prng_cases=cases,
        skip_million=skip_million,
    )
    (out / "correctness.json").write_text(
        json.dumps(correctness, indent=2) + "\n", encoding="utf-8"
    )
    for r in correctness["implementations"]:
        print(
            f"  [{'ok' if r['ok'] else 'FAIL'}] {r['id']}: checked={r['checked']} failed={r['failed']}"
        )
    admitted = [r["id"] for r in correctness["implementations"] if r["ok"]]
    if not admitted:
        print("Correctness gate admitted nobody; skipping bench.")
        return 1

    print("== interleaved bench")
    bench = run_interleaved_bench(
        root,
        ids=admitted,
        reps=reps,
        seed=effective_seed,
        max_size=max_size,
        output=out / "bench.json",
    )
    meta = {
        "shard": shard,
        "shards": shards,
        "seed": effective_seed,
        "output_dir": str(out),
        "admitted": admitted,
        "observations": len(bench["observations"]),
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out}")
    print(json.dumps(meta, indent=2))
    return 0 if bench_result_success(bench) else 1
