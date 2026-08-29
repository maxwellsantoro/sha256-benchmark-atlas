from __future__ import annotations

import json
from pathlib import Path

import yaml

from sha256_benchmark_atlas.analysis import check_timed_path_digests, summarize_files

DIGEST_A = "a" * 64
DIGEST_B = "b" * 64


def _write_bench(
    path: Path,
    observations: list[dict],
    *,
    arch: str = "x86_64",
    cpu_model: str = "Test CPU",
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "host": {"arch": arch, "cpu_model": cpu_model, "sha256_hw": True},
                "observations": observations,
            }
        )
    )
    return path


def _obs(
    impl: str,
    size: int,
    ns_per_hash: float,
    gb_per_s: float = 1.0,
    ok: bool = True,
    rep: int = 0,
    digest: str | None = None,
) -> dict:
    obs = {"impl": impl, "size": size, "ok": ok, "rep": rep}
    if ok:
        obs["ns_per_hash"] = ns_per_hash
        obs["gb_per_s"] = gb_per_s
        if digest is not None:
            obs["digest"] = digest
    return obs


def _registry(tmp_path: Path, implementations: list[dict]) -> None:
    (tmp_path / "registry").mkdir(parents=True, exist_ok=True)
    (tmp_path / "registry" / "implementations.yaml").write_text(
        yaml.safe_dump(
            {
                "leaderboards": [
                    {"id": "production", "description": "prod"},
                    {"id": "portable", "description": "portable"},
                ],
                "implementations": implementations,
            }
        )
    )


# --- stratification -------------------------------------------------------


def test_blocks_are_stratified_by_architecture(tmp_path: Path) -> None:
    x64 = _write_bench(
        tmp_path / "r1" / "bench.json", [_obs("impl-a", 64, 100.0)], arch="x86_64"
    )
    arm = _write_bench(
        tmp_path / "r2" / "bench.json", [_obs("impl-a", 64, 400.0)], arch="aarch64"
    )

    summary = summarize_files([x64, arm])

    assert summary["arch_block_counts"] == {"aarch64": 1, "x86_64": 1}
    strata = summary["strata"]
    assert strata["x86_64"]["rows"][0]["ns_per_hash_median"] == 100.0
    assert strata["aarch64"]["rows"][0]["ns_per_hash_median"] == 400.0


def test_architectures_are_never_pooled_into_one_median(tmp_path: Path) -> None:
    """The old behaviour produced 250.0 here — a number describing neither host."""
    x64 = _write_bench(
        tmp_path / "r1" / "bench.json", [_obs("impl-a", 64, 100.0)], arch="x86_64"
    )
    arm = _write_bench(
        tmp_path / "r2" / "bench.json", [_obs("impl-a", 64, 400.0)], arch="aarch64"
    )

    summary = summarize_files([x64, arm])

    medians = {
        arch: s["rows"][0]["ns_per_hash_median"] for arch, s in summary["strata"].items()
    }
    assert 250.0 not in medians.values()
    assert sorted(medians.values()) == [100.0, 400.0]


def test_arch_resolved_from_directory_name_when_unrecorded(tmp_path: Path) -> None:
    path = tmp_path / "results-shard-10-ubuntu-24.04-arm" / "bench.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"observations": [_obs("impl-a", 64, 100.0)]}))

    summary = summarize_files([path])

    assert "aarch64" in summary["strata"]


# --- aggregation and dispersion ------------------------------------------


def test_medians_aggregate_across_blocks_of_the_same_arch(tmp_path: Path) -> None:
    b1 = _write_bench(
        tmp_path / "r1" / "bench.json",
        [_obs("impl-a", 64, 100.0), _obs("impl-b", 64, 50.0)],
    )
    b2 = _write_bench(
        tmp_path / "r2" / "bench.json",
        [_obs("impl-a", 64, 200.0), _obs("impl-b", 64, 60.0)],
    )

    summary = summarize_files([b1, b2])

    assert summary["block_count"] == 2
    rows = {r["impl"]: r for r in summary["strata"]["x86_64"]["rows"]}
    assert rows["impl-a"]["n"] == 2
    assert rows["impl-a"]["blocks"] == 2
    assert rows["impl-a"]["ns_per_hash_median"] == 150.0
    assert rows["impl-b"]["ns_per_hash_median"] == 55.0


def test_rows_carry_dispersion_not_just_central_tendency(tmp_path: Path) -> None:
    block = _write_bench(
        tmp_path / "r1" / "bench.json",
        [_obs("impl-a", 64, v, rep=i) for i, v in enumerate([90.0, 100.0, 110.0, 300.0])],
    )

    row = summarize_files([block])["strata"]["x86_64"]["rows"][0]

    assert row["ns_per_hash_min"] == 90.0
    assert row["ns_per_hash_max"] == 300.0
    assert row["ns_per_hash_p25"] < row["ns_per_hash_median"] < row["ns_per_hash_p75"]
    assert row["ns_per_hash_cv"] > 0


def test_failed_and_unmarked_observations_are_ignored(tmp_path: Path) -> None:
    block = _write_bench(
        tmp_path / "r1" / "bench.json",
        [
            _obs("impl-a", 64, 100.0),
            _obs("impl-a", 64, 999.0, ok=False),
            {"impl": "impl-a", "size": 64, "rep": 0},
        ],
    )

    rows = summarize_files([block])["strata"]["x86_64"]["rows"]
    assert len(rows) == 1
    assert rows[0]["n"] == 1
    assert rows[0]["ns_per_hash_median"] == 100.0


def test_rankings_sort_fastest_first(tmp_path: Path) -> None:
    block = _write_bench(
        tmp_path / "r1" / "bench.json",
        [_obs("slow-impl", 64, 500.0), _obs("fast-impl", 64, 10.0)],
    )

    ranking = summarize_files([block])["strata"]["x86_64"]["rankings_by_size"]["64"]
    assert [r["impl"] for r in ranking] == ["fast-impl", "slow-impl"]
    assert [r["rank"] for r in ranking] == [1, 2]


# --- paired on-machine ratios --------------------------------------------


def test_paired_ratios_are_formed_within_each_block(tmp_path: Path) -> None:
    """Two hosts of very different speed, but a stable 2x on-machine ratio."""
    b1 = _write_bench(
        tmp_path / "r1" / "bench.json",
        [_obs("c-openssl", 64, 100.0), _obs("impl-x", 64, 200.0)],
    )
    b2 = _write_bench(
        tmp_path / "r2" / "bench.json",
        [_obs("c-openssl", 64, 1000.0), _obs("impl-x", 64, 2000.0)],
    )

    paired = summarize_files([b1, b2])["strata"]["x86_64"]["paired_ratios"]
    ratios = {r["impl"]: r for r in paired}

    assert ratios["impl-x"]["ratio_ns_median"] == 2.0
    assert ratios["impl-x"]["ratio_ns_min"] == 2.0
    assert ratios["impl-x"]["ratio_ns_max"] == 2.0
    assert ratios["impl-x"]["blocks_compared"] == 2


def test_win_counts_are_per_block(tmp_path: Path) -> None:
    b1 = _write_bench(
        tmp_path / "r1" / "bench.json",
        [_obs("c-openssl", 64, 100.0), _obs("impl-x", 64, 99.0)],
    )
    b2 = _write_bench(
        tmp_path / "r2" / "bench.json",
        [_obs("c-openssl", 64, 100.0), _obs("impl-x", 64, 101.0)],
    )

    paired = summarize_files([b1, b2])["strata"]["x86_64"]["paired_ratios"]
    row = next(r for r in paired if r["impl"] == "impl-x")

    assert row["blocks_faster_than_baseline"] == 1
    assert row["blocks_compared"] == 2


def test_paired_ratio_beats_pooled_ratio_under_host_variation(tmp_path: Path) -> None:
    """A slow host can invert a pooled comparison; pairing is immune.

    impl-x is 10% faster than the baseline on every host, but only ran alongside a
    fast baseline once. Comparing pooled medians reverses the finding.
    """
    blocks = [
        _write_bench(
            tmp_path / "r1" / "bench.json",
            [_obs("c-openssl", 64, 100.0), _obs("impl-x", 64, 90.0)],
        ),
        _write_bench(
            tmp_path / "r2" / "bench.json",
            [_obs("c-openssl", 64, 1000.0), _obs("impl-x", 64, 900.0)],
        ),
        _write_bench(
            tmp_path / "r3" / "bench.json",
            [_obs("c-openssl", 64, 1000.0), _obs("impl-x", 64, 900.0)],
        ),
    ]

    summary = summarize_files(blocks)
    row = next(
        r for r in summary["strata"]["x86_64"]["paired_ratios"] if r["impl"] == "impl-x"
    )

    assert row["ratio_ns_median"] == 0.9
    assert row["blocks_faster_than_baseline"] == 3
    assert row["blocks_compared"] == 3


def test_no_paired_ratios_without_a_known_baseline(tmp_path: Path) -> None:
    block = _write_bench(
        tmp_path / "r1" / "bench.json",
        [_obs("impl-x", 64, 100.0), _obs("impl-y", 64, 250.0)],
    )

    assert summarize_files([block])["strata"]["x86_64"]["paired_ratios"] == []


def test_claims_are_emitted_only_for_unanimous_results(tmp_path: Path) -> None:
    b1 = _write_bench(
        tmp_path / "r1" / "bench.json",
        [_obs("c-openssl", 64, 100.0), _obs("won", 64, 50.0), _obs("split", 64, 50.0)],
    )
    b2 = _write_bench(
        tmp_path / "r2" / "bench.json",
        [_obs("c-openssl", 64, 100.0), _obs("won", 64, 50.0), _obs("split", 64, 150.0)],
    )

    claims = summarize_files([b1, b2])["strata"]["x86_64"]["claims"]
    joined = " ".join(claims)

    assert "won beat c-openssl at 64 B in 2/2 blocks" in joined
    assert "split" not in joined


# --- timed-path digest validation ----------------------------------------


def test_digest_agreement_passes_when_all_impls_match(tmp_path: Path) -> None:
    block = _write_bench(
        tmp_path / "r1" / "bench.json",
        [
            _obs("impl-a", 64, 100.0, digest=DIGEST_A),
            _obs("impl-b", 64, 110.0, digest=DIGEST_A),
        ],
    )

    agreement = summarize_files([block])["digest_agreement"]
    assert agreement["ok"] is True
    assert agreement["cells_checked"] == 1


def test_digest_disagreement_is_detected_and_attributed(tmp_path: Path) -> None:
    block = _write_bench(
        tmp_path / "r1" / "bench.json",
        [
            _obs("good-1", 64, 100.0, digest=DIGEST_A),
            _obs("good-2", 64, 100.0, digest=DIGEST_A),
            _obs("liar", 64, 1.0, digest=DIGEST_B),
        ],
    )

    agreement = summarize_files([block])["digest_agreement"]
    assert agreement["ok"] is False
    assert agreement["disagreement_count"] == 1
    assert list(agreement["disagreements"][0]["dissenting"]) == ["liar"]


def test_digest_check_ignores_cells_with_a_single_implementation() -> None:
    report = check_timed_path_digests([_obs("only", 64, 100.0, digest=DIGEST_A)])
    assert report["cells_checked"] == 0
    assert report["ok"] is True


def test_digest_check_separates_cells_by_size_and_rep() -> None:
    report = check_timed_path_digests(
        [
            _obs("a", 64, 1.0, rep=0, digest=DIGEST_A),
            _obs("b", 64, 1.0, rep=0, digest=DIGEST_A),
            _obs("a", 64, 1.0, rep=1, digest=DIGEST_B),
            _obs("b", 64, 1.0, rep=1, digest=DIGEST_B),
        ]
    )
    assert report["cells_checked"] == 2
    assert report["ok"] is True


# --- backend clusters ----------------------------------------------------


def test_backend_clusters_require_at_least_two_members(tmp_path: Path) -> None:
    _registry(
        tmp_path,
        [
            {"id": "impl-a", "backend": "openssl", "status": "admitted", "binary": "a"},
            {"id": "impl-b", "backend": "openssl", "status": "admitted", "binary": "b"},
            {"id": "lonely", "backend": "solo", "status": "admitted", "binary": "c"},
        ],
    )
    block = _write_bench(
        tmp_path / "results" / "r1" / "bench.json",
        [
            _obs("impl-a", 1_048_576, 100.0),
            _obs("impl-b", 1_048_576, 110.0),
            _obs("lonely", 1_048_576, 120.0),
        ],
    )

    clusters = summarize_files([block])["strata"]["x86_64"]["backend_clusters"]
    by_backend = {c["backend"]: c for c in clusters}

    assert "solo" not in by_backend
    assert by_backend["openssl"]["count"] == 2
    assert by_backend["openssl"]["fastest_member"] == "impl-a"
    assert by_backend["openssl"]["slowest_member"] == "impl-b"


def test_backend_attribution_from_registry(tmp_path: Path) -> None:
    _registry(
        tmp_path,
        [{"id": "impl-a", "backend": "openssl", "status": "admitted", "binary": "a"}],
    )
    block = _write_bench(
        tmp_path / "results" / "r1" / "bench.json", [_obs("impl-a", 1_048_576, 100.0)]
    )

    summary = summarize_files([block])
    assert summary["registry_metadata_available"] is True
    assert summary["strata"]["x86_64"]["rows"][0]["backend"] == "openssl"


def test_missing_registry_is_reported_not_silently_swallowed(tmp_path: Path) -> None:
    block = _write_bench(
        tmp_path / "r1" / "bench.json", [_obs("mystery", 1_048_576, 100.0)]
    )

    summary = summarize_files([block], root=None)
    assert summary["registry_metadata_available"] is False
    assert summary["strata"]["x86_64"]["rows"][0]["backend"] is None


# --- leaderboards --------------------------------------------------------


def test_leaderboards_are_computed_from_registry_membership(tmp_path: Path) -> None:
    _registry(
        tmp_path,
        [
            {
                "id": "fast-prod",
                "backend": "openssl",
                "status": "admitted",
                "binary": "a",
                "leaderboards": ["production"],
            },
            {
                "id": "slow-portable",
                "backend": "ref",
                "status": "admitted",
                "binary": "b",
                "leaderboards": ["portable"],
            },
        ],
    )
    block = _write_bench(
        tmp_path / "results" / "r1" / "bench.json",
        [_obs("fast-prod", 64, 10.0), _obs("slow-portable", 64, 900.0)],
    )

    boards = summarize_files([block])["strata"]["x86_64"]["leaderboards"]

    assert [r["impl"] for r in boards["production"]["by_size"]["64"]] == ["fast-prod"]
    assert [r["impl"] for r in boards["portable"]["by_size"]["64"]] == ["slow-portable"]


# --- architecture sensitivity --------------------------------------------


def test_arch_sensitivity_flags_an_implementation_that_loses_acceleration(
    tmp_path: Path,
) -> None:
    """Peers are 1x across hosts; the outlier is 4x slower on the second arch."""
    peers = [("peer-1", 100.0), ("peer-2", 105.0), ("peer-3", 110.0)]
    x64 = _write_bench(
        tmp_path / "r1" / "bench.json",
        [_obs(i, 1_048_576, ns) for i, ns in peers] + [_obs("outlier", 1_048_576, 100.0)],
        arch="x86_64",
    )
    arm = _write_bench(
        tmp_path / "r2" / "bench.json",
        [_obs(i, 1_048_576, ns) for i, ns in peers] + [_obs("outlier", 1_048_576, 400.0)],
        arch="aarch64",
    )

    sensitivity = summarize_files([x64, arm])["arch_sensitivity"]
    flagged = {e["impl"] for e in sensitivity}

    assert flagged == {"outlier"}
    entry = next(e for e in sensitivity if e["impl"] == "outlier")
    assert entry["ratio_other_over_reference"] == 4.0
    assert entry["direction"] == "slower"


def test_arch_sensitivity_is_empty_for_a_single_architecture(tmp_path: Path) -> None:
    block = _write_bench(
        tmp_path / "r1" / "bench.json",
        [_obs("impl-a", 1_048_576, 100.0), _obs("impl-b", 1_048_576, 400.0)],
    )

    assert summarize_files([block])["arch_sensitivity"] == []


def test_reference_arch_is_the_one_with_more_blocks(tmp_path: Path) -> None:
    peers = [("peer-1", 100.0), ("peer-2", 105.0), ("peer-3", 110.0)]
    blocks = [
        _write_bench(
            tmp_path / f"x{i}" / "bench.json",
            [_obs(p, 1_048_576, ns) for p, ns in peers]
            + [_obs("outlier", 1_048_576, 100.0)],
            arch="x86_64",
        )
        for i in range(3)
    ]
    blocks.append(
        _write_bench(
            tmp_path / "a1" / "bench.json",
            [_obs(p, 1_048_576, ns) for p, ns in peers]
            + [_obs("outlier", 1_048_576, 400.0)],
            arch="aarch64",
        )
    )

    sensitivity = summarize_files(blocks)["arch_sensitivity"]
    assert all(e["reference_arch"] == "x86_64" for e in sensitivity)
