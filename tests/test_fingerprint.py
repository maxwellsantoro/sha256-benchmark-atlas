from __future__ import annotations

from sha256_benchmark_atlas.fingerprint import (
    _cpuinfo_fields,
    _lscpu_fields,
    collect_fingerprint,
    cpu_facts_from_fingerprint,
    detect_sha256_hw,
    normalize_arch,
)

# Trimmed from a real ubuntu-24.04-arm GitHub-hosted runner. aarch64 spells its
# capabilities "Features" and does not publish "model name" at all.
ARM_CPUINFO = """processor\t: 0
BogoMIPS\t: 2000.00
Features\t: fp asimd evtstrm aes pmull sha1 sha2 crc32 atomics sha3 sha512
CPU implementer\t: 0x41
CPU architecture: 8
CPU variant\t: 0x0
CPU part\t: 0xd49
CPU revision\t: 0

processor\t: 1
BogoMIPS\t: 2000.00
Features\t: fp asimd evtstrm aes pmull sha1 sha2 crc32 atomics sha3 sha512
"""

X86_CPUINFO = """processor\t: 0
vendor_id\t: AuthenticAMD
model name\t: AMD EPYC 9V45 96-Core Processor
flags\t\t: fpu vme de pse sse2 avx2 sha_ni avx512f
"""

ARM_LSCPU = """Architecture:                            aarch64
Vendor ID:                               ARM
Model name:                              Neoverse-N2
CPU(s):                                  4
"""


def test_normalize_arch_collapses_spellings() -> None:
    assert normalize_arch("x86_64") == "x86_64"
    assert normalize_arch("AMD64") == "x86_64"
    assert normalize_arch("aarch64") == "aarch64"
    assert normalize_arch("arm64") == "aarch64"
    assert normalize_arch("") == "unknown"


def test_detects_sha256_on_x86_via_sha_ni() -> None:
    supported, evidence = detect_sha256_hw("x86_64", "fpu avx2 sha_ni avx512f")
    assert supported is True
    assert evidence == ["sha_ni"]


def test_detects_sha256_on_aarch64_via_sha2() -> None:
    """The bug this guards: ARM was reported as having no SHA-256 hardware."""
    features = _cpuinfo_fields(ARM_CPUINFO)["Features"]
    supported, evidence = detect_sha256_hw("aarch64", features)
    assert supported is True
    assert evidence == ["sha2"]


def test_sha1_sha3_and_sha512_do_not_imply_sha256_acceleration() -> None:
    supported, evidence = detect_sha256_hw("aarch64", "fp asimd sha1 sha3 sha512")
    assert supported is False
    assert evidence == []


def test_unknown_features_report_none_rather_than_false() -> None:
    """A silent False on a capable CPU would corrupt every stratified comparison."""
    assert detect_sha256_hw("aarch64", "") == (None, [])
    assert detect_sha256_hw("riscv64", "sha2") == (None, [])


def test_cpuinfo_fields_reads_only_the_first_processor_block() -> None:
    fields = _cpuinfo_fields(ARM_CPUINFO)
    assert fields["CPU part"] == "0xd49"
    assert "sha2" in fields["Features"]


def test_lscpu_fields_parse() -> None:
    assert _lscpu_fields(ARM_LSCPU)["Model name"] == "Neoverse-N2"


def test_backfill_recovers_arm_facts_from_a_legacy_fingerprint() -> None:
    """Archived campaigns are re-read correctly instead of being re-run."""
    legacy = {
        "platform": {"machine": "aarch64"},
        "cpu": {"proc_cpuinfo": ARM_CPUINFO, "lscpu": ARM_LSCPU, "sha_ni": False, "model_name": ""},
    }

    facts = cpu_facts_from_fingerprint(legacy)

    assert facts["arch"] == "aarch64"
    assert facts["model_name"] == "Neoverse-N2"
    assert facts["sha256_hw"] is True
    assert facts["sha256_hw_evidence"] == ["sha2"]


def test_backfill_names_an_arm_cpu_from_part_id_without_lscpu() -> None:
    legacy = {"platform": {"machine": "aarch64"}, "cpu": {"proc_cpuinfo": ARM_CPUINFO}}
    assert cpu_facts_from_fingerprint(legacy)["model_name"] == "Neoverse-N2"


def test_backfill_recovers_x86_facts() -> None:
    legacy = {"platform": {"machine": "x86_64"}, "cpu": {"proc_cpuinfo": X86_CPUINFO}}

    facts = cpu_facts_from_fingerprint(legacy)

    assert facts["model_name"] == "AMD EPYC 9V45 96-Core Processor"
    assert facts["sha256_hw"] is True


def test_backfill_prefers_values_already_present() -> None:
    modern = {
        "platform": {"machine": "aarch64"},
        "cpu": {
            "arch": "aarch64",
            "model_name": "Neoverse-V2",
            "features": "fp asimd sha2",
            "sha256_hw": True,
            "sha256_hw_evidence": ["sha2"],
        },
    }
    assert cpu_facts_from_fingerprint(modern)["model_name"] == "Neoverse-V2"


def test_collect_fingerprint_reports_arch_and_sha_support_on_this_host() -> None:
    fp = collect_fingerprint()

    assert fp["cpu"]["arch"] == fp["platform"]["arch"]
    assert fp["cpu"]["arch"] in {"x86_64", "aarch64"}
    # Every current dev/CI target for this project has hardware SHA-256; the point
    # is that detection produces a definite answer rather than a silent False.
    assert fp["cpu"]["sha256_hw"] is not None
    assert fp["cpu"]["model_name"]
