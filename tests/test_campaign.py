from pathlib import Path
from types import SimpleNamespace

import pytest

from sha256_benchmark_atlas.campaign import run_campaign


@pytest.mark.parametrize("kwargs", [{"reps": 0}, {"max_size": -1}, {"cases": -1}, {"ids": []}])
def test_campaign_rejects_invalid_arguments_before_output(tmp_path: Path, kwargs: dict) -> None:
    with pytest.raises(ValueError):
        run_campaign(tmp_path, output_dir=tmp_path / "out", **kwargs)
    assert not (tmp_path / "out").exists()


def test_campaign_returns_nonzero_for_failed_bench(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("sha256_benchmark_atlas.campaign.write_fingerprint", lambda *_: None)
    monkeypatch.setattr(
        "sha256_benchmark_atlas.campaign.build_all",
        lambda *_args, **_kwargs: [SimpleNamespace(id="python-hashlib", ok=True, detail="ok")],
    )
    monkeypatch.setattr(
        "sha256_benchmark_atlas.campaign.audit_all",
        lambda *_args, **_kwargs: {
            "with_hardware_path": 0,
            "audited": 0,
            "arch": "test",
            "skipped": 0,
        },
    )
    monkeypatch.setattr(
        "sha256_benchmark_atlas.campaign.run_correctness",
        lambda *_args, **_kwargs: {
            "implementations": [{"id": "python-hashlib", "ok": True, "checked": 1, "failed": 0}]
        },
    )
    monkeypatch.setattr(
        "sha256_benchmark_atlas.campaign.run_interleaved_bench",
        lambda *_args, **_kwargs: {
            "observations": [{"ok": True}],
            "digest_agreement": {"ok": False},
        },
    )
    assert (
        run_campaign(
            Path(__file__).parents[1], ids=["python-hashlib"], cases=0, output_dir=tmp_path / "out"
        )
        == 1
    )


def test_campaign_returns_zero_for_valid_single_runner(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("sha256_benchmark_atlas.campaign.write_fingerprint", lambda *_: None)
    monkeypatch.setattr(
        "sha256_benchmark_atlas.campaign.build_all",
        lambda *_args, **_kwargs: [SimpleNamespace(id="python-hashlib", ok=True, detail="ok")],
    )
    monkeypatch.setattr(
        "sha256_benchmark_atlas.campaign.audit_all",
        lambda *_args, **_kwargs: {
            "with_hardware_path": 0,
            "audited": 0,
            "arch": "test",
            "skipped": 0,
        },
    )
    monkeypatch.setattr(
        "sha256_benchmark_atlas.campaign.run_correctness",
        lambda *_args, **_kwargs: {
            "implementations": [{"id": "python-hashlib", "ok": True, "checked": 1, "failed": 0}]
        },
    )
    monkeypatch.setattr(
        "sha256_benchmark_atlas.campaign.run_interleaved_bench",
        lambda *_args, **_kwargs: {
            "observations": [{"ok": True}],
            "digest_agreement": {"ok": True, "cells_checked": 0},
        },
    )
    assert (
        run_campaign(
            Path(__file__).parents[1], ids=["python-hashlib"], cases=0, output_dir=tmp_path / "out"
        )
        == 0
    )
