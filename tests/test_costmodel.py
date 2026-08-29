from __future__ import annotations

from sha256_benchmark_atlas.costmodel import (
    RESIDUAL_FLAG,
    aggregate_models,
    blocks_for_size,
    fit_cost_model,
)

SIZES = [0, 1, 3, 32, 55, 56, 63, 64, 65, 80, 127, 128, 256, 1024, 4096, 65536, 1048576]


def synthetic(a: float, b: float, sizes: list[int] | None = None) -> dict[int, float]:
    return {s: a + b * blocks_for_size(s) for s in (sizes or SIZES)}


# --- block accounting -----------------------------------------------------


def test_blocks_for_size_matches_fips_padding() -> None:
    # A message needs room for its 0x80 terminator and an 8-byte length, so 55 bytes
    # is the largest single-block message: 55 + 1 + 8 == 64 exactly. This is the
    # discontinuity the registry's 55/56 boundary sizes exist to probe.
    assert blocks_for_size(0) == 1
    assert blocks_for_size(55) == 1
    assert blocks_for_size(56) == 2
    assert blocks_for_size(64) == 2
    assert blocks_for_size(119) == 2
    assert blocks_for_size(120) == 3
    assert blocks_for_size(1_048_576) == 16385


# --- recovery of known parameters ----------------------------------------


def test_recovers_exact_parameters_from_noiseless_data() -> None:
    model = fit_cost_model(synthetic(a=330.0, b=40.35))
    assert model is not None
    assert model.a_ns == 330.0
    assert abs(model.b_ns_per_block - 40.35) < 1e-6
    assert model.max_abs_residual < 1e-9


def test_recovers_parameters_across_the_atlas_range() -> None:
    for a, b in [(15.0, 40.3), (2935.0, 45.2), (0.0, 300.0), (1800.0, 40.4)]:
        model = fit_cost_model(synthetic(a, b))
        assert model is not None
        assert abs(model.a_ns - a) < 1e-6, (a, b)
        assert abs(model.b_ns_per_block - b) < 1e-6, (a, b)


def test_asymptotic_throughput_derives_from_slope() -> None:
    model = fit_cost_model(synthetic(a=0.0, b=64.0))
    assert model is not None
    assert abs(model.asymptotic_gb_per_s - 1.0) < 1e-9


def test_slope_is_unaffected_by_a_large_fixed_overhead() -> None:
    """The point of the decomposition: API cost must not contaminate primitive speed."""
    cheap = fit_cost_model(synthetic(a=15.0, b=40.35))
    costly = fit_cost_model(synthetic(a=2935.0, b=40.35))
    assert cheap is not None and costly is not None
    assert abs(cheap.b_ns_per_block - costly.b_ns_per_block) < 1e-6
    assert costly.a_ns - cheap.a_ns > 2900


# --- residuals as a diagnostic -------------------------------------------


def test_a_size_that_never_reached_steady_state_is_flagged() -> None:
    by_size = synthetic(a=1200.0, b=45.0)
    by_size[4096] *= 2.2  # tiered runtime still interpreting at this size
    model = fit_cost_model(by_size)
    assert model is not None
    assert model.steady_state_residual_size == 4096
    assert model.steady_state_residual > RESIDUAL_FLAG


def test_small_size_deviation_does_not_count_as_a_steady_state_failure() -> None:
    """Below 1 KiB the affine model is approximate; that is not a runtime problem."""
    by_size = synthetic(a=30.0, b=40.0)
    by_size[64] *= 1.5
    model = fit_cost_model(by_size)
    assert model is not None
    assert model.max_abs_residual > RESIDUAL_FLAG
    assert model.steady_state_residual < RESIDUAL_FLAG


def test_clean_data_reports_steady_state() -> None:
    agg = aggregate_models([fit_cost_model(synthetic(330.0, 40.35))])  # type: ignore[list-item]
    assert agg is not None
    assert agg["reached_steady_state"] is True


# --- aggregation ----------------------------------------------------------


def test_aggregation_keeps_dispersion_across_blocks() -> None:
    models = [fit_cost_model(synthetic(300.0, b)) for b in (40.0, 41.0, 42.0, 43.0)]
    agg = aggregate_models([m for m in models if m])
    assert agg is not None
    assert agg["blocks_fitted"] == 4
    assert agg["b_ns_per_block"]["median"] == 41.5
    assert agg["b_ns_per_block"]["min"] == 40.0
    assert agg["b_ns_per_block"]["max"] == 43.0
    assert agg["b_ns_per_block"]["p25"] < agg["b_ns_per_block"]["p75"]


def test_aggregate_of_nothing_is_none() -> None:
    assert aggregate_models([]) is None


def test_one_noisy_block_does_not_flag_a_healthy_implementation() -> None:
    """Ten blocks over four CPU models nearly always include one outlier.

    Aggregating the worst block instead of the median across blocks made an
    ahead-of-time implementation look like it never reached steady state.
    """
    clean = [fit_cost_model(synthetic(30.0, 40.0)) for _ in range(9)]
    noisy_data = synthetic(30.0, 40.0)
    noisy_data[4096] *= 1.9
    models = [m for m in [*clean, fit_cost_model(noisy_data)] if m]

    agg = aggregate_models(models)

    assert agg is not None
    assert agg["reached_steady_state"] is True
    assert agg["steady_state_residual"] < RESIDUAL_FLAG
    # The outlier is still reported, just not used to judge the implementation.
    assert agg["steady_state_residual_worst_block"] > RESIDUAL_FLAG


def test_a_consistently_slow_size_is_still_flagged() -> None:
    """The majority behaviour is what counts, and here the majority is bad."""
    models = []
    for _ in range(10):
        data = synthetic(1200.0, 45.0)
        data[4096] *= 1.5
        models.append(fit_cost_model(data))

    agg = aggregate_models([m for m in models if m])

    assert agg is not None
    assert agg["reached_steady_state"] is False
    assert agg["steady_state_residual_size"] == 4096


def test_steady_state_residual_matches_median_residuals_table() -> None:
    """Top-level steady_state_* must agree with residuals_by_size for that size.

    A stale summary once reported worst-block residuals in steady_state_residual
    while residuals_by_size held the median-across-blocks table — two answers in
    one object. Keep them locked together.
    """
    models = []
    for _ in range(10):
        data = synthetic(1200.0, 45.0)
        data[4096] *= 1.5
        models.append(fit_cost_model(data))

    agg = aggregate_models([m for m in models if m])
    assert agg is not None
    size = agg["steady_state_residual_size"]
    assert size == 4096
    assert abs(agg["steady_state_residual"] - abs(agg["residuals_by_size"][str(size)])) < 1e-12

    # Same lock must hold when one noisy block would disagree with the median.
    clean = [fit_cost_model(synthetic(30.0, 40.0)) for _ in range(9)]
    noisy = synthetic(30.0, 40.0)
    noisy[4096] *= 1.9
    mixed = aggregate_models([m for m in [*clean, fit_cost_model(noisy)] if m])
    assert mixed is not None
    mixed_size = mixed["steady_state_residual_size"]
    if mixed_size is not None:
        assert (
            abs(mixed["steady_state_residual"] - abs(mixed["residuals_by_size"][str(mixed_size)]))
            < 1e-12
        )


# --- degenerate input -----------------------------------------------------


def test_too_few_points_yields_no_model() -> None:
    assert fit_cost_model({0: 10.0, 64: 20.0}) is None


def test_works_on_a_short_local_size_sweep() -> None:
    """A `--max-size 4096` local run must still produce a usable fit."""
    model = fit_cost_model(synthetic(300.0, 40.0, sizes=[0, 64, 256, 1024, 4096]))
    assert model is not None
    assert abs(model.b_ns_per_block - 40.0) < 1e-6


def test_flat_or_nonsensical_data_yields_no_model() -> None:
    assert fit_cost_model({s: 100.0 for s in SIZES}) is None
