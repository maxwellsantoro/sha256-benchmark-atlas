#!/usr/bin/env python3
"""Thin wrapper: uv run python analysis/summarize.py results/*/bench.json"""
from __future__ import annotations

import sys
from pathlib import Path

# Prefer installed package
try:
    from sha256_benchmark_atlas.analysis import summarize_files
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from sha256_benchmark_atlas.analysis import summarize_files

import json


def main() -> int:
    paths = [Path(p) for p in sys.argv[1:]]
    if not paths:
        print("usage: summarize.py RESULT_BENCH_JSON...", file=sys.stderr)
        return 2
    print(json.dumps(summarize_files(paths), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
