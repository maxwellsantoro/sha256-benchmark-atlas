#!/usr/bin/env python3
"""Thin wrapper around `sha256-atlas summarize`.

    uv run python analysis/summarize.py results/latest/blocks/*/bench.json.gz
"""

from __future__ import annotations

import sys
from pathlib import Path

# Prefer the installed package.
try:
    from sha256_benchmark_atlas.analysis import render_markdown, summarize_files
except ImportError:  # pragma: no cover - source checkout without an install
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from sha256_benchmark_atlas.analysis import render_markdown, summarize_files

import json


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--markdown"]
    as_markdown = "--markdown" in sys.argv[1:]
    paths = [Path(p) for p in args]
    if not paths:
        print("usage: summarize.py [--markdown] RESULT_BENCH_JSON...", file=sys.stderr)
        return 2
    summary = summarize_files(paths)
    print(render_markdown(summary) if as_markdown else json.dumps(summary, indent=2))
    return 0 if summary["digest_agreement"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
