"""Local `.psi/config.toml` ref resolution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .refs import validate_psi_ref


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
        self._settings: dict[str, Any] = {}
        self._services: dict[str, dict[str, Any]] = {}
        self._stores: dict[str, dict[str, Any]] = {}

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
        settings = data.get("settings", {})
        if not isinstance(settings, dict):
            raise ValueError("[settings] must be a TOML table.")
        resolver._settings = dict(settings)
        resolver._services = _table_of_tables(data.get("services", {}), "services")
        resolver._stores = _table_of_tables(data.get("stores", {}), "stores")
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
        validate_psi_ref(ref)
        _validate_target(ref, url=url, store=store, path=path, object=object)
        self._bindings[ref] = ResolvedRef(
            ref=ref,
            url=url,
            store=store,
            path=path,
            object=object,
            metadata=metadata or {},
        )

    def resolve(self, ref: str) -> ResolvedRef:
        validate_psi_ref(ref)
        try:
            return self._bindings[ref]
        except KeyError as exc:
            raise KeyError(f"Ref is not bound: {ref}") from exc

    def refs(self) -> tuple[str, ...]:
        return tuple(sorted(self._bindings))

    def settings(self) -> dict[str, Any]:
        return dict(self._settings)

    def setting(self, key: str, default: Any = None) -> Any:
        return self._settings.get(key, default)

    def services(self) -> dict[str, dict[str, Any]]:
        return {name: dict(value) for name, value in self._services.items()}

    def service(self, name: str) -> dict[str, Any]:
        try:
            return dict(self._services[name])
        except KeyError as exc:
            raise KeyError(f"Service config is not bound: {name}") from exc

    def stores(self) -> dict[str, dict[str, Any]]:
        return {name: dict(value) for name, value in self._stores.items()}

    def store(self, name: str) -> dict[str, Any]:
        try:
            return dict(self._stores[name])
        except KeyError as exc:
            raise KeyError(f"Store config is not bound: {name}") from exc


def _load_toml(path: Path) -> dict[str, Any]:
    try:
        import tomllib
    except ImportError:  # pragma: no cover - Python 3.10 fallback
        import tomli as tomllib  # type: ignore[no-redef]
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _table_of_tables(value: Any, name: str) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        raise ValueError(f"[{name}] must be a TOML table.")
    result: dict[str, dict[str, Any]] = {}
    for key, item in value.items():
        if not isinstance(item, dict):
            raise ValueError(f"[{name}.{key}] must be a TOML table.")
        result[str(key)] = dict(item)
    return result


def _validate_target(
    ref: str,
    *,
    url: str | None,
    store: str | None,
    path: str | None,
    object: Any,
) -> None:
    targets = {
        "url": url,
        "store": store,
        "path": path,
        "object": object,
    }
    active = [name for name, value in targets.items() if value is not None]
    if len(active) == 1:
        return
    if not active:
        raise ValueError(f"Ref binding must declare one concrete target: {ref}")
    targets_text = ", ".join(active)
    raise ValueError(
        "Ref binding must declare only one concrete target, "
        f"got {targets_text}: {ref}"
    )
