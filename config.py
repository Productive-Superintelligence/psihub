"""Local `.psi/config.toml` ref resolution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


PSI_REF_SECTIONS = {
    "schemas",
    "tactics",
    "services",
    "channels",
    "runs",
    "configs",
    "docs",
    "examples",
    "assets",
}


@dataclass(frozen=True)
class ResolvedRef:
    ref: str
    url: str | None = None
    store: str | None = None
    path: str | None = None
    object: Any = None
    metadata: dict[str, Any] | None = None


class LocalConfigResolver:
    """Resolve `psi://...` refs from local config and object bindings."""

    def __init__(self) -> None:
        self._bindings: dict[str, ResolvedRef] = {}

    @classmethod
    def from_file(cls, path: str | Path) -> "LocalConfigResolver":
        resolver = cls()
        target = Path(path)
        if target.is_dir():
            target = target / ".psi" / "config.toml"
        data = _load_toml(target)
        refs = data.get("refs", {})
        if not isinstance(refs, dict):
            raise ValueError("[refs] must be a TOML table.")
        for ref, binding in refs.items():
            if not isinstance(binding, dict):
                raise ValueError(f"Ref binding must be a table: {ref}")
            resolver.bind(
                ref,
                url=binding.get("url"),
                store=binding.get("store"),
                path=binding.get("path"),
                metadata={key: value for key, value in binding.items() if key not in {"url", "store", "path"}},
            )
        return resolver

    @classmethod
    def from_text(cls, text: str, *, root: str | Path | None = None) -> "LocalConfigResolver":
        root_path = Path(root or ".")
        target = root_path / ".psi" / "config.toml"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return cls.from_file(root_path)

    def bind(
        self,
        ref: str,
        *,
        url: str | None = None,
        store: str | None = None,
        path: str | None = None,
        object: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        _validate_psi_ref(ref)
        self._bindings[ref] = ResolvedRef(
            ref=ref,
            url=url,
            store=store,
            path=path,
            object=object,
            metadata=metadata or {},
        )

    def resolve(self, ref: str) -> ResolvedRef:
        try:
            return self._bindings[ref]
        except KeyError as exc:
            raise KeyError(f"Ref is not bound: {ref}") from exc

    def refs(self) -> tuple[str, ...]:
        return tuple(sorted(self._bindings))


def _load_toml(path: Path) -> dict[str, Any]:
    try:
        import tomllib
    except ImportError:  # pragma: no cover - Python 3.10 fallback
        import tomli as tomllib  # type: ignore[no-redef]
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _validate_psi_ref(ref: str) -> None:
    parsed = urlparse(ref)
    if parsed.scheme != "psi":
        raise ValueError(f"Ref must use psi:// scheme: {ref}")
    if parsed.params or parsed.query or parsed.fragment:
        raise ValueError(f"Ref must not include params, query, or fragment: {ref}")
    org = parsed.netloc.strip()
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 3:
        raise ValueError(f"Ref must have shape psi://org/package/resources/name: {ref}")
    package, resource_kind, name = parts
    if not org or not package or not name:
        raise ValueError(f"Ref contains an empty segment: {ref}")
    if resource_kind not in PSI_REF_SECTIONS:
        raise ValueError(f"Ref uses unknown resource section {resource_kind!r}: {ref}")
    for segment in (org, package, name):
        if any(ch in segment for ch in ":\\"):
            raise ValueError(f"Ref contains an invalid segment: {ref}")
