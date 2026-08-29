from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .campaign import run_campaign
from .paths import repo_root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sha256-atlas",
        description="SHA-256 Benchmark Atlas: build, verify, and comparatively bench implementations.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Repository root (default: auto-detect)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_fp = sub.add_parser("fingerprint", help="Print environment fingerprint JSON")
    p_fp.add_argument("-o", "--output", type=Path, default=None)

    p_build = sub.add_parser("build", help="Build admitted implementations")
    p_build.add_argument("--ids", nargs="*", default=None, help="Subset of implementation ids")

    p_ok = sub.add_parser("correctness", help="Run correctness gate")
    p_ok.add_argument("--ids", nargs="*", default=None)
    p_ok.add_argument("--cases", type=int, default=10_000, help="PRNG differential cases")
    p_ok.add_argument("--skip-million", action="store_true", help="Skip million-a NIST vector")

    p_bench = sub.add_parser("bench", help="Interleaved comparative benchmark on this machine")
    p_bench.add_argument("--ids", nargs="*", default=None)
    p_bench.add_argument("--sizes", nargs="*", type=int, default=None)
    p_bench.add_argument("--reps", type=int, default=5)
    p_bench.add_argument("--seed", type=int, default=1)
    p_bench.add_argument("--max-size", type=int, default=1_048_576, help="Skip larger sizes")
    p_bench.add_argument("-o", "--output", type=Path, default=None)

    p_run = sub.add_parser("campaign", help="Fingerprint + build + correctness + bench")
    p_run.add_argument("--ids", nargs="*", default=None)
    p_run.add_argument("--reps", type=int, default=5)
    p_run.add_argument("--seed", type=int, default=1)
    p_run.add_argument("--cases", type=int, default=10_000)
    p_run.add_argument("--max-size", type=int, default=1_048_576)
    p_run.add_argument("--skip-million", action="store_true")
    p_run.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for fingerprint/correctness/bench JSON (default: results/<stamp>)",
    )
    p_run.add_argument("--shard", type=int, default=0)
    p_run.add_argument("--shards", type=int, default=1)

    p_sum = sub.add_parser("summarize", help="Summarize one or more bench result JSON files")
    p_sum.add_argument("paths", nargs="+", type=Path)
    p_sum.add_argument("-o", "--output", type=Path, default=None)
    p_sum.add_argument(
        "--markdown",
        action="store_true",
        help="Print a compact Markdown digest instead of raw JSON",
    )
    p_sum.add_argument(
        "--fail-on-digest-disagreement",
        action="store_true",
        help="Exit non-zero if any timed-path digest disagreement is present",
    )

    p_arch = sub.add_parser(
        "archive",
        help="Store raw per-block observations as the committed evidence archive",
    )
    p_arch.add_argument("block_dirs", nargs="+", type=Path)
    p_arch.add_argument("-o", "--output-dir", type=Path, required=True)

    args = parser.parse_args(argv)
    root = args.root or repo_root()

    if args.cmd == "fingerprint":
        from .fingerprint import collect_fingerprint, write_fingerprint

        fp = collect_fingerprint()
        if args.output:
            write_fingerprint(args.output, fp)
        else:
            import json

            print(json.dumps(fp, indent=2, sort_keys=True))
        return 0

    if args.cmd == "build":
        from .build import build_all

        results = build_all(root, ids=args.ids)
        failed = [r for r in results if not r.ok]
        for r in results:
            status = "ok" if r.ok else "FAIL"
            print(f"[{status}] {r.id}: {r.detail}")
        return 1 if failed else 0

    if args.cmd == "correctness":
        from .correctness import run_correctness

        report = run_correctness(
            root,
            ids=args.ids,
            prng_cases=args.cases,
            skip_million=args.skip_million,
        )
        import json

        print(json.dumps(report, indent=2))
        return 0 if report["passed"] else 1

    if args.cmd == "bench":
        from .bench import run_interleaved_bench

        result = run_interleaved_bench(
            root,
            ids=args.ids,
            sizes=args.sizes,
            reps=args.reps,
            seed=args.seed,
            max_size=args.max_size,
            output=args.output,
        )
        import json

        print(json.dumps({"observations": len(result["observations"]), "path": result.get("path")}))
        return 0

    if args.cmd == "campaign":
        return run_campaign(
            root,
            ids=args.ids,
            reps=args.reps,
            seed=args.seed,
            cases=args.cases,
            max_size=args.max_size,
            skip_million=args.skip_million,
            output_dir=args.output_dir,
            shard=args.shard,
            shards=args.shards,
        )

    if args.cmd == "archive":
        import json

        from .archive import archive_blocks

        manifest = archive_blocks(args.block_dirs, args.output_dir)
        print(json.dumps(manifest, indent=2))
        return 0 if manifest["block_count"] else 1

    if args.cmd == "summarize":
        import json

        from .analysis import render_markdown, summarize_files

        summary = summarize_files(args.paths, root=root)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(render_markdown(summary) if args.markdown else json.dumps(summary, indent=2))

        agreement = summary["digest_agreement"]
        if args.fail_on_digest_disagreement and not agreement["ok"]:
            print(
                f"FAIL: {agreement['disagreement_count']} timed-path digest "
                "disagreement(s); benchmark measurements are not trustworthy.",
                file=sys.stderr,
            )
            return 1
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
