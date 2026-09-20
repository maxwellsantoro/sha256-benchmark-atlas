from __future__ import annotations

import pytest

from sha256_benchmark_atlas.bench import _validated_raw_result, choose_iters


@pytest.mark.parametrize("key", ["ns_total", "hashes", "size", "digest"])
def test_validated_raw_result_requires_fields(key: str) -> None:
    raw = {"ns_total": 100, "hashes": 2, "size": 64, "digest": "a" * 64}
    raw.pop(key)
    with pytest.raises(ValueError):
        _validated_raw_result(raw, size=64, iters=2)


@pytest.mark.parametrize(
    "change",
    [
        {"ns_total": 0},
        {"ns_total": -1},
        {"hashes": 1},
        {"size": 65},
        {"digest": None},
        {"digest": "bad"},
        {"ns_total": True},
        {"hashes": 2.0},
        {"size": "64"},
    ],
)
def test_validated_raw_result_rejects_malformed_values(change: dict) -> None:
    raw = {"ns_total": 100, "hashes": 2, "size": 64, "digest": "a" * 64}
    raw.update(change)
    with pytest.raises(ValueError):
        _validated_raw_result(raw, size=64, iters=2)


def test_validated_raw_result_accepts_positive_control() -> None:
    assert (
        _validated_raw_result(
            {"ns_total": 100, "hashes": 2, "size": 64, "digest": "a" * 64},
            size=64,
            iters=2,
        )["hashes"]
        == 2
    )


@pytest.mark.parametrize(
    "size, expected",
    [
        (0, 50_000),
        (64, 50_000),
        (65, 20_000),
        (1024, 20_000),
        (1025, 2_000),
        (65536, 2_000),
        (65537, 200),
        (1_048_576, 200),
        (1_048_577, 20),
        (16_777_216, 20),
    ],
)
def test_choose_iters_fast_breakpoints(size: int, expected: int) -> None:
    assert choose_iters(size, slow=False) == expected


@pytest.mark.parametrize(
    "size, expected",
    [
        (0, 200),
        (64, 200),
        (65, 50),
        (1024, 50),
        (1025, 10),
        (65536, 10),
        (65537, 2),
        (1_048_576, 2),
        (1_048_577, 1),
    ],
)
def test_choose_iters_slow_breakpoints(size: int, expected: int) -> None:
    assert choose_iters(size, slow=True) == expected


def test_slow_never_exceeds_fast_iters() -> None:
    """The 'slow' lane (pure-language runners) must never ask for *more*
    iterations than the fast lane at the same size — it exists to keep wall
    time bounded for slow implementations, not to make them run longer."""
    for size in (0, 64, 1024, 65536, 1_048_576, 16_777_216):
        assert choose_iters(size, slow=True) <= choose_iters(size, slow=False)
