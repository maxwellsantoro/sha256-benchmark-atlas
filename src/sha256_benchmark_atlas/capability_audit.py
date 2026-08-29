"""Static audit: does an implementation's machine code contain a SHA-256 datapath?

Timing tells you an implementation is slow. It does not tell you *why*, and the
usual inference — "it must not be using the hardware instructions" — is exactly the
kind of claim this atlas is supposed to support with evidence rather than assert.

Disassembling the shipped artifact settles it directly and costs nothing: either
the SHA-256 extension mnemonics are present in the binary or the crypto library it
links, or they are not. Run per architecture, this catches an implementation whose
registry entry claims `hardware_acceleration: auto` while its aarch64 build ships
none, which is precisely the case measurement flagged for `rust-sha2` and `zig-std`.

Coverage is honest rather than complete: statically linked runners and the native
crypto libraries behind the C bindings are auditable; a digest reached through an
interpreter's own embedded copy of a library may not be resolvable from outside, and
is reported as `unknown` rather than guessed at.
"""

from __future__ import annotations

import os
import platform
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .fingerprint import normalize_arch
from .registry import Implementation

# Instruction mnemonics that constitute a hardware SHA-256 datapath, per target.
SHA256_MNEMONICS: dict[str, tuple[str, ...]] = {
    "x86_64": ("sha256rnds2", "sha256msg1", "sha256msg2"),
    "aarch64": ("sha256h", "sha256h2", "sha256su0", "sha256su1"),
}

# Shared objects worth disassembling when a runner links them, by registry backend.
BACKEND_LIBRARY_HINTS: dict[str, tuple[str, ...]] = {
    "openssl": ("libcrypto",),
    "boringssl": ("libcrypto", "boringssl"),
    "libsodium": ("libsodium",),
    "mbedtls": ("libmbedcrypto", "mbedcrypto"),
}

# Interpreters are frequently a small launcher stub in front of a runtime library
# that has the crypto library statically linked into it. Auditing only the stub finds
# nothing and wrongly concludes there is no hardware path, so the runtime library is
# followed too.
RUNTIME_LIBRARY_PATTERNS = ("libpython", "libruby", "libnode", "libphp", "libjvm")

MAX_LIBRARIES_PER_IMPL = 6


def _run(cmd: list[str], timeout: float = 120.0) -> str:
    try:
        r = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=timeout)
        return r.stdout or ""
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return ""


def _disassembler() -> list[str] | None:
    for candidate in ("llvm-objdump", "objdump"):
        path = shutil.which(candidate)
        if path:
            return [path, "-d"]
    return None


def count_sha256_instructions(path: Path, arch: str) -> dict[str, Any]:
    """Count hardware SHA-256 mnemonics in one binary or shared object."""
    mnemonics = SHA256_MNEMONICS.get(arch)
    if mnemonics is None:
        return {"path": str(path), "supported": False, "reason": f"unknown arch {arch!r}"}
    disasm = _disassembler()
    if disasm is None:
        return {"path": str(path), "supported": False, "reason": "no objdump available"}
    # A venv's `python3` is a symlink chain; disassembling the link finds nothing.
    path = path.resolve()
    if not path.is_file():
        return {"path": str(path), "supported": False, "reason": "artifact not found"}

    text = _run([*disasm, str(path)])
    if not text:
        return {"path": str(path), "supported": False, "reason": "disassembly produced no output"}

    # Match whole mnemonics only: aarch64 also has sha1h/sha512h, and `sha256h`
    # is a prefix of `sha256h2`.
    counts: dict[str, int] = {}
    for m in mnemonics:
        counts[m] = len(re.findall(rf"\b{m}\b", text))
    total = sum(counts.values())
    return {
        "path": str(path),
        "supported": True,
        "counts": counts,
        "total": total,
        "present": total > 0,
    }


def _resolve_loader_path(entry: str, binary: Path) -> Path | None:
    """Resolve a Mach-O `@rpath` / `@loader_path` / `@executable_path` reference.

    These are not literal files, so treating them as such silently drops the very
    library that holds the crypto code — a stub launcher in front of
    `@rpath/libpython3.12.dylib` would audit as having no hardware path at all.
    Full rpath resolution needs the load commands; searching the handful of layouts
    actually used by these runtimes is enough and much simpler.
    """
    if not entry.startswith("@"):
        p = Path(entry)
        return p if p.is_file() else None

    name = os.path.basename(entry)
    base = binary.resolve().parent
    for candidate in (
        base / name,
        base.parent / "lib" / name,
        base.parent / "lib64" / name,
        base.parent / name,
    ):
        if candidate.is_file():
            return candidate
    return None


def _linked_libraries(binary: Path, backend: str | None) -> list[Path]:
    """Resolve the crypto and runtime shared objects a runner actually links."""
    hints = (*BACKEND_LIBRARY_HINTS.get(backend or "", ()), *RUNTIME_LIBRARY_PATTERNS)
    if not binary.is_file():
        return []

    if platform.system() == "Darwin":
        out = _run(["otool", "-L", str(binary)])
        candidates = [line.strip().split(" ")[0] for line in out.splitlines()[1:] if line.strip()]
    else:
        out = _run(["ldd", str(binary)])
        candidates = []
        for line in out.splitlines():
            if "=>" in line:
                target = line.split("=>", 1)[1].strip().split(" ")[0]
                if target and target != "not":
                    candidates.append(target)
            elif line.strip().startswith("/"):
                candidates.append(line.strip().split(" ")[0])

    found: list[Path] = []
    for c in candidates:
        name = os.path.basename(c).lower()
        if not any(h in name for h in hints):
            continue
        resolved = _resolve_loader_path(c, binary)
        if resolved is None:
            continue
        p = resolved.resolve()
        if p not in found and p != binary.resolve():
            found.append(p)
    return found[:MAX_LIBRARIES_PER_IMPL]


def _probe_artifact(command: str) -> Path | None:
    """Ask an interpreted runtime where its native SHA-256 code actually lives.

    Split rather than run through a shell: these probes legitimately contain `$`
    (Ruby's `$LOADED_FEATURES`), which a shell would expand to nothing, and it keeps
    registry-supplied strings away from shell interpretation entirely.
    """
    try:
        argv = shlex.split(command)
    except ValueError:
        return None
    if not argv:
        return None
    try:
        r = subprocess.run(argv, check=False, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    out = (r.stdout or "").strip().splitlines()
    if not out:
        return None
    p = Path(out[-1].strip())
    return p if p.is_file() else None


def audit_implementation(
    root: Path, impl: Implementation, arch: str | None = None
) -> dict[str, Any]:
    """Audit one implementation's shipped artifacts for a hardware SHA-256 path."""
    arch = normalize_arch(arch or platform.machine())
    artifacts: list[dict[str, Any]] = []
    probe_used: str | None = None

    # An interpreted runner's `binary` is a script, so disassembling it is
    # meaningless; the registry says how to locate the native module instead.
    if impl.interpreter is not None:
        command = impl.raw.get("audit_artifact_cmd")
        target = _probe_artifact(command) if command else None
        if target is not None:
            probe_used = command
            artifacts.append(count_sha256_instructions(target, arch))
            for lib in _linked_libraries(target, impl.backend):
                artifacts.append(count_sha256_instructions(lib, arch))
    else:
        binary = root / impl.binary
        artifacts.append(count_sha256_instructions(binary, arch))
        for lib in _linked_libraries(binary, impl.backend):
            artifacts.append(count_sha256_instructions(lib, arch))

    audited = [a for a in artifacts if a.get("supported")]
    total = sum(a.get("total", 0) for a in audited)

    if audited:
        present: bool | None = total > 0
        reason = None
    else:
        present = None
        reason = impl.raw.get("audit_note") or (
            "no audit_artifact_cmd in the registry, or the probe found nothing"
            if impl.interpreter is not None
            else "no artifact could be disassembled (is it built?)"
        )

    return {
        "id": impl.id,
        "arch": arch,
        "backend": impl.backend,
        "declared_hardware_acceleration": impl.raw.get("hardware_acceleration"),
        "hardware_sha256_present": present,
        "instruction_total": total if audited else None,
        "probe_command": probe_used,
        "artifacts": artifacts,
        "not_audited_reason": reason,
    }


def audit_all(root: Path, impls: list[Implementation], arch: str | None = None) -> dict[str, Any]:
    results = [audit_implementation(root, impl, arch) for impl in impls]
    audited = [r for r in results if r["hardware_sha256_present"] is not None]
    return {
        "arch": normalize_arch(arch or platform.machine()),
        "disassembler": (_disassembler() or ["<none>"])[0],
        "audited": len(audited),
        "skipped": len(results) - len(audited),
        "with_hardware_path": sum(1 for r in audited if r["hardware_sha256_present"]),
        "implementations": results,
    }


def cross_check(
    audit: dict[str, Any],
    cost_rows: list[dict[str, Any]],
    *,
    accel_ratio_threshold: float = 2.0,
) -> list[dict[str, Any]]:
    """Reconcile what the binary contains against what the measurement implies.

    The fitted per-block cost `b` is the compression function's speed. Implementations
    that ship SHA-256 instructions should cluster near the fastest observed `b`; those
    that do not should sit well above it. A disagreement means one of the two is
    wrong, and is worth surfacing rather than quietly averaging away.
    """
    by_id = {r["impl"]: r for r in cost_rows if r.get("b_ns_per_block")}
    if not by_id:
        return []
    fastest = min(r["b_ns_per_block"]["median"] for r in by_id.values())

    findings: list[dict[str, Any]] = []
    for entry in audit["implementations"]:
        present = entry["hardware_sha256_present"]
        row = by_id.get(entry["id"])
        if present is None or row is None:
            continue
        b = row["b_ns_per_block"]["median"]
        ratio = b / fastest if fastest else None
        if ratio is None:
            continue
        looks_accelerated = ratio < accel_ratio_threshold
        if looks_accelerated != present:
            findings.append(
                {
                    "impl": entry["id"],
                    "arch": entry["arch"],
                    "hardware_sha256_present": present,
                    "b_ns_per_block": b,
                    "b_ratio_vs_fastest": ratio,
                    "measurement_suggests_acceleration": looks_accelerated,
                    "likely_cause": (
                        "hardware path present but unused at run time (dispatch "
                        "declined it), or the instructions belong to an unrelated "
                        "routine in the same artifact"
                        if present
                        else "incomplete audit: the real implementation is most "
                        "likely in a library the probe did not reach — a system "
                        "library behind the macOS dyld shared cache, a dlopen'd "
                        "module, or a runtime-generated JIT intrinsic"
                    ),
                    "note": (
                        "binary ships SHA-256 instructions but the measured per-block "
                        "cost is not near the accelerated cluster"
                        if present
                        else "measured per-block cost matches the accelerated cluster "
                        "but no SHA-256 instructions were found in the audited artifacts"
                    ),
                }
            )
    return findings
