# SHA-256 Benchmark Atlas

[![SHA-256 campaign](https://github.com/maxwellsantoro/sha256-benchmark-atlas/actions/workflows/campaign.yml/badge.svg)](https://github.com/maxwellsantoro/sha256-benchmark-atlas/actions/workflows/campaign.yml)

Public atlas of **SHA-256 implementations** across languages and libraries: correctness first, then comparative performance with explicit provenance.

This is **not** a “fastest programming language” shootout. Many language APIs wrap the same native backend (often OpenSSL). The registry records:

```text
language interface → library → implementation → backend → CPU path
```

Design notes and motivation: [`GitHub-CI-Limits.md`](GitHub-CI-Limits.md). Pain points that should feed a future general harness live in [`PAIN.md`](PAIN.md).

## Layout

```text
implementations/       per-candidate runners (same CLI contract)
registry/              admitted / excluded implementations + provenance
vectors/               NIST / FIPS short-message vectors
harness via            `uv run sha256-atlas ...`
results/latest/blocks/ raw per-block observations + fingerprint + capability audit
results/latest/        summary.json derived from those blocks
analysis/              summarization helpers
.github/workflows/     multi-shard GitHub Actions experimental blocks
```

## Runner contract

Every implementation exposes:

```text
hash                 # stdin bytes → hex digest on stdout
verify               # batch: repeated [u32 BE length][msg] → hex digest per line
bench SIZE ITERS [SEED]
                     # → JSON {"ns_total","hashes","size","digest"}
```

Timing loops run **inside** the candidate process (startup cost is not the measurement).
Correctness uses `verify` so thousands of cases share one process.
Warmup is a shared time budget (200 ms, capped at 100k iterations) rather than a fixed
count, so JIT runtimes reach steady state and multi-second software hashes don't pay for
iterations they don't need.

## How results are aggregated

Two rules, because violating either produces numbers that describe no real machine:

1. **Architectures are never pooled.** Each stratum is reported separately. Pooling
   10 x86_64 blocks with 2 aarch64 blocks hides the fact that some implementations
   change rank entirely between them (see below).
2. **Ratios are formed within a block, never between pooled medians.** The
   interleaved design exists so `T_A/T_B` can be measured on one host, where
   host-to-host speed differences cancel. This matters concretely: the ten x86_64
   blocks span **four different CPU models**, so absolute ns/hash has a CV around
   0.11, while the paired ratios resolve differences of 0.2%.

Every summary also cross-checks the digests produced **inside the timed loop** —
all runners fill their buffer from the same seeded PRNG, so at a given (size, rep)
they must agree. The correctness gate exercises `verify`, a different code path;
without this a bench loop hashing the wrong bytes would be timed and published.

## Mechanical decomposition

A ranked list of ns/hash cannot tell you *why* one implementation differs from
another. Two additions do.

### Fixed cost vs per-block cost

SHA-256 consumes whole 64-byte compression blocks, so cost is close to affine in
block count: `ns = a + b · ceil((n+9)/64)`. Fitting that inside each block splits
every implementation into two mechanically different quantities — `a`, everything
the API wraps around the primitive, and `b`, the primitive itself.

| x86_64 | a (ns/call) | b (ns/64B block) | asympt GB/s |
|---|---|---|---|
| rust-sha2 | 32 | 40.32 | 1.587 |
| go-stdlib | 43 | 40.36 | 1.586 |
| rust-ring | 64 | 40.32 | 1.587 |
| c-openssl | 326 | 40.36 | 1.586 |
| python-hashlib | 352 | 40.34 | 1.587 |
| bun-crypto | 488 | 40.51 | 1.580 |
| node-crypto | 869 | 40.61 | 1.576 |
| python-cryptography | 1441 | 40.41 | 1.584 |
| ruby-openssl | 1725 | 40.39 | 1.584 |
| zig-std | 96 | 46.75 | 1.369 |
| c-libsodium | 49 | 206.45 | 0.310 |
| c-ref | −23 | 299.43 | 0.214 |

`b` agrees to **0.8% across five unrelated codebases** — ring, RustCrypto, Go
stdlib, OpenSSL and BoringSSL — which is the hardware ceiling stated directly
rather than inferred from a ratio at one size. `a` spans **54×** over the same
set: `c-openssl`'s 326 ns *is* the EVP context setup, and Ruby's extra ~1400 ns is
interpreter overhead. That single number explains the entire small-message spread
the 1 MiB table cannot see.

The same split settles the aarch64 case without appeal to timing coincidence:
`rust-sha2` has `a` = 21 ns (negligible) and `b` = 152.9 vs OpenSSL's 29.7. The
penalty is in the compression function, so it is a different code path — not an
API difference.

Residuals against the fit are reported per size. Below 1 KiB the affine model is
genuinely approximate and departures mean nothing; above it, it holds to a couple
of percent for every ahead-of-time implementation, so a large residual is a real
signal. It flags exactly the tiered runtimes and nothing else:

```text
java-jdk           75% at 4096 B      node-crypto        25% at 4096 B
java-bouncycastle  27% at 4096 B      bun-crypto         13% at 4096 B
```

That is a runtime which never reached steady state at that size, not a property of
SHA-256 — and it is a direct before/after metric for the warmup budget.

### Static capability audit

Whether a hardware SHA-256 datapath is even present is a question about the binary,
not about timing. `sha256-atlas audit` disassembles each built artifact and the
crypto libraries it links, counting the arch-specific mnemonics:

```text
rust-sha2 (aarch64)        0     libcrypto           1105
rust-ring                 56     libsodium              0
go-stdlib                 56     libmbedcrypto          0
```

Interpreted runners declare an `audit_artifact_cmd` in the registry saying where
their native module actually lives, which covers the OpenSSL front-ends. A JIT
intrinsic (`java-jdk`) exists only at run time and is reported as unknown rather
than guessed at.

The audit and the fitted `b` are independent answers to the same question, so
`summary.json` cross-checks them and reports any disagreement under
`audit_measurement_conflicts`. A fast implementation with no instructions found
means the audit missed a library; instructions present with portable-looking timing
means dispatch declined them. Either way it is a finding, not something to average
away — and it is how `php-hash` was reclassified from `hardware_acceleration: auto`
to `portable`.

## Experiment design (GitHub Actions)

Each workflow job is one **experimental block**:

1. Fingerprint CPU / OS / toolchains / library versions / SHA hardware support
2. Build all admitted candidates, then statically audit them for a SHA-256 datapath
3. Correctness gate (NIST + boundaries + PRNG); only passers are timed
4. **Interleaved** benches of all candidates on that same VM
5. Archive raw observations, then summarize stratified by architecture

## Latest campaign ([run #33234020231](https://github.com/maxwellsantoro/sha256-benchmark-atlas/actions/runs/33234020231))

12 independent GitHub-hosted blocks, 5 interleaved reps, 10k correctness cases,
sizes 0–1 MiB, all 19 admitted implementations passing correctness and benched.
Raw observations: [`results/latest/blocks/`](results/latest/blocks/) — 1020 timed-path
digest cells checked, 0 disagreements. Aggregate: [`results/latest/summary.json`](results/latest/summary.json).

Host population: **10 × x86_64** spanning four CPU models (EPYC 7763, EPYC 9V45,
EPYC 9V74, Xeon Platinum 8573C) and **2 × aarch64** (Neoverse-N2).

### At 1 MiB, on-machine ratio vs `c-openssl` (median, with per-block win count)

| Implementation | Backend | x86_64 | aarch64 |
|---|---|---|---|
| rust-ring | ring | **0.998×** (9/10) | **0.995×** (2/2) |
| rust-sha2 | rustcrypto | **0.999×** (10/10) | **5.143×** (0/2) |
| go-stdlib | go-stdlib | 0.999× (9/10) | 1.016× (0/2) |
| python-hashlib | openssl | 1.000× (7/10) | 0.998× (2/2) |
| node-crypto | openssl | 1.006× | 1.016× |
| java-jdk | jdk-provider | 1.128× | 1.101× |
| zig-std | zig-stdlib | 1.138× | **6.822×** |
| c-libsodium | libsodium | 5.054× | 5.845× |
| c-mbedtls | mbedtls | 5.704× | 6.088× |
| php-hash | php-hash-ext | 5.994× | 13.019× |
| c-ref | reference-c | 7.024× | 14.051× |
| java-bouncycastle | bouncycastle | 9.816× | 9.004× |

Peak bulk throughput: **1.587 GB/s** on x86_64, **2.163 GB/s** on aarch64.

### What the data actually shows

**The 1 MiB convergence is a hardware ceiling, not a shared library.** Six OpenSSL
front-ends land within 1% of each other — but so do `rust-ring`, `rust-sha2` and
`go-stdlib`, which share no code with OpenSSL and sit *closer* to `c-openssl` than
`node-crypto` does. Everything with a SHA-256 hardware datapath converges on the
same number; everything portable (libsodium, mbedTLS, the C reference) sits ~5–7×
below it. That gap is the size of the hardware acceleration, and it is the real
finding. Backend identity explains almost nothing here.

**Two implementations silently lose their acceleration on aarch64.** `rust-sha2`
goes from 0.999× (beating `c-openssl` in 10/10 x86_64 blocks) to **5.143×** on
Neoverse-N2; `zig-std` goes from 1.138× to **6.822×**. `sha2 = "0.10"` needs its
`asm` feature for ARMv8 crypto extensions, so the default stable build falls back
to portable code, and Zig 0.14's std has no ARM path at all. Their peers on the
same two hosts keep their acceleration, which is how the `arch_sensitivity` check
flags them. A pooled median across all 12 blocks reports `rust-sha2` at roughly
`c-openssl`'s speed — a number true of neither architecture.

**Same backend does not mean same speed.** The six OpenSSL front-ends converge
within 1.009× at 1 MiB but spread **4.538×** at 64 B (`c-openssl` 412 ns vs
`ruby-openssl` ~1870 ns). At small messages the front-end's per-call overhead —
allocation, FFI, object churn — dominates the primitive entirely. Any claim that
"backend determines performance" is a statement about message size.

## Leaderboards

Computed per architecture and message size in `summary.json` under
`strata.<arch>.leaderboards`.

| Board | Question |
|---|---|
| production | Fastest normal API in an ecosystem (native accel OK) |
| native | Ecosystem-owned impl, not a foreign crypto wrap |
| portable | No SHA-NI / arch asm |
| pure-language | Mostly written in the named language |
| reference | Pedagogical clarity |

## Quick start

Requires: `uv`, a C compiler, OpenSSL headers (`libssl-dev` / Homebrew `openssl`), Rust (`cargo`), Go, Node, Java JDK.

On macOS with Homebrew OpenSSL:

```bash
export PKG_CONFIG_PATH="$(brew --prefix openssl)/lib/pkgconfig"
export PATH="/opt/homebrew/opt/openjdk@21/bin:$PATH"   # if needed
```

```bash
uv sync
uv run sha256-atlas fingerprint
uv run sha256-atlas build
uv run sha256-atlas audit          # which binaries ship a hardware SHA-256 path
uv run sha256-atlas correctness --cases 1000 --skip-million
uv run sha256-atlas bench --reps 3 --max-size 65536 -o results/local-bench.json
# or one shot:
uv run sha256-atlas campaign --reps 3 --cases 1000 --max-size 65536 --skip-million
uv run sha256-atlas summarize results/latest/blocks/*/bench.json.gz --markdown
```

## Adding an implementation

1. Add a runner under `implementations/<id>/` obeying the CLI contract (`hash`, `verify`, `bench`), using the shared warmup budget
2. Register it in `registry/implementations.yaml` with provenance, backend, and status
3. Open a PR — CI builds, verifies, and benches it interleaved with the rest

Currently admitted: **19** implementations across C, Rust, Go, Python, JavaScript (Node/Bun), Ruby, PHP, Java, and Zig — spanning OpenSSL, BoringSSL, libsodium, mbedTLS, ring, RustCrypto, Bouncy Castle, Go stdlib, Zig stdlib, and reference paths.

## Correctness and its oracle

The gate runs 10,021 cases: NIST/FIPS vectors, padding-boundary messages, and PRNG
messages up to 4 KiB. Only the **5 NIST vectors are externally published ground
truth**; the rest are checked against `hashlib`, which is itself usually OpenSSL, so
they cannot detect an error shared with the oracle. The independent evidence is
unanimity: 19 implementations across 12 distinct backends agreeing digest-for-digest
on every case. `correctness.json` states this split explicitly rather than implying
independence it doesn't have.

## Claims this repo will and will not make

**Will:** On architecture \(A\), implementation \(X\) beat \(Y\) at size \(n\) in
\(k/k\) blocks, with median on-machine ratio \(R\). These sentences are generated
from the paired data, not written by hand — see `strata.<arch>.claims` in
`summary.json`.

**Will not:** Absolute ns/op on a specific unnamed Azure host as a hardware datasheet;
any figure pooled across architectures; any ranking whose supporting observations
are not in `results/latest/blocks/`.
