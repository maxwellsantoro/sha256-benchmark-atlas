from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# ARMv8 "CPU part" values seen on CI/cloud hosts. lscpu is preferred when present;
# this map only exists so an aarch64 block still names its CPU when lscpu is absent.
ARM_PART_NAMES = {
    (0x41, 0xD03): "Cortex-A53",
    (0x41, 0xD07): "Cortex-A57",
    (0x41, 0xD08): "Cortex-A72",
    (0x41, 0xD0C): "Neoverse-N1",
    (0x41, 0xD40): "Neoverse-V1",
    (0x41, 0xD49): "Neoverse-N2",
    (0x41, 0xD4F): "Neoverse-V2",
    (0x41, 0xD8E): "Neoverse-N3",
    (0x4E, 0x004): "Carmel",
    (0x50, 0x000): "Ampere-eMAG",
    (0xC0, 0xAC3): "Ampere-1",
}

# Tokens that indicate a *hardware SHA-256* datapath, by architecture. These are
# exact tokens, never substrings: aarch64 also advertises `sha1`, `sha3` and
# `sha512`, none of which accelerate SHA-256.
SHA256_HW_TOKENS = {
    "x86_64": ("sha_ni", "sha"),
    "aarch64": ("sha2", "sha256"),
}


def _run(cmd: list[str], timeout: float = 30.0) -> str:
    try:
        r = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return (r.stdout or "") + (r.stderr or "")
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        return f"<unavailable: {e}>"


def _first_line(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line
    return ""


def normalize_arch(machine: str) -> str:
    """Collapse platform.machine() spellings onto the names used for stratification."""
    m = (machine or "").lower()
    if m in {"x86_64", "amd64", "x64"}:
        return "x86_64"
    if m in {"aarch64", "arm64"}:
        return "aarch64"
    return m or "unknown"


def _lscpu_fields(text: str | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (text or "").splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def _cpuinfo_fields(text: str) -> dict[str, str]:
    """First-processor-block view of /proc/cpuinfo (hosts here are homogeneous)."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip():
            if out:
                break
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            out.setdefault(k.strip(), v.strip())
    return out


def detect_sha256_hw(arch: str, features: str) -> tuple[bool | None, list[str]]:
    """Does this CPU expose a hardware SHA-256 datapath?

    Returns (supported, matched_tokens). `None` means "could not tell" — which is
    reported honestly rather than collapsed to False, because a silent False on a
    CPU that *does* accelerate SHA-256 corrupts every comparison stratified on it.
    """
    tokens = SHA256_HW_TOKENS.get(arch)
    if tokens is None:
        return None, []
    present = set(features.split())
    if not present:
        return None, []
    matched = [t for t in tokens if t in present]
    return bool(matched), matched


def collect_library_versions() -> dict[str, str | None]:
    """Resolve the versions of the crypto libraries actually linked at run time.

    Registry entries for system libraries can only say "system"; without this the
    published numbers cannot be traced to a specific libsodium or mbedTLS, and the
    atlas's provenance promise stops at the package name.
    """
    out: dict[str, str | None] = {}

    if shutil.which("pkg-config"):
        for name in ("libcrypto", "libsodium", "mbedcrypto"):
            version = _first_line(_run(["pkg-config", "--modversion", name]))
            out[name] = version if version and not version.startswith("<") else None
    else:
        out.update({"libcrypto": None, "libsodium": None, "mbedcrypto": None})

    out["python-cryptography"] = _first_line(
        _run(
            [
                "python3",
                "-c",
                "import cryptography; print(cryptography.__version__)",
            ]
        )
    ) or None
    if out["python-cryptography"] and (
        "Traceback" in out["python-cryptography"] or "<" in out["python-cryptography"]
    ):
        out["python-cryptography"] = None

    return out


def cpu_facts_from_fingerprint(fp: dict[str, Any]) -> dict[str, Any]:
    """Re-derive CPU identity from a fingerprint file, old schema or new.

    Fingerprints written before the aarch64 fix recorded an empty `model_name` and
    `sha_ni: false` on ARM hosts, because they only understood the x86 spelling of
    /proc/cpuinfo. The raw text they captured is sufficient to recover the truth, so
    archived campaigns can be re-read correctly instead of being re-run.
    """
    cpu = fp.get("cpu", {}) or {}
    plat = fp.get("platform", {}) or {}
    arch = normalize_arch(cpu.get("arch") or plat.get("arch") or plat.get("machine") or "")

    model = cpu.get("model_name") or ""
    features = cpu.get("features") or ""
    sha_hw = cpu.get("sha256_hw")

    if not features or not model or sha_hw is None:
        cpuinfo = cpu.get("proc_cpuinfo") or cpu.get("proc_cpuinfo_first_block") or ""
        fields = _cpuinfo_fields(cpuinfo) if cpuinfo else {}
        lscpu = _lscpu_fields(cpu.get("lscpu"))

        if not features:
            features = fields.get("flags") or fields.get("Features") or lscpu.get("Flags", "")
        if not model:
            model = fields.get("model name") or lscpu.get("Model name", "")
        if not model and arch == "aarch64" and "CPU part" in fields:
            try:
                impl = int(fields.get("CPU implementer", "0"), 16)
                part = int(fields.get("CPU part", "0"), 16)
                model = ARM_PART_NAMES.get((impl, part), f"aarch64 impl={impl:#x} part={part:#x}")
            except ValueError:
                pass

    if sha_hw is None:
        sha_hw, evidence = detect_sha256_hw(arch, features)
    else:
        evidence = cpu.get("sha256_hw_evidence") or []

    return {
        "arch": arch or "unknown",
        "model_name": model or None,
        "features": features,
        "sha256_hw": sha_hw,
        "sha256_hw_evidence": evidence,
    }


def collect_fingerprint() -> dict[str, Any]:
    uname = platform.uname()
    arch = normalize_arch(uname.machine)
    fp: dict[str, Any] = {
        "collected_at": datetime.now(UTC).isoformat(),
        "platform": {
            "system": uname.system,
            "node": uname.node,
            "release": uname.release,
            "version": uname.version,
            "machine": uname.machine,
            "arch": arch,
            "processor": uname.processor,
            "python": platform.python_version(),
        },
        "env": {
            "GITHUB_ACTIONS": os.environ.get("GITHUB_ACTIONS"),
            "RUNNER_OS": os.environ.get("RUNNER_OS"),
            "RUNNER_ARCH": os.environ.get("RUNNER_ARCH"),
            "ImageOS": os.environ.get("ImageOS"),
            "ImageVersion": os.environ.get("ImageVersion"),
        },
        "tools": {},
        "cpu": {"arch": arch},
        "memory": {},
    }

    tool_cmds = {
        "cc": ["cc", "--version"],
        "rustc": ["rustc", "--version"],
        "cargo": ["cargo", "--version"],
        "go": ["go", "version"],
        "node": ["node", "--version"],
        "java": ["java", "-version"],
        "javac": ["javac", "-version"],
        "openssl": ["openssl", "version"],
        "python": ["python3", "--version"],
        "ruby": ["ruby", "--version"],
        "php": ["php", "--version"],
        "bun": ["bun", "--version"],
        "zig": ["zig", "version"],
    }
    for name, cmd in tool_cmds.items():
        if shutil.which(cmd[0]) is None:
            fp["tools"][name] = None
            continue
        fp["tools"][name] = _first_line(_run(cmd))

    fp["libraries"] = collect_library_versions()

    lscpu_text = _run(["lscpu"]) if shutil.which("lscpu") else None
    lscpu = _lscpu_fields(lscpu_text)

    model = ""
    features = ""
    feature_source = None

    if Path("/proc/cpuinfo").exists():
        cpuinfo = Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="replace")
        fields = _cpuinfo_fields(cpuinfo)
        fp["cpu"]["processor_count"] = len(re.findall(r"^processor\s*:", cpuinfo, re.MULTILINE))
        # Keep one representative block rather than N identical ones: a 96-core
        # host otherwise buries the fingerprint under ~500 KiB of duplicates.
        fp["cpu"]["proc_cpuinfo_first_block"] = cpuinfo.split("\n\n", 1)[0]

        # x86 spells these `model name` / `flags`; aarch64 spells them nowhere and
        # `Features` respectively. Handling only the x86 spelling silently reports
        # an empty model and no SHA support on every ARM host.
        model = fields.get("model name") or fields.get("Model name") or ""
        if fields.get("flags"):
            features, feature_source = fields["flags"], "cpuinfo:flags"
        elif fields.get("Features"):
            features, feature_source = fields["Features"], "cpuinfo:Features"

        if not model:
            model = lscpu.get("Model name", "")
        if not model and arch == "aarch64":
            try:
                impl = int(fields.get("CPU implementer", "0"), 16)
                part = int(fields.get("CPU part", "0"), 16)
                model = ARM_PART_NAMES.get((impl, part), f"aarch64 impl={impl:#x} part={part:#x}")
            except ValueError:
                model = ""
        if not features and lscpu.get("Flags"):
            features, feature_source = lscpu["Flags"], "lscpu:Flags"
    else:
        sysctl = {
            "brand": _first_line(_run(["sysctl", "-n", "machdep.cpu.brand_string"])),
            "features": _first_line(_run(["sysctl", "-n", "machdep.cpu.features"])),
            "leaf7": _first_line(_run(["sysctl", "-n", "machdep.cpu.leaf7_features"])),
        }
        fp["cpu"]["sysctl"] = sysctl
        model = sysctl.get("brand") or ""
        if arch == "aarch64":
            # Apple silicon reports capabilities as individual sysctl booleans.
            feat = _first_line(_run(["sysctl", "-n", "hw.optional.arm.FEAT_SHA256"]))
            if feat.strip() == "1":
                features, feature_source = "sha2", "sysctl:hw.optional.arm.FEAT_SHA256"
            elif feat.strip() == "0":
                features, feature_source = "", "sysctl:hw.optional.arm.FEAT_SHA256"
        else:
            features = " ".join(
                t.lower() for t in (sysctl.get("leaf7", "") + " " + sysctl.get("features", "")).split()
            )
            feature_source = "sysctl:machdep.cpu"

    sha_hw, evidence = detect_sha256_hw(arch, features)

    fp["cpu"]["model_name"] = model
    fp["cpu"]["features"] = features
    fp["cpu"]["feature_source"] = feature_source
    fp["cpu"]["sha256_hw"] = sha_hw
    fp["cpu"]["sha256_hw_evidence"] = evidence
    # Retained under its original name for older result files; x86-specific.
    fp["cpu"]["sha_ni"] = bool(sha_hw) if arch == "x86_64" else False
    fp["cpu"]["lscpu"] = lscpu_text

    fp["memory"]["free"] = _run(["free", "-h"]) if shutil.which("free") else None
    if shutil.which("sysctl"):
        fp["memory"]["memsize"] = _first_line(_run(["sysctl", "-n", "hw.memsize"]))
        fp["cpu"]["ncpu"] = _first_line(_run(["sysctl", "-n", "hw.ncpu"]))
    if Path("/proc/meminfo").exists():
        meminfo = Path("/proc/meminfo").read_text(encoding="utf-8", errors="replace")
        fp["memory"]["meminfo"] = "\n".join(meminfo.splitlines()[:8])

    return fp


def write_fingerprint(path: Path, fp: dict[str, Any] | None = None) -> dict[str, Any]:
    data = fp or collect_fingerprint()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return data
