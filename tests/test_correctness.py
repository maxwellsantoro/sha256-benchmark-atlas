from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

from sha256_benchmark_atlas import correctness as correctness_mod
from sha256_benchmark_atlas.correctness import (
    MAX_FAILURE_SAMPLES,
    boundary_vectors,
    check_impl,
    load_nist_vectors,
    make_prng_cases,
    streamish_cases,
)
from sha256_benchmark_atlas.paths import repo_root
from sha256_benchmark_atlas.registry import Implementation


def test_boundary_vectors_cover_padding_discontinuity() -> None:
    sizes = [len(msg) for _, msg, _ in boundary_vectors()]
    assert 55 in sizes and 56 in sizes  # the one-block/two-block padding boundary
    assert 63 in sizes and 64 in sizes and 65 in sizes  # block-boundary neighbors


def test_boundary_vectors_digests_match_hashlib_oracle() -> None:
    for _, msg, expected in boundary_vectors():
        assert hashlib.sha256(msg).hexdigest() == expected


def test_make_prng_cases_is_deterministic() -> None:
    a = make_prng_cases(20, seed=42)
    b = make_prng_cases(20, seed=42)
    assert a == b


def test_make_prng_cases_different_seed_differs() -> None:
    a = make_prng_cases(20, seed=42)
    b = make_prng_cases(20, seed=43)
    assert a != b


def test_make_prng_cases_digests_match_hashlib_oracle() -> None:
    for _, msg, expected in make_prng_cases(50, seed=7):
        assert hashlib.sha256(msg).hexdigest() == expected


def test_make_prng_cases_length_bound() -> None:
    for _, msg, _ in make_prng_cases(200, seed=1):
        assert 0 <= len(msg) < 4097


def test_streamish_cases_digests_match_hashlib_oracle() -> None:
    for _, msg, expected in streamish_cases():
        assert hashlib.sha256(msg).hexdigest() == expected


def test_load_nist_vectors_skip_million() -> None:
    root = repo_root()
    with_million = load_nist_vectors(root, skip_million=False)
    without_million = load_nist_vectors(root, skip_million=True)
    ids_with = {vid for vid, _, _ in with_million}
    ids_without = {vid for vid, _, _ in without_million}
    assert "million_a" in ids_with
    assert "million_a" not in ids_without
    assert ids_with - ids_without == {"million_a"}


def test_load_nist_vectors_digests_match_hashlib_oracle() -> None:
    root = repo_root()
    for _, msg, expected in load_nist_vectors(root, skip_million=True):
        assert hashlib.sha256(msg).hexdigest() == expected


# --- failure accounting ---------------------------------------------------


def _impl(iid: str = "fake") -> Implementation:
    return Implementation({"id": iid, "binary": "nonexistent", "status": "admitted"})


def _cases(n: int) -> list[tuple[str, bytes, str]]:
    return [(f"case_{i}", bytes([i % 251]), hashlib.sha256(bytes([i % 251])).hexdigest()) for i in range(n)]


def _patch_verify(monkeypatch: pytest.MonkeyPatch, digests: list[str]) -> None:
    monkeypatch.setattr(
        correctness_mod, "verify_batch", lambda root, impl, messages: digests
    )


def test_check_impl_counts_every_failure_not_just_the_sampled_ones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A totally broken implementation used to report `failed: 5`."""
    cases = _cases(100)
    _patch_verify(monkeypatch, ["0" * 64] * 100)

    result = check_impl(Path("."), _impl(), cases)

    assert result["ok"] is False
    assert result["failed"] == 100
    assert len(result["failure_samples"]) == MAX_FAILURE_SAMPLES
    assert result["failures_truncated"] is True


def test_check_impl_reports_exact_count_below_the_sample_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cases = _cases(10)
    digests = [expected for _, _, expected in cases]
    digests[3] = "0" * 64
    digests[7] = "0" * 64
    _patch_verify(monkeypatch, digests)

    result = check_impl(Path("."), _impl(), cases)

    assert result["failed"] == 2
    assert result["failures_truncated"] is False
    assert [f["case"] for f in result["failure_samples"]] == ["case_3", "case_7"]


def test_check_impl_passes_cleanly(monkeypatch: pytest.MonkeyPatch) -> None:
    cases = _cases(10)
    _patch_verify(monkeypatch, [expected for _, _, expected in cases])

    result = check_impl(Path("."), _impl(), cases)

    assert result == {
        "id": "fake",
        "checked": 10,
        "failed": 0,
        "failure_samples": [],
        "failures_truncated": False,
        "ok": True,
    }


def test_check_impl_batch_failure_counts_all_cases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A runner that will not start has failed every case, not one."""

    def boom(root: Path, impl: Implementation, messages: list[bytes]) -> list[str]:
        raise RuntimeError("runner exploded")

    monkeypatch.setattr(correctness_mod, "verify_batch", boom)

    result: dict[str, Any] = check_impl(Path("."), _impl(), _cases(42))

    assert result["ok"] is False
    assert result["failed"] == 42
