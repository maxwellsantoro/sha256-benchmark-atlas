from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Implementation:
    raw: dict[str, Any]

    @property
    def id(self) -> str:
        return str(self.raw["id"])

    @property
    def status(self) -> str:
        return str(self.raw.get("status", "discovered"))

    @property
    def backend(self) -> str | None:
        return self.raw.get("backend")

    @property
    def build(self) -> str | None:
        return self.raw.get("build")

    @property
    def binary(self) -> str:
        return str(self.raw["binary"])

    @property
    def interpreter(self) -> str | None:
        return self.raw.get("interpreter")

    @property
    def java_main(self) -> str | None:
        return self.raw.get("java_main")

    @property
    def java_cp(self) -> str | None:
        return self.raw.get("java_cp")

    def as_dict(self) -> dict[str, Any]:
        return dict(self.raw)


@dataclass
class Registry:
    data: dict[str, Any]
    root: Path

    @property
    def message_sizes(self) -> list[int]:
        return list(self.data.get("message_sizes_bytes", []))

    def implementations(self, *, admitted_only: bool = True) -> list[Implementation]:
        out: list[Implementation] = []
        for item in self.data.get("implementations", []):
            impl = Implementation(item)
            if admitted_only and impl.status != "admitted":
                continue
            out.append(impl)
        return out

    def by_id(self, ids: list[str] | None = None, *, admitted_only: bool = True) -> list[Implementation]:
        impls = self.implementations(admitted_only=admitted_only)
        if ids is None:
            return impls
        wanted = set(ids)
        found = [i for i in impls if i.id in wanted]
        missing = wanted - {i.id for i in found}
        if missing:
            raise KeyError(f"Unknown implementation ids: {sorted(missing)}")
        return found


def load_registry(root: Path) -> Registry:
    path = root / "registry" / "implementations.yaml"
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return Registry(data=data, root=root)
