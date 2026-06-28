"""Load and initialize `psi.toml` manifests."""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

from .models import PackageManifest


def manifest_path(path: str | Path) -> Path:
    value = Path(path).expanduser()
    if value.is_dir():
        value = value / "psi.toml"
    return value.resolve()


def load_manifest(path: str | Path) -> PackageManifest:
    target = manifest_path(path)
    data = _load_toml(target)
    manifest = PackageManifest.model_validate(data)
    manifest.base_dir = target.parent
    return manifest


def init_package(
    path: str | Path = ".",
    *,
    name: str | None = None,
    org: str = "local",
    kind: str = "mixed",
    force: bool = False,
) -> Path:
    root = Path(path).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    target = root / "psi.toml"
    if target.exists() and not force:
        return target
    package_name = name or root.resolve().name
    target.write_text(
        textwrap.dedent(
            f"""
            [package]
            psi_version = "0.1"
            org = "{org}"
            name = "{package_name}"
            version = "0.1.0"
            kind = "{kind}"
            description = ""

            [card]
            summary = ""

            [docs.readme]
            path = "README.md"
            title = "README"
            """
        ).lstrip(),
        encoding="utf-8",
    )
    readme = root / "README.md"
    if not readme.exists():
        readme.write_text(f"# {package_name}\n\nPsi package.\n", encoding="utf-8")
    return target


def _load_toml(path: Path) -> dict[str, Any]:
    try:
        import tomllib
    except ImportError:  # pragma: no cover - Python 3.10 fallback
        import tomli as tomllib  # type: ignore[no-redef]
    with path.open("rb") as handle:
        return tomllib.load(handle)
