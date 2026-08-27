# PAIN.md — empirical requirements for a future Benchmarkour

Every concrete friction encountered while building the SHA-256 atlas gets a note here.
This file is intentionally ugly and cumulative. Abstractions in a later general harness
should cite entries from this list.

## Build & packaging

- [ ] Heterogeneous build systems (Make, Cargo, Go modules, javac, interpreters) with no shared install root.
- [ ] OpenSSL discovery differs by platform (`pkg-config`, Homebrew keg-only paths, distro `libssl-dev`).
- [ ] Toolchains absent locally but present in CI (Go); harness must soft-skip or mark `UNSUPPORTED_PLATFORM`.
- [ ] Java major-version APIs (`HexFormat` vs manual hex) silently break older JDKs.
- [ ] Pinning library versions / source commits in the registry while runners use “system” OpenSSL.

## Provenance & identity

- [ ] Language front-ends that are really OpenSSL (Python `hashlib`, Node `crypto`, Ruby, …) look “fast in Python” on leaderboards.
- [ ] Detecting the actual CPU path (SHA-NI vs portable C) from outside the library is unreliable.
- [ ] Duplicate backends: how to mark `DUPLICATE_BACKEND` without punishing legitimate API comparisons.
- [ ] “Native” vs “production” leaderboard membership is a judgment call that needs audit notes.

## Measurement boundaries

- [ ] Process startup must stay outside the timed region (hence in-process `bench` loops).
- [ ] One-shot vs streaming APIs are different products; mixing them confounds small-message results.
- [ ] Allocation / GC (Java, Python, Node) affects short-message ns/hash more than bulk GB/s.
- [ ] JIT warmup (JVM, JS) — how many discarded reps are enough?
- [ ] Buffer preparation and PRNG fill must not dominate tiny-message timings (currently outside timed loop, good).
- [ ] Clock choice (`CLOCK_MONOTONIC` vs `perf_counter_ns` vs `System.nanoTime`) cross-language consistency.

## Hardware & environment

- [ ] Same runner *class* ≠ same CPU model; fingerprinting is mandatory evidence, not metadata fluff.
- [ ] Noisy neighbors / turbo / thermal — absolute GB/s are weak; on-machine ratios are stronger.
- [ ] SHA-NI / ARM crypto feature detection for stratification of results.
- [ ] macOS vs Linux local results are not interchangeable with GHA blocks.

## Correctness

- [ ] Streaming with adversarial chunk partitions not yet exercised inside every implementation (only one-shot).
- [ ] Million-`a` NIST vector is slow for pure-Python — needs opt-out / separate slow lane.
- [ ] Differential agreement among implementations vs single oracle (`hashlib`) — oracle independence.

## Statistics & reporting

- [ ] How many interleaved reps and runner blocks for a portable claim?
- [ ] Summaries must keep raw observations; derived medians are not the evidence archive.
- [ ] Artifact storage limits vs keeping full PRNG-scale correctness logs.

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
