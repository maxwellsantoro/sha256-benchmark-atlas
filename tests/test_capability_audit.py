from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from sha256_benchmark_atlas import capability_audit as ca
from sha256_benchmark_atlas.capability_audit import (
    audit_implementation,
    count_sha256_instructions,
    cross_check,
)
from sha256_benchmark_atlas.registry import Implementation

ARM_DISASM = """
0000000100003a00 <_sha256_block>:
100003a00: 5e004000     sha256h  q0, q1, v2.4s
100003a04: 5e005020     sha256h2 q0, q1, v2.4s
100003a08: 5e282800     sha256su0 v0.4s, v0.4s
100003a0c: 5e0e6000     sha256su1 v0.4s, v1.4s, v2.4s
100003a10: 5e280800     sha1h    s0, s1
100003a14: ce608000     sha512h  q0, q1, v0.2d
"""

X86_DISASM = """
0000000000001000 <sha256_block>:
    1000: 0f 38 cb c1   sha256rnds2 %xmm0,%xmm1
    1004: 0f 38 cc c1   sha256msg1  %xmm0,%xmm1
    1008: 0f 38 cd c1   sha256msg2  %xmm0,%xmm1
"""

NO_SHA_DISASM = """
0000000100003a00 <_portable_block>:
100003a00: 8b000000     add  w0, w0, w0
100003a04: 5e280800     sha1h s0, s1
100003a08: ce608000     sha512h q0, q1, v0.2d
"""


@pytest.fixture
def fake_objdump(monkeypatch: pytest.MonkeyPatch):
    """Drive the counter from canned disassembly instead of a real toolchain."""

    def install(text: str) -> None:
        monkeypatch.setattr(ca, "_disassembler", lambda: ["fake-objdump", "-d"])
        monkeypatch.setattr(ca, "_run", lambda cmd, timeout=120.0: text)

    return install


def _artifact(tmp_path: Path) -> Path:
    p = tmp_path / "sha256_runner"
    p.write_bytes(b"\x7fELF")
    return p


# --- instruction counting -------------------------------------------------


def test_counts_aarch64_sha256_instructions(tmp_path: Path, fake_objdump) -> None:
    fake_objdump(ARM_DISASM)
    result = count_sha256_instructions(_artifact(tmp_path), "aarch64")
    assert result["present"] is True
    assert result["total"] == 4
    assert result["counts"] == {
        "sha256h": 1,
        "sha256h2": 1,
        "sha256su0": 1,
        "sha256su1": 1,
    }


def test_sha1_and_sha512_are_not_counted(tmp_path: Path, fake_objdump) -> None:
    """aarch64 advertises sha1/sha3/sha512; none of them accelerate SHA-256."""
    fake_objdump(NO_SHA_DISASM)
    result = count_sha256_instructions(_artifact(tmp_path), "aarch64")
    assert result["total"] == 0
    assert result["present"] is False


def test_sha256h_does_not_swallow_sha256h2(tmp_path: Path, fake_objdump) -> None:
    fake_objdump("sha256h2 q0, q1, v2.4s\nsha256h2 q0, q1, v2.4s\n")
    result = count_sha256_instructions(_artifact(tmp_path), "aarch64")
    assert result["counts"]["sha256h"] == 0
    assert result["counts"]["sha256h2"] == 2


def test_counts_x86_sha_ni(tmp_path: Path, fake_objdump) -> None:
    fake_objdump(X86_DISASM)
    result = count_sha256_instructions(_artifact(tmp_path), "x86_64")
    assert result["total"] == 3
    assert result["present"] is True


def test_arch_specific_mnemonics_do_not_cross_over(tmp_path: Path, fake_objdump) -> None:
    fake_objdump(ARM_DISASM)
    assert count_sha256_instructions(_artifact(tmp_path), "x86_64")["total"] == 0


def test_unknown_arch_is_unsupported_not_absent(tmp_path: Path, fake_objdump) -> None:
    fake_objdump(ARM_DISASM)
    result = count_sha256_instructions(_artifact(tmp_path), "riscv64")
    assert result["supported"] is False


def test_missing_artifact_is_unsupported(tmp_path: Path, fake_objdump) -> None:
    fake_objdump(ARM_DISASM)
    result = count_sha256_instructions(tmp_path / "nope", "aarch64")
    assert result["supported"] is False
    assert "not found" in result["reason"]


def test_symlinks_are_resolved(tmp_path: Path, fake_objdump) -> None:
    fake_objdump(ARM_DISASM)
    real = _artifact(tmp_path)
    link = tmp_path / "python3"
    link.symlink_to(real)
    assert count_sha256_instructions(link, "aarch64")["total"] == 4


# --- loader-relative library paths ---------------------------------------


def test_resolves_rpath_relative_library(tmp_path: Path) -> None:
    (tmp_path / "bin").mkdir()
    (tmp_path / "lib").mkdir()
    binary = tmp_path / "bin" / "python3"
    binary.write_bytes(b"\x7fELF")
    lib = tmp_path / "lib" / "libpython3.12.dylib"
    lib.write_bytes(b"\x7fELF")

    assert ca._resolve_loader_path("@rpath/libpython3.12.dylib", binary) == lib


def test_unresolvable_loader_path_is_dropped(tmp_path: Path) -> None:
    binary = tmp_path / "python3"
    binary.write_bytes(b"\x7fELF")
    assert ca._resolve_loader_path("@rpath/libmissing.dylib", binary) is None


# --- probe execution ------------------------------------------------------


def test_probe_does_not_let_the_shell_expand_variables(tmp_path: Path) -> None:
    """Ruby's probe contains `$LOADED_FEATURES`; a shell would eat it."""
    target = _artifact(tmp_path)
    python = shutil.which("python3") or "python3"
    cmd = f"{python} -c \"print('$NOT_A_SHELL_VAR' and {str(target)!r})\""
    assert ca._probe_artifact(cmd) == target


def test_probe_failure_returns_none() -> None:
    assert ca._probe_artifact("definitely-not-a-real-binary-xyz") is None
    assert ca._probe_artifact("") is None


# --- implementation-level audit ------------------------------------------


def test_interpreted_runner_without_a_probe_is_unknown_not_absent(tmp_path: Path) -> None:
    impl = Implementation(
        {"id": "x", "binary": "implementations/x/run.py", "interpreter": "python"}
    )
    result = audit_implementation(tmp_path, impl, "aarch64")
    assert result["hardware_sha256_present"] is None
    assert result["not_audited_reason"]


def test_registry_audit_note_is_surfaced(tmp_path: Path) -> None:
    impl = Implementation(
        {
            "id": "java-bouncycastle",
            "binary": "implementations/java-bouncycastle/out",
            "interpreter": "java",
            "audit_note": "Pure Java: nothing native to audit.",
        }
    )
    result = audit_implementation(tmp_path, impl, "aarch64")
    assert result["not_audited_reason"] == "Pure Java: nothing native to audit."


def test_compiled_runner_reports_presence(tmp_path: Path, fake_objdump) -> None:
    fake_objdump(ARM_DISASM)
    (tmp_path / "implementations" / "r").mkdir(parents=True)
    (tmp_path / "implementations" / "r" / "sha256_runner").write_bytes(b"\x7fELF")
    impl = Implementation({"id": "r", "binary": "implementations/r/sha256_runner"})

    result = audit_implementation(tmp_path, impl, "aarch64")
    assert result["hardware_sha256_present"] is True
    assert result["instruction_total"] == 4


# --- cross-check against measurement -------------------------------------


def _cost_row(impl: str, b: float) -> dict:
    return {"impl": impl, "b_ns_per_block": {"median": b}}


def _audit(entries: list[tuple[str, bool | None]]) -> dict:
    return {
        "implementations": [
            {"id": i, "hardware_sha256_present": p, "arch": "aarch64"} for i, p in entries
        ]
    }


def test_cross_check_is_silent_when_both_methods_agree() -> None:
    audit = _audit([("fast", True), ("slow", False)])
    rows = [_cost_row("fast", 30.0), _cost_row("slow", 180.0)]
    assert cross_check(audit, rows) == []


def test_cross_check_flags_fast_implementation_with_no_instructions() -> None:
    """Exactly the signature of an audit that missed a dlopen'd system library."""
    audit = _audit([("fast", True), ("mystery", False)])
    rows = [_cost_row("fast", 30.0), _cost_row("mystery", 30.5)]

    findings = cross_check(audit, rows)

    assert [f["impl"] for f in findings] == ["mystery"]
    assert findings[0]["measurement_suggests_acceleration"] is True
    assert "incomplete audit" in findings[0]["likely_cause"]


def test_cross_check_flags_instructions_that_do_not_show_up_in_timing() -> None:
    audit = _audit([("fast", True), ("claims_hw", True)])
    rows = [_cost_row("fast", 30.0), _cost_row("claims_hw", 180.0)]

    findings = cross_check(audit, rows)

    assert [f["impl"] for f in findings] == ["claims_hw"]
    assert findings[0]["measurement_suggests_acceleration"] is False


def test_cross_check_ignores_unaudited_implementations() -> None:
    audit = _audit([("fast", True), ("unknown", None)])
    rows = [_cost_row("fast", 30.0), _cost_row("unknown", 300.0)]
    assert cross_check(audit, rows) == []
