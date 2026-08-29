"""Decompose an implementation into fixed per-call cost and per-block cost.

SHA-256 consumes its input in 64-byte compression blocks, with the length and
padding forcing `ceil((n + 9) / 64)` of them. Cost is therefore close to affine in
block count:

    ns(n) = a + b * blocks(n)

The two parameters are mechanically different things, and separating them answers
questions a ranked list of ns/hash cannot:

  * **b** is the compression function itself. Implementations sharing a CPU
    datapath agree on it to a fraction of a percent regardless of language — it is
    the hardware ceiling, not a property of the binding.
  * **a** is everything the API wraps around that primitive: context allocation,
    FFI transitions, interpreter object churn. It spans two orders of magnitude
    across this atlas and is invisible at 1 MiB.

Estimation is deliberately two-stage rather than one ordinary least-squares pass.
Block counts span 1 to 16385, so OLS residuals are dominated by the largest size:
it recovers `b` well but leaves `a` poorly constrained, and reports an R² above
0.999 even for a fit that is 68% wrong at 4 KiB. Weighting by relative error fixes
the residual balance but biases `b` (it discards exactly the large-size points that
identify the slope). So:

  1. `b` is fitted on the large-size regime, where `a` is a rounding error.
  2. `a` is then taken as the robust median of `y - b * blocks` over the
     small-size regime, where `a` dominates.

The affine model is an approximation, not a law. Relative residuals are reported at
every size so the reader can see where it holds — and departures are themselves
informative: a large positive residual at one mid-range size is the signature of a
runtime that never reached steady state there.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any

# Fraction of the largest observed block count above which a point is considered
# part of the asymptotic regime used to fit the slope.
LARGE_REGIME_FRACTION = 1 / 1024

# Points at or below this multiple of the smallest observed block count are used to
# estimate the intercept.
SMALL_REGIME_MULTIPLE = 2

MIN_POINTS = 3

# A relative residual beyond this is reported as a departure worth explaining.
RESIDUAL_FLAG = 0.10

# Residuals are only diagnostic above this size. At one or two compression blocks the
# affine model is genuinely approximate — finalisation and padding are neither purely
# fixed nor purely per-block — so a large residual there says nothing about the
# runtime. Above it the model fits to a couple of percent for every ahead-of-time
# implementation in the atlas, which makes a large residual a real signal: almost
# always a tiered runtime that never reached steady state at that size.
STEADY_STATE_MIN_SIZE = 1024


def blocks_for_size(n: int) -> int:
    """Compression blocks consumed by an `n`-byte message (FIPS 180-4 padding)."""
    return -(-(n + 9) // 64)


@dataclass
class CostModel:
    a_ns: float
    b_ns_per_block: float
    asymptotic_gb_per_s: float
    residuals_by_size: dict[int, float] = field(default_factory=dict)
    max_abs_residual: float = 0.0
    worst_residual_size: int | None = None
    steady_state_residual: float = 0.0
    steady_state_residual_size: int | None = None
    slope_fit_sizes: list[int] = field(default_factory=list)
    intercept_fit_sizes: list[int] = field(default_factory=list)

    def predict(self, size: int) -> float:
        return self.a_ns + self.b_ns_per_block * blocks_for_size(size)

    def as_dict(self) -> dict[str, Any]:
        return {
            "a_ns_fixed": self.a_ns,
            "b_ns_per_block": self.b_ns_per_block,
            "asymptotic_gb_per_s": self.asymptotic_gb_per_s,
            "max_abs_relative_residual": self.max_abs_residual,
            "worst_residual_size": self.worst_residual_size,
            "residuals_by_size": {str(k): v for k, v in sorted(self.residuals_by_size.items())},
            "slope_fit_sizes": self.slope_fit_sizes,
            "intercept_fit_sizes": self.intercept_fit_sizes,
        }


def _ols_slope(points: list[tuple[float, float]]) -> float | None:
    xs = [x for x, _ in points]
    if len(set(xs)) < 2:
        return None
    mx = statistics.fmean(xs)
    my = statistics.fmean(y for _, y in points)
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in points) / denom


def fit_cost_model(by_size: dict[int, float]) -> CostModel | None:
    """Fit `ns = a + b * blocks` from a size → ns/hash mapping."""
    if len(by_size) < MIN_POINTS:
        return None

    points = sorted((blocks_for_size(s), ns, s) for s, ns in by_size.items())
    max_blocks = points[-1][0]
    min_blocks = points[0][0]

    large = [(x, y) for x, y, _ in points if x >= max_blocks * LARGE_REGIME_FRACTION]
    if len(large) < 2:
        large = [(x, y) for x, y, _ in points[-3:]]
    slope = _ols_slope(large)
    if slope is None or slope <= 0:
        return None

    small = [(x, y) for x, y, _ in points if x <= max(2, min_blocks * SMALL_REGIME_MULTIPLE)]
    if not small:
        small = [(x, y) for x, y, _ in points[:3]]
    intercept = statistics.median([y - slope * x for x, y in small])

    large_x = {x for x, _ in large}
    small_x = {x for x, _ in small}

    residuals: dict[int, float] = {}
    for x, y, size in points:
        if y:
            residuals[size] = (y - (intercept + slope * x)) / y

    worst_size, worst = None, 0.0
    for size, r in residuals.items():
        if abs(r) > abs(worst):
            worst_size, worst = size, r

    ss_size, ss = None, 0.0
    for size, r in residuals.items():
        if size >= STEADY_STATE_MIN_SIZE and abs(r) > abs(ss):
            ss_size, ss = size, r

    return CostModel(
        a_ns=intercept,
        b_ns_per_block=slope,
        asymptotic_gb_per_s=64.0 / slope if slope else 0.0,
        residuals_by_size=residuals,
        max_abs_residual=abs(worst),
        worst_residual_size=worst_size,
        steady_state_residual=abs(ss),
        steady_state_residual_size=ss_size,
        slope_fit_sizes=sorted({s for x, _, s in points if x in large_x}),
        intercept_fit_sizes=sorted({s for x, _, s in points if x in small_x}),
    )


def aggregate_models(models: list[CostModel]) -> dict[str, Any] | None:
    """Combine per-block fits, keeping dispersion rather than a single point value."""
    if not models:
        return None
    a = [m.a_ns for m in models]
    b = [m.b_ns_per_block for m in models]

    def spread(vals: list[float]) -> dict[str, float]:
        vals = sorted(vals)
        if len(vals) >= 4:
            q = statistics.quantiles(vals, n=4, method="inclusive")
            p25, p75 = q[0], q[2]
        else:
            p25, p75 = vals[0], vals[-1]
        return {
            "median": statistics.median(vals),
            "p25": p25,
            "p75": p75,
            "min": vals[0],
            "max": vals[-1],
        }

    worst = max(models, key=lambda m: m.max_abs_residual)
    b_median = statistics.median(b)

    # Residuals are aggregated by taking the median across blocks *first*, then the
    # worst size. Taking the worst block instead lets a single noisy host — and with
    # ten blocks spread over four CPU models there is usually one — flag an
    # implementation whose typical behaviour is fine.
    median_residuals = {
        size: statistics.median(
            [m.residuals_by_size[size] for m in models if size in m.residuals_by_size]
        )
        for size in sorted({s for m in models for s in m.residuals_by_size})
    }
    ss_size, ss = None, 0.0
    for size, r in median_residuals.items():
        if size >= STEADY_STATE_MIN_SIZE and abs(r) > abs(ss):
            ss_size, ss = size, r

    return {
        "blocks_fitted": len(models),
        "a_ns_fixed": spread(a),
        "b_ns_per_block": spread(b),
        "asymptotic_gb_per_s": 64.0 / b_median if b_median else 0.0,
        "max_abs_relative_residual": worst.max_abs_residual,
        "worst_residual_size": worst.worst_residual_size,
        # The diagnostic that matters: a departure at a size where the model is
        # otherwise exact. Large values here are a not-at-steady-state signal.
        "steady_state_residual": abs(ss),
        "steady_state_residual_size": ss_size,
        "steady_state_residual_worst_block": max(m.steady_state_residual for m in models),
        "reached_steady_state": abs(ss) <= RESIDUAL_FLAG,
        "residuals_by_size": {str(k): v for k, v in median_residuals.items()},
        "slope_fit_sizes": models[0].slope_fit_sizes,
        "intercept_fit_sizes": models[0].intercept_fit_sizes,
    }
