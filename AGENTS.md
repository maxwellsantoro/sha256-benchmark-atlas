# Agent guide — SHA-256 Benchmark Atlas

Public atlas of SHA-256 implementations: correctness first, then comparative
performance with explicit provenance. Not a “fastest language” shootout.

## Layout

| Path | Role |
|---|---|
| `src/sha256_benchmark_atlas/` | Harness: CLI, build, correctness, bench, analysis, audit, cost model |
| `implementations/<id>/` | One runner per candidate (shared CLI contract) |
| `registry/implementations.yaml` | Admitted/excluded registry + message sizes + leaderboards |
| `vectors/nist.json` | NIST/FIPS short-message vectors |
| `results/latest/` | Published campaign evidence (`blocks/` + `summary.json`) |
| `tests/` | Unit tests (do not require full multi-language toolchains) |
| `PAIN.md` | Empirical pain log for a future general harness |

CLI entry: `uv run sha256-atlas …`

## Runner contract

Every implementation under `implementations/<id>/` must expose:

```text
hash                 # stdin bytes → hex digest on stdout
verify               # batch: [u32 BE length][msg]… → one hex digest per line
bench SIZE ITERS [SEED]
                     # → JSON {"ns_total","hashes","size","digest"}
```

Timing loops run **inside** the candidate process. Warmup is a shared time budget
(200 ms, capped at 100k iterations), not a fixed iteration count.

## Registry schema (`registry/implementations.yaml`)

Provenance model:

```text
language interface → library → implementation → backend → CPU path
```

Important fields per implementation: `id`, `status` (`admitted` / `excluded` /
`discovered` / `broken` / …), `backend`, `hardware_acceleration`, `leaderboards`,
`build` / `binary` (or interpreter + script), optional `audit_artifact_cmd` for
interpreted front-ends.

`message_sizes_bytes` must only list sizes a default campaign actually runs.

## Analysis rules (do not violate)

1. **Never pool architectures.** Report x86_64 and aarch64 (etc.) separately.
2. **Ratios are within-block only.** Form `T_A/T_B` on one host; do not divide
   pooled medians across hosts.
3. **Timed-path digests must agree** across runners for the same (size, rep, seed).
4. Claims are generated sentences under `strata.<arch>.claims` — do not invent
   absolute ns/op datasheet claims for unnamed cloud hosts.

Summary schema version is `3` (`analysis.SCHEMA_VERSION`). Keep
`results/latest/meta.json`’s `summary_schema_version` in sync when re-aggregating.

## Cost model & capability audit

- `costmodel`: affine fit `ns = a + b · ceil((n+9)/64)` → fixed cost `a` vs per-block `b`.
- `capability_audit`: static objdump mnemonic counts for hardware SHA paths;
  cross-checked against fitted `b` in `summary.json` (`audit_measurement_conflicts`).

## Adding an implementation

1. Add `implementations/<id>/` obeying the runner contract (shared warmup budget).
2. Register it in `registry/implementations.yaml` with provenance and `status`.
3. Extend tests if the registry/analysis contract grows.
4. Open a PR — lightweight CI runs pytest/ruff; campaign workflow builds and benches.

## Local commands

```bash
uv sync --extra dev
uv run ruff check src tests
uv run ruff format --check src tests
uv run pytest -q
uv run sha256-atlas campaign --reps 3 --cases 1000 --max-size 65536 --skip-million
```

Full multi-language campaigns need C/OpenSSL, Rust, Go, Node, Java, Ruby, PHP,
Bun, Zig, libsodium, mbedTLS — see README quick start (macOS OpenSSL `PKG_CONFIG_PATH`).

## Claims discipline

**Will:** On arch A, X beat Y at size n in k/k blocks with median on-machine ratio R
(backed by `results/latest/blocks/`).

**Will not:** Architecture-pooled rankings; absolute ns/op as hardware datasheets;
rankings without archived raw observations.
