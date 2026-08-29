from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from sha256_benchmark_atlas.paths import repo_root
from sha256_benchmark_atlas.registry import Implementation, Registry, load_registry

FIXTURE = {
    "schema_version": 1,
    "message_sizes_bytes": [0, 64, 1024],
    "leaderboards": [{"id": "production", "description": "..."}],
    "implementations": [
        {"id": "a-admitted", "status": "admitted", "backend": "x", "binary": "a"},
        {"id": "b-admitted", "status": "admitted", "backend": "y", "binary": "b"},
        {"id": "c-excluded", "status": "excluded", "backend": "z", "binary": "c"},
        {"id": "d-discovered", "backend": "w", "binary": "d"},  # no status → default
    ],
}


def _registry(tmp_path: Path) -> Registry:
    (tmp_path / "registry").mkdir()
    (tmp_path / "registry" / "implementations.yaml").write_text(yaml.safe_dump(FIXTURE))
    return load_registry(tmp_path)


def test_message_sizes(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    assert reg.message_sizes == [0, 64, 1024]


def test_implementations_default_admitted_only(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    ids = {i.id for i in reg.implementations()}
    assert ids == {"a-admitted", "b-admitted"}


def test_implementations_all(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    ids = {i.id for i in reg.implementations(admitted_only=False)}
    assert ids == {"a-admitted", "b-admitted", "c-excluded", "d-discovered"}


def test_implementation_default_status_is_discovered() -> None:
    impl = Implementation({"id": "x", "binary": "x"})
    assert impl.status == "discovered"


def test_by_id_filters_and_preserves_admitted_gate(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    found = reg.by_id(["a-admitted"])
    assert [i.id for i in found] == ["a-admitted"]
    # excluded implementation is invisible even if explicitly requested,
    # because by_id filters through implementations(admitted_only=True) first
    with pytest.raises(KeyError):
        reg.by_id(["c-excluded"])


def test_by_id_none_returns_all_admitted(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    assert {i.id for i in reg.by_id(None)} == {"a-admitted", "b-admitted"}


def test_by_id_unknown_id_raises(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    with pytest.raises(KeyError, match="nope"):
        reg.by_id(["a-admitted", "nope"])


def test_registry_sizes_are_all_exercised_by_a_default_campaign() -> None:
    """A size the campaign never runs implies a claim the atlas does not make."""
    import inspect

    from sha256_benchmark_atlas.campaign import run_campaign

    default_max = inspect.signature(run_campaign).parameters["max_size"].default
    reg = load_registry(repo_root())
    assert reg.message_sizes, "registry declares no message sizes"
    assert max(reg.message_sizes) == default_max, (
        f"largest registry size {max(reg.message_sizes)} != campaign default "
        f"max_size {default_max}; one of the two is wrong"
    )


def test_version_provenance_points_at_real_fingerprint_keys() -> None:
    """`version_resolved_from` must name a key a fingerprint actually produces."""
    from sha256_benchmark_atlas.fingerprint import collect_fingerprint

    fp = collect_fingerprint()
    reg = load_registry(repo_root())

    for impl in reg.implementations(admitted_only=False):
        key = impl.raw.get("version_resolved_from")
        if key is None:
            continue
        section, _, name = str(key).partition(".")
        assert section in fp, f"{impl.id}: unknown fingerprint section {section!r}"
        assert name in fp[section], (
            f"{impl.id}: fingerprint section {section!r} has no key {name!r}"
        )


def test_every_admitted_implementation_declares_provenance() -> None:
    reg = load_registry(repo_root())
    for impl in reg.implementations():
        assert impl.raw.get("version"), f"{impl.id} has no version"
        assert impl.raw.get("backend"), f"{impl.id} has no backend"
        assert "version_resolved_from" in impl.raw, (
            f"{impl.id}: state where the version comes from, or null for a hard pin"
        )


def test_real_registry_ids_are_unique_and_admitted() -> None:
    """Sanity-check the actual project registry, not just fixtures."""
    root = repo_root()
    reg = load_registry(root)
    impls = reg.implementations(admitted_only=False)
    ids = [i.id for i in impls]
    assert len(ids) == len(set(ids)), "duplicate implementation ids in registry"

    admitted = reg.implementations(admitted_only=True)
    assert len(admitted) > 0
    for impl in admitted:
        assert impl.status == "admitted"
        assert impl.binary, f"{impl.id} has no binary path"
        # binary path must at least live under this implementation's own
        # source directory, even though the binary itself is a gitignored
        # build artifact that may not exist until `build` has run.
        impl_dir = root / "implementations" / impl.id
        assert impl_dir.is_dir(), f"{impl.id}: implementations/{impl.id}/ missing"
        assert Path(impl.binary).parts[:2] == ("implementations", impl.id), (
            f"{impl.id}: binary {impl.binary!r} not under implementations/{impl.id}/"
        )
