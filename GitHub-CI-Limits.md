> From: https://chatgpt.com/c/6a8faf2e-b618-83ea-b5e4-ee896ffd5531

# you asked

message time: 2026-08-26 23:29:50

if your project is public on github, what are the limits to CI / compute usage?

---

# chatgpt response

For a public GitHub project, the practical answer is surprisingly generous: standard GitHub-hosted CI is generally free, but there are still hard limits on job duration, concurrency, storage, and specialized/larger runners. I’m checking the current GitHub limits so I can separate “free” from “unlimited.”

Yes. For a **public GitHub repository, standard GitHub Actions runners are effectively an unusually large pool of free CI compute**. GitHub explicitly says their use is **“free and unlimited”** for public repos. There is no monthly Actions-minute quota for those standard runners. ([GitHub Docs](https://docs.github.com/en/actions/reference/runners/github-hosted-runners))

The important distinction is that **unlimited minutes ≠ unlimited instantaneous compute**.

| Limit | Current GitHub limit |
|---|---:|
| Standard Linux public runner | **4 vCPU, 16 GB RAM, 14 GB SSD** |
| Standard Windows public runner | **4 vCPU, 16 GB RAM, 14 GB SSD** |
| ARM Linux public runner | **4 vCPU, 16 GB RAM, 14 GB SSD** |
| macOS Intel | **4 CPU, 14 GB RAM** |
| macOS ARM/M1 | **3 CPU, 7 GB RAM** |
| Maximum normal hosted job duration | **6 hours** |
| Maximum workflow-run lifetime | **35 days** |
| Maximum matrix jobs per workflow | **256** |
| Concurrent standard jobs — GitHub Free | **20** |
| Concurrent standard jobs — GitHub Pro | **40** |
| Concurrent standard jobs — Team | **60** |
| Concurrent standard jobs — Enterprise | **500** |
| Max concurrent macOS jobs, Free/Pro/Team | **5** |
| Default cache | **10 GB/repository** |

([GitHub Docs](https://docs.github.com/en/actions/reference/runners/github-hosted-runners))

So, for example, a GitHub Free account owning public repositories can in principle have:

**20 jobs × 4 vCPUs = ~80 vCPUs running simultaneously.**

If you kept the queue populated for 24 hours, that's theoretically:

$$
80\ \mathrm{vCPU}\times24\mathrm{h}
=
1,920\ \mathrm{vCPU\!-\!hours/day}.
$$

And because public-repo standard-runner minutes don't have a monthly quota, there isn't a rule saying “you've consumed your 2,000 minutes, stop.” That 2,000-minute figure associated with GitHub Free is relevant to metered usage such as private repositories, not standard hosted execution in public repositories. ([GitHub Docs](https://docs.github.com/en/billing/concepts/product-billing/github-actions?_fsi=LlxUgcTQ&utm_source=chatgpt.com))

There are a few major catches.

**1. Each job dies after six hours.** You can divide a long computation into shards/checkpoints and schedule subsequent jobs, but no individual GitHub-hosted standard job can exceed six hours. A matrix can contain up to 256 jobs, though only your concurrency allowance runs at once. ([GitHub Docs](https://docs.github.com/en/actions/reference/limits))

**2. “Unlimited” is still subject to GitHub's acceptable-use rules.** This is probably the most important qualification. GitHub says hosted Actions must relate to the **production, testing, deployment, or publication of the software project in that repository**. It expressly prohibits cryptomining and also prohibits workloads that put a burden on GitHub disproportionate to their benefit, such as using Actions as generic serverless infrastructure. GitHub can terminate jobs or restrict accounts/repositories for misuse. ([GitHub Docs](https://docs.github.com/en/site-policy/github-terms/github-terms-for-additional-products-and-features?utm_source=chatgpt.com))

That means things like these are naturally defensible:

- compiling a large Rust/C++/Lean project;
- running a huge test matrix;
- fuzzing the project's implementation;
- executing correctness/property tests;
- reproducing experiments that are actually part of the repository;
- benchmarking implementations maintained by the repository;
- building proofs, datasets, generated test vectors, releases, etc.

Where it gets questionable is creating a nominal public repo whose real purpose is simply **“give me 80 free CPUs for arbitrary computation.”**

**3. Bigger/GPU runners aren't free.** GitHub's “larger runners,” including GPU machines, are billed **even for public repositories**. Included Actions minutes cannot be applied to them. ([GitHub Docs](https://docs.github.com/en/actions/concepts/runners/larger-runners?utm_source=chatgpt.com))

**4. Storage isn't unlimited.** The compute-minutes exemption shouldn't be confused with artifact retention. The normal account allowances still apply to Actions artifact/package storage: GitHub Free has 500 MB, Pro 1 GB, Team 2 GB, Enterprise 50 GB. Dependency caches get **10 GB per repository by default**, with old caches subject to eviction. ([GitHub Docs](https://docs.github.com/en/actions/reference/limits))

One particularly interesting consequence is that **public open-source projects get better standard Linux machines than private repositories**: the public `ubuntu-latest` machine is currently **4 CPU / 16 GB**, whereas the corresponding standard private runner is **2 CPU / 8 GB**. ([GitHub Docs](https://docs.github.com/en/actions/reference/runners/github-hosted-runners))

### For your kinds of projects

There is quite a lot you could legitimately exploit here.

A public project doing formal verification, reproducibility testing, cross-language correctness, benchmarking, fuzzing, or exhaustive finite searches could structure its CI as, say, a **20-way matrix**, where each shard receives 4 CPUs and 16 GB. On GitHub Free that's roughly an **80-vCPU ephemeral cluster**, and on GitHub Pro the concurrency ceiling rises to 40 standard jobs, i.e. roughly **160 simultaneous vCPUs** assuming Linux runners. ([GitHub Docs](https://docs.github.com/en/actions/reference/limits))

You could also make jobs restartable:

$$
\text{problem}
\rightarrow
\{S_0,\ldots,S_{255}\}
\rightarrow
\text{independent CI shards}
\rightarrow
\text{content-addressed results}
\rightarrow
\text{verification/aggregation}.
$$

That architecture is particularly natural for exhaustive tests, proof compilation, property searches, adversarial test campaigns, and reproducibility campaigns.

There is one thing I **wouldn't** use these runners for as primary evidence: precision performance benchmarking. They are excellent for checking that a benchmark executes and for broad regression detection, but ephemeral cloud VMs aren't a sufficiently controlled hardware environment for strong claims like “implementation A is 3.7% faster than B.” For something like Benchmarkour, I'd treat GitHub Actions as a **free correctness/reproducibility fleet**, while requiring controlled/self-hosted hardware for high-confidence performance claims.

So the surprising summary is:

> **Public repo + ordinary GitHub-hosted Actions = no compute-minute bill and no monthly compute quota. Your real ceilings are concurrency, six-hour jobs, runner size, storage, and legitimate-project-use policy.**

And at the GitHub Free tier, that amounts to a potential **20 × (4 CPU / 16 GB)** parallel fleet—which is considerably more useful than the phrase “free CI” makes it sound. ([GitHub Docs](https://docs.github.com/en/actions/reference/runners/github-hosted-runners))

---

# you asked

message time: 2026-08-26 23:38:56

But isn't the hardware very much always the same across them?

---

# chatgpt response

Yes — **much more standardized than my previous answer implied**.

For a given runner label such as `ubuntu-24.04`, GitHub guarantees essentially the same *machine class*: public-repo jobs currently get **4 vCPUs, 16 GB RAM, 14 GB SSD, x64**, and every job gets a fresh VM. ([GitHub Docs](https://docs.github.com/en/actions/reference/runners/github-hosted-runners?utm_source=chatgpt.com))

The distinction is:

> **same nominal hardware envelope ≠ guaranteed same physical processor.**

GitHub documents the vCPU count, RAM, storage, architecture, and image, but does **not** promise that every `ubuntu-24.04` invocation lands on the exact same CPU model, stepping, physical host, cache topology, or host load. Linux/Windows runners are backed by Azure infrastructure. ([GitHub Docs](https://docs.github.com/en/actions/reference/runners/github-hosted-runners?utm_source=chatgpt.com))

So I would revise my assessment of their benchmarking value upward quite a bit.

### The really useful trick

Suppose Benchmarkour wants to compare:

$$
A,\ B,\ C,\ D
$$

Instead of doing:

```text
job 1: benchmark A
job 2: benchmark B
job 3: benchmark C
job 4: benchmark D
```

you do:

```text
job 1:
    inspect CPU/environment
    A B C D A B C D ... interleaved

job 2:
    inspect CPU/environment
    D C B A D C B A ...

...

job N
```

Now **all competitors within an observation block are executing on the same VM and physical host**.

Host-to-host speed variation largely becomes a nuisance variable rather than a confounder:

$$
T_{i,j}
=
H_i \cdot P_j + \epsilon_{i,j}
$$

where $H_i$ is “how fast this particular runner happens to be” and $P_j$ is implementation performance.

If you care about the ratio

$$
R_i=\frac{T_{i,A}}{T_{i,B}},
$$

most of $H_i$ cancels.

That is a **far better experimental design** than independently timing A and B on arbitrary cloud instances.

### And you can fingerprint every runner

At the beginning of every job, record things like:

```bash
lscpu
cat /proc/cpuinfo
uname -a
free -h
lsblk
```

plus CPUID feature flags, kernel, runner-image version, compiler versions, CPU governor information available to you, etc.

Interestingly, OpenAI's Codex repository itself has Actions steps that print the CPU model, logical CPU count, RAM and OS from its runners. ([GitHub](https://github.com/openai/codex/actions/runs/25173051966/workflow?utm_source=chatgpt.com))

So Benchmarkour could turn an otherwise annoying property into part of the dataset:

$$
\boxed{
(\text{implementation},\text{workload},\text{CPU identity},\text{runner image})
\rightarrow \text{performance}
}
$$

rather than pretending every machine is identical.

## This actually makes GitHub Actions pretty compelling

Imagine a public Benchmarkour campaign using your 20 concurrent jobs.

Each job receives:

**4 vCPU + 16 GB**

and performs, say:

- 4 implementations;
- 10 input sizes;
- randomized/interleaved execution;
- 30 repetitions;
- environment fingerprint;
- correctness oracle;
- raw timing distributions.

Twenty independent runner VMs then give you **20 machine-level experimental blocks simultaneously**.

Instead of seeing runner variation as garbage, you get replication:

$$
R_1,R_2,\ldots,R_{20}.
$$

Then ask:

$$
P(T_A<T_B)
$$

**across machines**, rather than merely:

> “A happened to win on my laptop.”

That's arguably *stronger* evidence for a portable performance claim.

You could even stratify the result if CPU models differ:

```text
AMD EPYC xxxx:
    A/B = 0.81 [0.79, 0.83]

Intel Xeon xxxx:
    A/B = 0.86 [0.84, 0.88]

all observed GHA runners:
    A wins 39 / 40 blocks
```

That's excellent Benchmarkour evidence.

### What GitHub Actions still can't establish

I'd distinguish two claim types.

**Excellent fit:**

> “On the population of GitHub's public Ubuntu runners observed in this campaign, A is faster than B by X–Y%, with 20/20 independent runner blocks agreeing.”

That's rigorous and reproducible.

**Not justified:**

> “A takes 3.217 ns/op on an Intel Xeon 8370C.”

You don't control enough of the physical machine for that absolute hardware characterization: exact host, turbo state, neighboring VM activity, thermal conditions, etc.

And GitHub only guarantees the resource specification, **not an exact CPU model**. ([GitHub Docs](https://docs.github.com/en/actions/reference/runners/github-hosted-runners?utm_source=chatgpt.com))

But for **comparative benchmarking**, that's much less damaging when candidates run back-to-back/interleaved on one VM.

So yes: your intuition is right. I was too dismissive of GitHub Actions as a Benchmarkour measurement substrate.

In fact, there's an interesting possibility here:

$$
\boxed{\text{GitHub Actions itself becomes Benchmarkour's first standardized public testbed}}
$$

A public project could offer a **zero-cost, massively replicated, independently provisioned benchmarking tier**, with every runner treated as an experimental block and its actual hardware fingerprint becoming part of the immutable evidence bundle.

For the kind of system you've been designing, that is potentially **very valuable**, not merely useful for CI.

---

# you asked

message time: 2026-08-26 23:41:36

It could be interesting before we build that, to make a public repo that is a straightforward test of all of the implementations of something we can find in all languages, like SHA-256 or arbitrary precision arithmetic, and compare speed and accuracy etc across ALL of them.

---

# chatgpt response

Yes — and I think doing this *before* Benchmarkour is a strong move. The useful version would be deliberately simple: one public repo, one operation family, many implementations, one transparent harness, and raw results anyone can reproduce or dispute.

The key design choice is to **benchmark implementations, not “languages.”** Python `hashlib`, Node `crypto`, and a C program calling OpenSSL may all ultimately execute closely related native crypto code; treating them as three language implementations would produce a misleading leaderboard. The repo should make that provenance explicit.

Yes. I think this is probably the **right experiment to build before Benchmarkour itself**.

It would be useful in its own right, while also forcing us to encounter the exact problems Benchmarkour is supposed to solve—equivalence, provenance, measurement boundaries, hardware variation, statistical treatment, reproducibility—without first designing a generalized framework in the abstract.

I would start with **SHA-256**, not arbitrary-precision arithmetic.

### Why SHA-256 is almost an ideal first target

SHA-256 gives us an unusually clean experimental contract:

$$
f:\{0,1\}^*\rightarrow\{0,1\}^{256}.
$$

There isn't really an "accuracy" continuum. An implementation either returns the correct 256 bits or it doesn't. We can test official/reference vectors plus millions of deterministic generated cases.

And virtually every serious language ecosystem exposes it.

There is already partial work in this direction—a repo specifically compares Node, OpenSSL and Go SHA implementations, for example—but not the exhaustive, provenance-conscious, cross-ecosystem experiment we're describing. ([GitHub](https://github.com/benduncan/sha-benchmark-avx-simd-native?utm_source=chatgpt.com)) GitHub alone has hundreds/thousands of repositories tagged around SHA-256, so there is a huge implementation population to draw from. ([GitHub](https://github.com/topics/sha-256?o=desc&s=updated&utm_source=chatgpt.com))

The really important conceptual move would be:

> **Do not make a "fastest programming language" benchmark. Make an atlas of SHA-256 implementations.**

Because the former would often be nonsense.

Python's `hashlib` can use OpenSSL implementations. ([Python documentation](https://docs.python.org/3/library/hashlib.html?utm_source=chatgpt.com)) Node's `node:crypto` is explicitly a wrapper around OpenSSL's crypto functions. ([Node.js](https://nodejs.org/api/crypto.html?utm_source=chatgpt.com)) Go, on the other hand, has its own SHA-256 machinery and architecture-specific implementation infrastructure. ([Go](https://go.dev/src/crypto/sha256/sha256.go?utm_source=chatgpt.com))

So we might discover something like:

```text
Python / hashlib ─────┐
Node / crypto ────────┼──> OpenSSL SHA-256 ──> SHA-NI implementation
Ruby / OpenSSL ───────┘

C / OpenSSL ─────────────> OpenSSL SHA-256 ──> SHA-NI implementation

Go / crypto/sha256 ──────> Go implementation ─> amd64 optimized implementation

Rust / sha2 ─────────────> RustCrypto SHA-2
Rust / ring ─────────────> ring implementation
Rust / openssl crate ────> OpenSSL
```

That graph is arguably **more interesting than the leaderboard**.

A naive result could say:

> C: 6.1 GB/s  
> Python: 6.0 GB/s  
> Node: 5.9 GB/s

and conclude that Python is nearly as fast as C at SHA-256.

Our repo would instead explain:

> You're substantially measuring three front ends to the same highly optimized native primitive.

That alone would make the project valuable.

## I would structure the population along two axes

First, **language/ecosystem**:

C, C++, Rust, Zig, Go, Java, Kotlin, Scala, C#, F#, Swift, D, Nim, Haskell, OCaml, Fortran, Ada, Pascal, Python/CPython, PyPy, JavaScript/Node, Bun, Deno, Ruby, PHP, Perl, Lua, LuaJIT, Julia, Erlang, Elixir, R, etc.

Then, within an ecosystem, **every meaningful implementation** rather than one representative:

```text
Rust
    std-ish ecosystem
    sha2 / RustCrypto
    ring
    openssl
    pure implementations
    SIMD implementations

C/C++
    OpenSSL
    BoringSSL
    LibreSSL
    libsodium
    Crypto++
    Botan
    mbedTLS
    wolfSSL
    reference/simple C implementations

Java
    JDK MessageDigest providers
    Bouncy Castle
    other providers

Python
    hashlib
    cryptography/OpenSSL
    pure Python implementations
    PyCryptodome
    etc.
```

And record provenance for every entry:

$$
\boxed{
\text{language interface}
\rightarrow
\text{library}
\rightarrow
\text{implementation}
\rightarrow
\text{backend}
\rightarrow
\text{CPU path}
}
$$

That last distinction becomes fascinating when SHA-NI is available.

---

# There should actually be several leaderboards

Putting everything into a single ranking would throw away much of the experiment.

I'd have at least:

**Default / production**

> What's the fastest normal SHA-256 API a programmer using this ecosystem would reasonably use?

Native libraries and CPU acceleration are allowed.

**Native implementation**

> Implementations actually belonging to that ecosystem rather than wrapping OpenSSL or another foreign library.

**Portable**

> No SHA extensions or architecture-specific assembly.

**Pure language**

> Implemented predominantly in the named language.

**Reference / pedagogical**

> Straightforward implementations emphasizing the SHA-256 algorithm itself.

Then something like Python can legitimately appear in several places:

```text
Python hashlib/OpenSSL     production
Python native extension X  production
pure Python SHA256         pure-language
```

Rather than pretending those are the same thing.

## The workload should expose the shape of SHA-256

Don't benchmark only 1 MB buffers.

Use deliberately chosen message lengths:

| Bytes | Why |
|---:|---|
| 0 | initialization/finalization |
| 1 | tiny-message overhead |
| 3 | familiar `abc` case |
| 32 | digest-sized |
| 55 | last one-block padded message |
| **56** | padding forces another block |
| 63 | block boundary −1 |
| **64** | exact SHA block |
| 65 | block boundary +1 |
| **80** | Bitcoin block-header size |
| 127 | 2 blocks −1 |
| 128 | 2 blocks |
| 256 | small payload |
| 1 KiB | medium |
| 4 KiB | page-ish |
| 64 KiB | throughput transition |
| 1 MiB | bulk |
| 16 MiB | sustained throughput |

The **55 → 56** discontinuity is especially valuable because SHA-256 padding changes the number of compression blocks there.

That means the result isn't merely:

> OpenSSL wins.

It becomes curves:

$$
T_I(n)
$$

for implementation $I$ and message size $n$.

We may see completely different winner regions:

```text
0–32 B       implementation A
33–512 B     implementation B
512 B–64 KB  implementation C
>64 KB       implementation D
```

Which is already basically the motivating idea behind Benchmarkour.

---

## And measure several different things

For small messages:

$$
\text{ns/hash}
$$

For bulk:

$$
\text{GB/s}
$$

Also:

- initialization cost;
- update cost;
- finalization cost;
- one-shot API;
- streaming API;
- allocations/hash where measurable;
- peak memory;
- binary/code size if interesting;
- build time as a secondary metric.

And separately:

$$
\textbf{correctness}.
$$

Every candidate must pass correctness **before its timing is admitted**.

I'd use:

1. published SHA-256 test vectors;
2. boundary-length vectors;
3. deterministic pseudo-random byte strings;
4. very long inputs;
5. streaming with randomly partitioned chunks;
6. one-shot vs streaming equality;
7. differential agreement among implementations.

You could make the test unusually aggressive because hashing is cheap.

Ten million correctness cases is not crazy when distributed over free CI.

---

# GitHub Actions becomes part of the experiment

And our previous conversation makes this particularly interesting.

Public Linux runners currently give **4 vCPU / 16 GB RAM** and standard hosted execution is free/unmetered for public repositories. ([GitHub Docs](https://docs.github.com/en/actions/reference/runners/github-hosted-runners?utm_source=chatgpt.com))

But I would **not** send one implementation to each runner.

I'd make a runner an experimental block:

```text
Runner R17

environment fingerprint
    CPU
    CPU flags
    kernel
    compiler versions
    runtime versions
    OpenSSL version
    ...

build all candidates

correctness gate

randomized blocks:

    Go
    OpenSSL
    RustCrypto
    Java
    Python/hashlib
    ...

    Python/hashlib
    Java
    OpenSSL
    Go
    RustCrypto
    ...

repeat
```

Therefore,

$$
R_{A/B,r}
=
\frac{T_{A,r}}{T_{B,r}}
$$

is an **on-machine comparison**.

Then GitHub gives us many independently provisioned experimental blocks:

$$
r_1,r_2,\ldots,r_{20}.
$$

That is far more defensible than comparing numbers copied from twenty different projects' READMEs.

### We'd fingerprint CPU features too

Because one of the most interesting dimensions will probably be:

```text
SHA-NI available
SHA-NI unavailable
AVX2
AVX-512
ARM crypto extensions
```

GitHub now exposes both x64 and ARM64 public Linux standard runners with the same nominal 4-vCPU/16-GB class. ([GitHub Docs](https://docs.github.com/en/actions/reference/runners/github-hosted-runners?utm_source=chatgpt.com))

So eventually:

$$
\text{x86-64}
\times
\text{ARM64}
\times
\text{implementation}
\times
\text{message size}.
$$

That's a serious dataset.

---

# Don't try to define "ALL" up front

I'd make **completeness itself auditable**.

Have a registry:

```yaml
id: rust-rustcrypto-sha2
language: rust
project: RustCrypto/hashes
package: sha2
version: ...
source_commit: ...
implementation_class: native
backend: rustcrypto
hardware_acceleration: auto
status: admitted
```

And maintain:

```text
DISCOVERED
ADMITTED
EXCLUDED
BROKEN
DUPLICATE_BACKEND
UNSUPPORTED_PLATFORM
```

with reasons.

Then the claim is not literally unknowable:

> “Every SHA-256 implementation on Earth.”

It's:

> **Every implementation in Benchmark SHA's public registry as of commit X, with the discovery and exclusion record included.**

People can PR missing ones.

That creates a fun dynamic:

> “Your favorite language/library isn't here? Add it.”

The repository gets better through adversarial participation.

---

# There is a second experiment hiding inside it

We can compare **ecosystem overhead against the underlying primitive**.

Suppose OpenSSL direct C gets:

$$
6.20\ \mathrm{GB/s}
$$

and Python `hashlib` gets:

$$
6.13
$$

while Node gets:

$$
6.06.
$$

Now normalize them:

$$
\eta
=
\frac{\text{front-end throughput}}
{\text{underlying backend throughput}}.
$$

For large buffers perhaps:

```text
C/OpenSSL       1.000
Python/OpenSSL  0.989
Node/OpenSSL    0.977
Ruby/OpenSSL    0.94
...
```

But at 1 byte:

```text
C/OpenSSL        1.00
Python/OpenSSL   0.18
Node/OpenSSL     0.08
...
```

That measures the **cost of crossing an abstraction boundary**.

That is legitimately interesting computer-systems research.

---

# Arbitrary precision should be project #2

It is potentially even richer, but considerably harder to make fair.

There are already strong intra-Rust BigInt comparisons showing how radically implementations diverge as operand size and operation change—for example comparing `rug`/GMP, Malachite, Dashu, `ibig`, and `num-bigint`. ([GitHub](https://github.com/DRMacIver/rust-bigint-benchmarks/blob/main/README.md?utm_source=chatgpt.com))

And that's exactly why it is attractive.

You'd have:

$$
T_{\text{impl}}(\text{operation},n,m,\text{operand structure})
$$

for:

```text
addition
subtraction
multiplication
division
mod
gcd
modular exponentiation
conversion decimal → integer
conversion integer → decimal
```

at:

```text
8 bits
64
128
256
512
1K
2K
4K
8K
16K
64K
1M...
```

Then you start seeing **algorithm transitions**:

schoolbook → Karatsuba → Toom-Cook → FFT-like multiplication, etc.

The winner map could be spectacular.

But SHA-256 lets us first solve the experimental infrastructure with essentially no semantic ambiguity.

---

# I would make this intentionally *not* Benchmarkour

That's important.

Something like:

```text
sha256-everywhere/
    implementations/
        c/
        cpp/
        rust/
        go/
        python/
        javascript/
        java/
        ...
    registry/
        implementations.yaml
    vectors/
    harness/
    results/
    analysis/
    .github/workflows/
```

The harness can initially be ugly and specific.

No generic adapter system.

No general schema language.

No arbitrary contracts.

No framework abstractions.

Just:

$$
\boxed{
\text{Can we rigorously answer:
“Which SHA-256 implementation is fastest where?”}
}
$$

Then, while building it, keep a file like:

```text
PAIN.md
```

Every time we encounter:

- incompatible build systems;
- ambiguous backend identity;
- JIT warmup;
- process startup;
- hardware dispatch;
- shared native libraries;
- compiler flags;
- environment drift;
- measurement boundaries;
- result provenance;
- statistical uncertainty;
- reproducibility;
- exclusion decisions;
- comparison families;
- evidence storage;

we write it down.

**That file becomes the empirical requirements document for Benchmarkour.**

There are existing broad cross-language benchmarks such as `benchLANG`, which currently covers many languages and pins toolchains, but it benchmarks general programming tasks rather than exhaustively studying one mathematical primitive and its implementation provenance. ([GitHub](https://github.com/GlebOlsen/benchLANG?utm_source=chatgpt.com)) That's a useful indication that the niche we're describing is distinct.

So I'd sequence the projects:

$$
\boxed{
\text{SHA-256 Everywhere}
\rightarrow
\text{BigInt Everywhere}
\rightarrow
\text{extract common machinery}
\rightarrow
\text{Benchmarkour}
}
$$

Rather than:

$$
\text{design Benchmarkour}
\rightarrow
\text{hope its abstractions were right}.
$$

And there is a nice philosophical fit: **Benchmarkour would itself emerge from two real benchmark campaigns**, with every abstraction justified by a concrete problem we actually encountered.

I think SHA-256 Everywhere could also become genuinely popular as a standalone public repo. The combination of *“every language,” “every implementation,” “live GitHub CI results,”* and *“add yours by PR”* is immediately understandable, while the backend/provenance graph gives it considerably more scientific substance than a typical language shootout.