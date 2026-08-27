from __future__ import annotations

import hashlib

from sha256_benchmark_atlas.correctness import (
    boundary_vectors,
    load_nist_vectors,
    make_prng_cases,
    streamish_cases,
)
from sha256_benchmark_atlas.paths import repo_root


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
