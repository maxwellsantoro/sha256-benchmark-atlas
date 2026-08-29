# PAIN.md — empirical requirements for a future Benchmarkour

Every concrete friction encountered while building the SHA-256 atlas gets a note here.
This file is intentionally ugly and cumulative. Abstractions in a later general harness
should cite entries from this list.

## Build & packaging

- [ ] Heterogeneous build systems (Make, Cargo, Go modules, javac, interpreters) with no shared install root.
- [ ] OpenSSL discovery differs by platform (`pkg-config`, Homebrew keg-only paths, distro `libssl-dev`).
- [ ] Toolchains absent locally but present in CI (Go); harness must soft-skip or mark `UNSUPPORTED_PLATFORM`.
- [ ] Java major-version APIs (`HexFormat` vs manual hex) silently break older JDKs.
- [x] Pinning library versions / source commits in the registry while runners use “system” OpenSSL.
      *Resolved:* the fingerprint now resolves `libcrypto` / `libsodium` / `mbedcrypto` /
      `cryptography` versions, and each registry entry carries `version_resolved_from`
      naming the fingerprint key that holds its real version. A test enforces the pointer.

## Provenance & identity

- [ ] Language front-ends that are really OpenSSL (Python `hashlib`, Node `crypto`, Ruby, …) look “fast in Python” on leaderboards.
- [x] Detecting the actual CPU path (SHA-NI vs portable C) from outside the library is unreliable.
      *Partly resolved:* CPU capability is now detected per-arch (x86 `sha_ni`, aarch64 `sha2`),
      and what the library actually **did** with it is inferred from `arch_sensitivity` —
      an implementation that loses acceleration on one arch departs from its cohort's ratio.
- [ ] Duplicate backends: how to mark `DUPLICATE_BACKEND` without punishing legitimate API comparisons.
- [ ] “Native” vs “production” leaderboard membership is a judgment call that needs audit notes.

## Measurement boundaries

- [ ] Process startup must stay outside the timed region (hence in-process `bench` loops).
- [ ] One-shot vs streaming APIs are different products; mixing them confounds small-message results.
- [ ] Allocation / GC (Java, Python, Node) affects short-message ns/hash more than bulk GB/s.
- [x] JIT warmup (JVM, JS) — how many discarded reps are enough?
      *Resolved:* a fixed count is the wrong shape. All runners now warm on a shared
      200 ms budget capped at 100k iterations, which reaches C2 at small sizes and
      does not waste multi-second iterations at 1 MiB.
- [ ] Buffer preparation and PRNG fill must not dominate tiny-message timings (currently outside timed loop, good).
- [ ] Clock choice (`CLOCK_MONOTONIC` vs `perf_counter_ns` vs `System.nanoTime`) cross-language consistency.

## Hardware & environment

- [x] Same runner *class* ≠ same CPU model; fingerprinting is mandatory evidence, not metadata fluff.
      *Confirmed the hard way:* one campaign's 10 `ubuntu-24.04` blocks landed on **four**
      different CPU models. Absolute ns/hash has CV ~0.11 across them; within-block
      paired ratios resolve 0.2%. Absolute numbers across a runner class are near-useless.
- [ ] Noisy neighbors / turbo / thermal — absolute GB/s are weak; on-machine ratios are stronger.
- [x] SHA-NI / ARM crypto feature detection for stratification of results.
      *Resolved:* aarch64 publishes `Features`, not `flags`, and no `model name` at all.
      The original parser therefore reported every ARM host as having no SHA-256 hardware
      and no CPU name. Both are now parsed, with `None` for genuinely unknown rather than
      a silent `False`.
- [ ] macOS vs Linux local results are not interchangeable with GHA blocks.

## Correctness

- [ ] Streaming with adversarial chunk partitions not yet exercised inside every implementation (only one-shot).
- [ ] Million-`a` NIST vector is slow for pure-Python — needs opt-out / separate slow lane.
- [x] Differential agreement among implementations vs single oracle (`hashlib`) — oracle independence.
      *Resolved by disclosure:* 5 of 10,021 cases are externally published ground truth;
      the rest are `hashlib`-derived and cannot detect an error shared with the oracle.
      `correctness.json` now states the split and reports unanimity across 12 backends
      as the actual independent evidence.

## Statistics & reporting

- [ ] How many interleaved reps and runner blocks for a portable claim?
      Partly informed: 2 aarch64 blocks were enough to detect a 5x acceleration loss,
      but not enough to bound small differences. Win counts (`k/k`) make the evidence
      base legible where a bare median does not.
- [x] Summaries must keep raw observations; derived medians are not the evidence archive.
      *Resolved:* `results/latest/blocks/` holds every observation, gzipped, ~660 KiB for
      12 blocks, and the summary is derived **from that archive** so the two cannot drift.
- [ ] Artifact storage limits vs keeping full PRNG-scale correctness logs.
      Bench observations turned out to be cheap once the per-block registry copy and the
      per-core `/proc/cpuinfo` repetition were dropped (6.9 MiB → 660 KiB).

## Process / social

- [ ] Exclusion decisions need durable reasons in the registry (avoid silent omissions).
- [ ] “Add yours by PR” requires a low-friction runner template and CI that fails clearly.

## Entries filed while scaffolding (2026-08-26)

1. **OpenSSL link flags on macOS** — plain `-lcrypto` failed until `pkg-config` was wired into the Makefile.
2. **Go optional locally** — campaign must continue when `go` is missing; CI installs it.
3. **Pure-Python cost** — full size matrix + high iters is impractical; `max-size` / `choose_iters` are load-bearing.
4. **No generic adapter yet** — duplicated CLI parsers in each language; painful but intentional for v1.
5. **Registry `build: null` vs interpreted runners** — needed an interpreter field and chmod for scripts.
6. **Per-case process spawn** — initial correctness gate was unusable at 10k cases; added length-prefixed batch `verify`.
7. **macOS Java stubs** — `/usr/bin/java` exists but needs a real JDK on PATH (Homebrew OpenJDK).
8. **Slow pure-language benches** — registry `slow: true` with reduced iters; otherwise pure Python dominates wall clock.
9. **mbedTLS version split** — PSA `psa_hash_compute` used so runner works on Ubuntu 3.x and Homebrew 4.x.
10. **PHP 64-bit PRNG** — bench fill uses GMP; CI needs `php-gmp` extension.
11. **Native lib discovery** — C Makefiles use `pkg-config` (libsodium, mbedcrypto) like OpenSSL.

## Entries filed while reviewing the first published campaign (2026-08-29)

12. **Pooling across architectures is silently destructive** — a single median over
    10 x86_64 and 2 aarch64 blocks reported `rust-sha2` at parity with `c-openssl`.
    Stratified, it is 0.999x on x86_64 and 5.14x on aarch64. Any harness that offers a
    "combine all runs" summary needs to refuse, or at minimum flag, heterogeneous pools.
13. **A ratio of two pooled medians is not an on-machine ratio** — the repo promised
    "median on-machine ratio R over k/k blocks" and computed `median(A)/median(B)` over
    pooled observations, which cannot produce a win count and does not cancel host
    variation. Pairing must happen inside the block, before any aggregation.
14. **The timed path needs its own correctness check** — the correctness gate exercised
    `verify` while the benchmark timed `bench`. Cross-implementation digest agreement per
    (size, rep) is free, because all runners share a seeded PRNG spec, and it is the only
    thing standing between the harness and timing a dead loop.
15. **Single-member "clusters" are noise** — 11 of 13 backend clusters had one member and
    a spread of exactly 1.0, burying the two informative rows.
16. **The same statistic can support opposite conclusions at different sizes** — the
    OpenSSL front-end cluster spreads 1.009x at 1 MiB and 4.538x at 64 B. Reporting only
    the flattering size is an easy and invisible mistake.
17. **Truncating a failure scan corrupts the count** — stopping at 5 samples and then
    reporting `failed: 5` understated a total failure by three orders of magnitude.
18. **Detection code needs a negative test on real foreign hardware** — the ARM
    fingerprint bug was invisible because the value it produced (`false`) was a plausible
    one. Prefer tri-state (`true`/`false`/unknown) for any capability probe.

## Entries filed while adding mechanical decomposition (2026-08-29)

19. **A ranked list of ns/hash is the wrong output shape** — 17 correlated numbers per
    implementation hide the two that matter. Fitting `a + b*blocks` separates API cost
    from primitive cost and makes "same backend" claims checkable: `b` agrees to 0.8%
    across five unrelated codebases while `a` spans 54x over the same set.
20. **R^2 is worthless when the x range spans four orders of magnitude** — an ordinary
    least-squares fit reported R^2 > 0.999 for a model that was 68% wrong at 4 KiB.
    Per-point relative residuals are the diagnostic; the summary statistic is not.
21. **Weighting to fix residual balance biases the slope** — minimising relative error
    discards exactly the large-size points that identify `b`. Fit the slope in the
    asymptotic regime and the intercept in the small-message regime instead.
22. **Residuals need a regime before they mean anything** — below ~1 KiB the affine
    model is genuinely approximate (finalisation is neither fixed nor per-block), so a
    large residual there is not a defect. Above it, a large residual is almost always a
    tiered runtime that never reached steady state.
23. **Static disassembly answers "which code path" directly** — counting arch-specific
    SHA-256 mnemonics in the shipped artifact needs no runner, no timing and no
    inference. Match whole mnemonics: aarch64 also advertises sha1/sha3/sha512, and
    `sha256h` is a prefix of `sha256h2`.
24. **Auditing an interpreter means finding its native module** — a venv `python3` is a
    symlink to a launcher stub in front of `@rpath/libpython3.12.dylib`, which is where
    the statically linked OpenSSL actually lives. Naive auditing of the named binary
    reports "no hardware path" for an implementation running at 2.16 GB/s.
25. **Registry-supplied commands must not go through a shell** — the Ruby probe contains
    `$LOADED_FEATURES`, which a shell expands to nothing. `shlex.split` fixes it and
    removes an injection surface at the same time.
26. **Two independent methods disagreeing is a finding, not noise** — cross-checking the
    audit against the fitted `b` caught a genuine audit gap (a system library behind the
    macOS dyld shared cache) that neither method would have surfaced alone.
27. **A registry field can be wrong for years without anyone noticing** — `php-hash` was
    marked `hardware_acceleration: auto`; it ships no SHA-256 instructions and its
    per-block cost matches the portable cohort on both architectures.
