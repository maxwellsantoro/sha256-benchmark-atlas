from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .registry import Implementation, load_registry

SCRIPT_INTERPRETERS = {"python", "node", "ruby", "php", "bun"}


@dataclass
class BuildResult:
    id: str
    ok: bool
    detail: str


def _java_sources(root: Path, impl: Implementation) -> Path:
    impl_dir = root / "implementations" / impl.id
    for name in ("Sha256Runner.java", "sha256_runner.java"):
        candidate = impl_dir / name
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"no Java source under implementations/{impl.id}")


def build_impl(root: Path, impl: Implementation) -> BuildResult:
    if not impl.build:
        if impl.interpreter == "java":
            out = root / impl.binary
            out.mkdir(parents=True, exist_ok=True)
            try:
                src = _java_sources(root, impl)
            except FileNotFoundError as e:
                return BuildResult(impl.id, False, str(e))
            cp_parts = [str(out)]
            if impl.java_cp:
                cp_parts.append(str(root / impl.java_cp))
            cmd = ["javac", "-cp", os.pathsep.join(cp_parts), "-d", str(out), str(src)]
            r = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
            if r.returncode != 0:
                return BuildResult(impl.id, False, (r.stderr or r.stdout or "javac failed")[:500])
            return BuildResult(impl.id, True, "javac ok")

        if impl.interpreter == "ruby" and not shutil.which("ruby"):
            return BuildResult(impl.id, False, "ruby not installed")
        if impl.interpreter == "php" and not shutil.which("php"):
            return BuildResult(impl.id, False, "php not installed")
        if impl.interpreter == "bun" and not shutil.which("bun"):
            return BuildResult(impl.id, False, "bun not installed")

        path = root / impl.binary
        if not path.exists():
            return BuildResult(impl.id, False, f"missing {impl.binary}")
        if impl.interpreter in SCRIPT_INTERPRETERS:
            path.chmod(path.stat().st_mode | 0o111)
        return BuildResult(impl.id, True, "no build step")

    if impl.build.startswith("bash "):
        script = impl.build.split(" ", 1)[1]
        cmd = ["bash", str(root / script)]
    else:
        cmd = shlex.split(impl.build)

    tool = cmd[0]
    if tool == "go" and not shutil.which("go"):
        return BuildResult(impl.id, False, "go toolchain not installed")
    if tool == "cargo" and not shutil.which("cargo"):
        return BuildResult(impl.id, False, "cargo/rustc not installed")
    if tool == "javac" and not shutil.which("javac"):
        return BuildResult(impl.id, False, "javac not installed")
    if tool == "make" and not shutil.which("make"):
        return BuildResult(impl.id, False, "make not installed")
    if tool == "zig" and not shutil.which("zig"):
        return BuildResult(impl.id, False, "zig not installed")

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
