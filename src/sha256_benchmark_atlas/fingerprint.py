from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


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


def collect_fingerprint() -> dict[str, Any]:
    uname = platform.uname()
    fp: dict[str, Any] = {
        "collected_at": datetime.now(UTC).isoformat(),
        "platform": {
            "system": uname.system,
            "node": uname.node,
            "release": uname.release,
            "version": uname.version,
            "machine": uname.machine,
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
        "cpu": {},
        "memory": {},
    }

    tool_cmds = {
        "cc": ["cc", "--version"],
        "rustc": ["rustc", "--version"],
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

    if Path("/proc/cpuinfo").exists():
        cpuinfo = Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="replace")
        fp["cpu"]["proc_cpuinfo"] = cpuinfo
        model = ""
        flags = ""
        for line in cpuinfo.splitlines():
            if line.startswith("model name") and not model:
                model = line.split(":", 1)[1].strip()
            if line.startswith("flags") and not flags:
                flags = line.split(":", 1)[1].strip()
        fp["cpu"]["model_name"] = model
        fp["cpu"]["flags"] = flags
        fp["cpu"]["sha_ni"] = " sha_ni " in f" {flags} " or "sha_ni" in flags.split()
    else:
        fp["cpu"]["sysctl"] = {
            "brand": _first_line(_run(["sysctl", "-n", "machdep.cpu.brand_string"])),
            "features": _first_line(_run(["sysctl", "-n", "machdep.cpu.features"])),
            "leaf7": _first_line(_run(["sysctl", "-n", "machdep.cpu.leaf7_features"])),
        }
        leaf7 = (fp["cpu"]["sysctl"].get("leaf7") or "").upper()
        fp["cpu"]["sha_ni"] = "SHA" in leaf7.split()

    fp["cpu"]["lscpu"] = _run(["lscpu"]) if shutil.which("lscpu") else None
    fp["memory"]["free"] = _run(["free", "-h"]) if shutil.which("free") else None
    if shutil.which("sysctl"):
        fp["memory"]["memsize"] = _first_line(_run(["sysctl", "-n", "hw.memsize"]))
        fp["cpu"]["ncpu"] = _first_line(_run(["sysctl", "-n", "hw.ncpu"]))
    if Path("/proc/meminfo").exists():
        fp["memory"]["meminfo"] = Path("/proc/meminfo").read_text(encoding="utf-8", errors="replace")

    return fp


def write_fingerprint(path: Path, fp: dict[str, Any] | None = None) -> dict[str, Any]:
    data = fp or collect_fingerprint()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return data
