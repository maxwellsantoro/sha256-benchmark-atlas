from __future__ import annotations

import gzip
import json
from pathlib import Path

from sha256_benchmark_atlas.analysis import summarize_files
from sha256_benchmark_atlas.archive import archive_blocks

ARM_CPUINFO = """processor\t: 0
BogoMIPS\t: 2000.00
Features\t: fp asimd aes pmull sha1 sha2 crc32
CPU implementer\t: 0x41
CPU part\t: 0xd49

processor\t: 1
BogoMIPS\t: 2000.00
Features\t: fp asimd aes pmull sha1 sha2 crc32
CPU implementer\t: 0x41
CPU part\t: 0xd49
"""


def _block(root: Path, name: str, *, legacy_fingerprint: bool = False) -> Path:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "bench.json").write_text(
        json.dumps(
            {
                "host": {"arch": "aarch64"},
                "implementations": [{"id": "impl-a", "notes": "x" * 5000}],
                "observations": [
                    {
                        "impl": "impl-a",
                        "size": 64,
                        "rep": 0,
                        "ok": True,
                        "ns_per_hash": 100.0,
                        "gb_per_s": 0.64,
                        "digest": "a" * 64,
                    }
                ],
            }
        )
    )
    if legacy_fingerprint:
        (d / "fingerprint.json").write_text(
            json.dumps(
                {
                    "platform": {"machine": "aarch64"},
                    "tools": {"openssl": "OpenSSL 3.0.13"},
                    "cpu": {
                        "proc_cpuinfo": ARM_CPUINFO,
                        "model_name": "",
                        "sha_ni": False,
                    },
                    "memory": {"meminfo": "\n".join(f"line {i}" for i in range(50))},
                }
            )
        )
    return d


def test_archive_writes_one_gzipped_record_per_block(tmp_path: Path) -> None:
    blocks = [_block(tmp_path / "raw", f"shard-{i}") for i in range(3)]

    manifest = archive_blocks(blocks, tmp_path / "out")

    assert manifest["block_count"] == 3
    for i in range(3):
        assert (tmp_path / "out" / f"shard-{i}" / "bench.json.gz").is_file()
    assert json.loads((tmp_path / "out" / "manifest.json").read_text())["block_count"] == 3


def test_archive_preserves_every_observation(tmp_path: Path) -> None:
    block = _block(tmp_path / "raw", "shard-0")

    archive_blocks([block], tmp_path / "out")

    with gzip.open(tmp_path / "out" / "shard-0" / "bench.json.gz", "rt") as f:
        restored = json.load(f)
    original = json.loads((block / "bench.json").read_text())
    assert restored["observations"] == original["observations"]


def test_archive_drops_the_per_block_registry_copy(tmp_path: Path) -> None:
    """The registry is committed once; a copy in each block is pure duplication."""
    block = _block(tmp_path / "raw", "shard-0")

    archive_blocks([block], tmp_path / "out")

    with gzip.open(tmp_path / "out" / "shard-0" / "bench.json.gz", "rt") as f:
        assert "implementations" not in json.load(f)


def test_archive_normalizes_legacy_arm_fingerprints(tmp_path: Path) -> None:
    """A pre-fix fingerprint is archived with correct CPU facts, not the buggy ones."""
    block = _block(tmp_path / "raw", "shard-0", legacy_fingerprint=True)

    archive_blocks([block], tmp_path / "out")

    with gzip.open(tmp_path / "out" / "shard-0" / "fingerprint.json.gz", "rt") as f:
        fp = json.load(f)

    assert fp["cpu"]["model_name"] == "Neoverse-N2"
    assert fp["cpu"]["sha256_hw"] is True
    assert fp["cpu"]["normalized_by_archive"] is True


def test_archive_keeps_one_cpuinfo_block_and_the_core_count(tmp_path: Path) -> None:
    block = _block(tmp_path / "raw", "shard-0", legacy_fingerprint=True)

    archive_blocks([block], tmp_path / "out")

    with gzip.open(tmp_path / "out" / "shard-0" / "fingerprint.json.gz", "rt") as f:
        cpu = json.load(f)["cpu"]

    assert "proc_cpuinfo" not in cpu
    assert cpu["proc_cpuinfo_first_block"].count("processor") == 1
    assert cpu["processor_count"] == 2


def test_archive_output_is_readable_by_the_summarizer(tmp_path: Path) -> None:
    """The committed archive must be the thing the summary is derived from."""
    blocks = [_block(tmp_path / "raw", f"shard-{i}", legacy_fingerprint=True) for i in range(2)]
    archive_blocks(blocks, tmp_path / "out")

    summary = summarize_files(sorted((tmp_path / "out").glob("*/bench.json.gz")))

    assert summary["block_count"] == 2
    assert summary["arch_block_counts"] == {"aarch64": 2}
    assert summary["strata"]["aarch64"]["cpu_models"] == ["Neoverse-N2"]


def test_archive_skips_directories_without_a_bench_file(tmp_path: Path) -> None:
    good = _block(tmp_path / "raw", "shard-0")
    empty = tmp_path / "raw" / "not-a-block"
    empty.mkdir(parents=True)

    manifest = archive_blocks([good, empty], tmp_path / "out")

    assert manifest["block_count"] == 1
