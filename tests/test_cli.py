from pathlib import Path

import pytest
import yaml

from sha256_benchmark_atlas import cli


def test_bench_cli_returns_nonzero_for_failed_result(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "sha256_benchmark_atlas.bench.run_interleaved_bench",
        lambda _root, **_: {"observations": [{"ok": False}], "digest_agreement": {"ok": True}},
    )
    assert cli.main(["--root", str(tmp_path), "bench", "--sizes", "1"]) == 1


def test_bench_cli_returns_nonzero_for_disagreement(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "sha256_benchmark_atlas.bench.run_interleaved_bench",
        lambda _root, **_: {
            "observations": [{"ok": True}],
            "digest_agreement": {"ok": False},
        },
    )
    assert cli.main(["--root", str(tmp_path), "bench", "--sizes", "1"]) == 1


def test_bench_cli_accepts_valid_single_runner_result(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "sha256_benchmark_atlas.bench.run_interleaved_bench",
        lambda _root, **_: {
            "observations": [{"ok": True}],
            "digest_agreement": {"ok": True, "cells_checked": 0},
        },
    )
    assert cli.main(["--root", str(tmp_path), "bench", "--sizes", "1"]) == 0


def test_bench_cli_reports_argument_error_before_work(tmp_path: Path) -> None:
    assert cli.main(["--root", str(tmp_path), "bench", "--reps", "0"]) == 2


@pytest.mark.parametrize("command", ["bench", "campaign"])
@pytest.mark.parametrize("sizes", [[-1], [True], ["64"], []])
def test_invalid_registry_sizes_fail_before_runner_work(monkeypatch, tmp_path, command, sizes):
    (tmp_path / "registry").mkdir()
    (tmp_path / "registry/implementations.yaml").write_text(
        yaml.safe_dump(
            {
                "message_sizes_bytes": sizes,
                "implementations": [{"id": "fake", "status": "admitted", "binary": "missing"}],
            }
        )
    )

    def forbidden(*args, **kwargs):
        pytest.fail("invalid registry must fail before external work")

    monkeypatch.setattr("sha256_benchmark_atlas.bench.bench_once", forbidden)
    monkeypatch.setattr("sha256_benchmark_atlas.campaign.write_fingerprint", forbidden)
    assert cli.main(["--root", str(tmp_path), command]) == 2
