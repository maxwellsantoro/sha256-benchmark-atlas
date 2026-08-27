from __future__ import annotations

import json
from pathlib import Path

import yaml

from sha256_benchmark_atlas.analysis import summarize_files


def _write_bench(path: Path, observations: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"observations": observations}))
    return path


def _obs(impl: str, size: int, ns_per_hash: float, gb_per_s: float = 1.0, ok: bool = True) -> dict:
    obs = {"impl": impl, "size": size, "ok": ok}
    if ok:
        obs["ns_per_hash"] = ns_per_hash
        obs["gb_per_s"] = gb_per_s
    return obs


def test_summarize_aggregates_medians_across_blocks(tmp_path: Path) -> None:
    block1 = _write_bench(
        tmp_path / "r1" / "bench.json",
        [_obs("impl-a", 64, 100.0), _obs("impl-b", 64, 50.0)],
    )
    block2 = _write_bench(
        tmp_path / "r2" / "bench.json",
        [_obs("impl-a", 64, 200.0), _obs("impl-b", 64, 60.0)],
    )

    summary = summarize_files([block1, block2])

    assert summary["blocks"] == 2
    rows_by_impl = {r["impl"]: r for r in summary["rows"]}
    assert rows_by_impl["impl-a"]["n"] == 2
    assert rows_by_impl["impl-a"]["ns_per_hash_median"] == 150.0
    assert rows_by_impl["impl-a"]["ns_per_hash_mean"] == 150.0
    assert rows_by_impl["impl-b"]["ns_per_hash_median"] == 55.0


def test_summarize_ignores_failed_and_unmarked_observations(tmp_path: Path) -> None:
    block = _write_bench(
        tmp_path / "r1" / "bench.json",
        [
            _obs("impl-a", 64, 100.0),
            _obs("impl-a", 64, 999.0, ok=False),
            {"impl": "impl-a", "size": 64},  # no "ok" key at all
        ],
    )

    summary = summarize_files([block])

    rows = [r for r in summary["rows"] if r["impl"] == "impl-a"]
    assert len(rows) == 1
    assert rows[0]["n"] == 1
    assert rows[0]["ns_per_hash_median"] == 100.0


def test_rankings_by_size_sorts_fastest_first(tmp_path: Path) -> None:
    block = _write_bench(
        tmp_path / "r1" / "bench.json",
        [_obs("slow-impl", 64, 500.0), _obs("fast-impl", 64, 10.0)],
    )

    summary = summarize_files([block])

    ranking = summary["rankings_by_size"]["64"]
    assert [r["impl"] for r in ranking] == ["fast-impl", "slow-impl"]
    assert [r["rank"] for r in ranking] == [1, 2]


def test_ratios_vs_baseline_uses_first_available_baseline(tmp_path: Path) -> None:
    block = _write_bench(
        tmp_path / "r1" / "bench.json",
        [_obs("c-openssl", 64, 100.0), _obs("some-impl", 64, 250.0)],
    )

    summary = summarize_files([block])

    ratios = {r["impl"]: r for r in summary["ratios_vs_baseline"] if r["size"] == 64}
    assert ratios["c-openssl"]["baseline"] == "c-openssl"
    assert ratios["c-openssl"]["ratio_ns"] == 1.0
    assert ratios["some-impl"]["ratio_ns"] == 2.5


def test_ratios_vs_baseline_absent_baseline_yields_no_ratios(tmp_path: Path) -> None:
    block = _write_bench(
        tmp_path / "r1" / "bench.json",
        [_obs("impl-x", 64, 100.0), _obs("impl-y", 64, 250.0)],
    )

    summary = summarize_files([block])

    assert summary["ratios_vs_baseline"] == []


def test_backend_attribution_from_registry(tmp_path: Path) -> None:
    (tmp_path / "registry").mkdir()
    (tmp_path / "registry" / "implementations.yaml").write_text(
        yaml.safe_dump(
            {
                "implementations": [
                    {"id": "impl-a", "backend": "openssl", "status": "admitted", "binary": "a"},
                    {"id": "impl-b", "backend": "openssl", "status": "admitted", "binary": "b"},
                ]
            }
        )
    )
    block = _write_bench(
        tmp_path / "results" / "r1" / "bench.json",
        [_obs("impl-a", 1_048_576, 100.0), _obs("impl-b", 1_048_576, 110.0)],
    )

    summary = summarize_files([block])

    rows_by_impl = {r["impl"]: r for r in summary["rows"]}
    assert rows_by_impl["impl-a"]["backend"] == "openssl"
    assert rows_by_impl["impl-b"]["backend"] == "openssl"

    clusters = {c["backend"]: c for c in summary["backend_clusters_1mib"]}
    assert clusters["openssl"]["count"] == 2
    assert set(clusters["openssl"]["members"]) == {"impl-a", "impl-b"}
    assert clusters["openssl"]["fastest_member"] == "impl-a"


def test_backend_unknown_without_registry(tmp_path: Path) -> None:
    block = _write_bench(
        tmp_path / "results" / "r1" / "bench.json",
        [_obs("mystery-impl", 1_048_576, 100.0)],
    )

    summary = summarize_files([block])

    row = summary["rows"][0]
    assert row["backend"] is None
    cluster = summary["backend_clusters_1mib"][0]
    assert cluster["backend"] == "unknown"
