from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .bench import run_interleaved_bench
from .build import build_all
from .correctness import run_correctness
from .fingerprint import write_fingerprint


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
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
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

    print("== correctness")
    correctness = run_correctness(
        root,
        ids=built_ids,
        prng_cases=cases,
        skip_million=skip_million,
    )
    (out / "correctness.json").write_text(json.dumps(correctness, indent=2) + "\n", encoding="utf-8")
    for r in correctness["implementations"]:
        print(f"  [{'ok' if r['ok'] else 'FAIL'}] {r['id']}: checked={r['checked']} failed={r['failed']}")
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
    return 0
