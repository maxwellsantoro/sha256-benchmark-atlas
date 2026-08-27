from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    """Locate repository root containing registry/implementations.yaml."""
    here = Path(__file__).resolve()
    for candidate in [here.parent, *here.parents]:
        if (candidate / "registry" / "implementations.yaml").is_file():
            return candidate
    cwd = Path.cwd()
    if (cwd / "registry" / "implementations.yaml").is_file():
        return cwd
    raise FileNotFoundError("Could not find registry/implementations.yaml")
