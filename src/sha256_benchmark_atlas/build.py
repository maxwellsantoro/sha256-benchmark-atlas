from __future__ import annotations

import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .registry import Implementation, load_registry


@dataclass
class BuildResult:
    id: str
    ok: bool
    detail: str


def build_impl(root: Path, impl: Implementation) -> BuildResult:
    if not impl.build:
        # Interpreted runners: ensure executable bit / compile java handled by command
        if impl.interpreter == "java":
            out = root / impl.binary
            out.mkdir(parents=True, exist_ok=True)
            src = root / "implementations" / "java-jdk" / "Sha256Runner.java"
            cmd = ["javac", "-d", str(out), str(src)]
            r = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
            if r.returncode != 0:
                return BuildResult(impl.id, False, (r.stderr or r.stdout or "javac failed")[:500])
            return BuildResult(impl.id, True, "javac ok")
        path = root / impl.binary
        if not path.exists():
            return BuildResult(impl.id, False, f"missing {impl.binary}")
        if impl.interpreter in {"python", "node"}:
            path.chmod(path.stat().st_mode | 0o111)
        return BuildResult(impl.id, True, "no build step")

    # Rewrite relative paths in build to run from root
    cmd = shlex.split(impl.build)
    if cmd[0] == "go" and not shutil.which("go"):
        return BuildResult(impl.id, False, "go toolchain not installed")
    if cmd[0] == "cargo" and not shutil.which("cargo"):
        return BuildResult(impl.id, False, "cargo/rustc not installed")
    if cmd[0] == "javac" and not shutil.which("javac"):
        return BuildResult(impl.id, False, "javac not installed")

    r = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
    if r.returncode != 0:
        detail = (r.stderr or r.stdout or "build failed").strip()[:800]
        return BuildResult(impl.id, False, detail)
    return BuildResult(impl.id, True, "built")


def build_all(root: Path, ids: list[str] | None = None) -> list[BuildResult]:
    reg = load_registry(root)
    results: list[BuildResult] = []
    for impl in reg.by_id(ids):
        results.append(build_impl(root, impl))
    return results
