"""Persist raw per-block observations as the campaign's evidence archive.

A summary is a derived artifact. Publishing only medians means the published claim
cannot be re-derived, re-stratified, or challenged once the 30-day CI artifact
retention expires. Gzipped, the full observation set for a 12-block campaign is
well under a megabyte, so there is no reason not to keep it in the repository.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

from .fingerprint import cpu_facts_from_fingerprint

# The registry is committed separately and identically in every block; keeping a
# copy per block roughly doubles the archive for no added evidence.
DROPPED_BENCH_KEYS = ("implementations",)

CPUINFO_KEEP_BLOCKS = 1


def _write_gz(path: Path, payload: dict[str, Any]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    with gzip.open(path, "wb", compresslevel=9) as f:
        f.write(raw)
    return path.stat().st_size


def _read_json(path: Path) -> dict[str, Any]:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)
    return json.loads(path.read_text(encoding="utf-8"))


def _trim_fingerprint(fp: dict[str, Any]) -> dict[str, Any]:
    """Normalise a fingerprint, then drop only genuinely redundant bulk.

    The CPU facts are re-derived first, so a fingerprint written before the aarch64
    detection fix is archived with a correct model name and SHA-256 support rather
    than the empty string and `false` it originally recorded. `lscpu` is retained:
    it is the authoritative CPU description and costs almost nothing compressed.
    Only the per-core repetition of /proc/cpuinfo is discarded — on a 96-core host
    that is ~500 KiB of near-identical text carrying no extra information.
    """
    out = dict(fp)
    cpu = dict(out.get("cpu") or {})

    facts = cpu_facts_from_fingerprint(fp)
    cpu["arch"] = facts["arch"]
    cpu["model_name"] = facts["model_name"]
    cpu["features"] = facts["features"]
    cpu["sha256_hw"] = facts["sha256_hw"]
    cpu["sha256_hw_evidence"] = facts["sha256_hw_evidence"]
    cpu["normalized_by_archive"] = True

    cpuinfo = cpu.pop("proc_cpuinfo", None)
    if cpuinfo and "proc_cpuinfo_first_block" not in cpu:
        blocks = cpuinfo.split("\n\n")
        cpu["proc_cpuinfo_first_block"] = "\n\n".join(blocks[:CPUINFO_KEEP_BLOCKS])
        cpu["processor_count"] = sum(1 for b in blocks if b.strip().startswith("processor"))

    out["cpu"] = cpu
    memory = dict(out.get("memory") or {})
    if isinstance(memory.get("meminfo"), str):
        memory["meminfo"] = "\n".join(memory["meminfo"].splitlines()[:8])
    out["memory"] = memory
    return out


def archive_blocks(block_dirs: list[Path], out_dir: Path) -> dict[str, Any]:
    """Write one compact gzipped record per block into `out_dir`."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[dict[str, Any]] = []
    total = 0

    for block_dir in sorted(block_dirs):
        bench_path = next(
            (p for p in (block_dir / "bench.json", block_dir / "bench.json.gz") if p.is_file()),
            None,
        )
        if bench_path is None:
            continue

        bench = _read_json(bench_path)
        for key in DROPPED_BENCH_KEYS:
            bench.pop(key, None)

        block_id = block_dir.name
        dest = out_dir / block_id
        size = _write_gz(dest / "bench.json.gz", bench)
        total += size

        fp_path = next(
            (
                p
                for p in (block_dir / "fingerprint.json", block_dir / "fingerprint.json.gz")
                if p.is_file()
            ),
            None,
        )
        if fp_path is not None:
            total += _write_gz(
                dest / "fingerprint.json.gz", _trim_fingerprint(_read_json(fp_path))
            )

        written.append(
            {
                "block_id": block_id,
                "observations": len(bench.get("observations", [])),
                "bytes": size,
            }
        )

    manifest = {
        "blocks": written,
        "block_count": len(written),
        "total_bytes": total,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest
