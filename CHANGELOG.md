# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-08-29

### Added

- Public SHA-256 implementation atlas with shared runner contract (`hash` / `verify` / `bench`)
- Registry-driven harness (`sha256-atlas`): fingerprint, build, correctness, bench, campaign
- Stratified-by-architecture summarization (summary schema 3) with within-block ratios and claims
- Affine cost model (`a` fixed / `b` per 64-byte block) and residual / steady-state flags
- Static capability audit (objdump SHA mnemonic counts) with timing cross-checks
- Gzipped per-block evidence archive under `results/latest/blocks/`
- GitHub Actions campaign matrix (10× x86_64 + 2× aarch64) with aggregate publish
- Lightweight CI workflow for pytest + ruff on push/PR
- Agent guide (`AGENTS.md`) and empirical harness pain log (`PAIN.md`)

### Notes

- First tagged release baseline. Campaign figures in the README correspond to
  published `results/latest/` evidence; re-run the campaign workflow to refresh.
