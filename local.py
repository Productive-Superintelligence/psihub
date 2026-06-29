"""Disk-backed local PsiHub."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .cards import render_agent_card, render_config_template, render_package_card
from .manifest import load_manifest, manifest_path, require_path_value
from .models import HubResource, PackageManifest, PackageRecord, ValidationReport
from .validator import validate_package


PUBLISH_IGNORE_NAMES = {
    ".git",
    ".mypy_cache",
    ".psi",
    ".psihub",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "htmlcov",
    "site",
    "venv",
}
SAFE_ENV_TEMPLATE_NAMES = {
    ".env.example",
    ".env.sample",
    ".env.template",
}


class PublishValidationError(ValueError):
    """Raised when validated publish receives an invalid package."""

    def __init__(self, report: ValidationReport) -> None:
        self.report = report
        super().__init__("Package validation failed.")


class LocalHub:
    """A deterministic local package hub."""

    def __init__(self, root: str | Path = ".psihub") -> None:
        self.root = Path(require_path_value(root, "hub root")).expanduser().resolve()
        self.packages_dir = self.root / "packages"
        self.index_dir = self.root / "index"
        self.index_path = self.index_dir / "packages.json"
        self.packages_dir.mkdir(parents=True, exist_ok=True)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self._records: dict[str, PackageRecord] = {}
        self._load()

    def publish(self, package_path: str | Path, *, validate: bool = True) -> PackageRecord:
        source_manifest = load_manifest(package_path)
        report = validate_package(package_path) if validate else ValidationReport(ok=True)
        if validate and not report.ok:
            raise PublishValidationError(report)
        destination = self._package_destination(source_manifest)
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(
            source_manifest.base_dir or manifest_path(package_path).parent,
            destination,
            ignore=_publish_ignore,
        )
        manifest = load_manifest(destination)
        record = record_from_manifest(manifest, validation=report)
        self._records[record.key] = record
        self._write()
        return record.model_copy(deep=True)

    def get(self, identifier: str, *, version: str | None = None) -> PackageRecord:
        org, name = _split_identifier(identifier)
        matches = [
            record
            for record in self._records.values()
            if record.org == org and record.name == name
        ]
        if version is not None:
            _validate_identifier_segment(version, "package version")
            matches = [record for record in matches if record.version == version]
        if not matches:
            raise KeyError(f"Package not found: {identifier}")
        return sorted(matches, key=lambda record: _version_sort_key(record.version))[
            -1
        ].model_copy(
            deep=True
        )

    def download(
        self,
        identifier: str,
        destination: str | Path,
        *,
        version: str | None = None,
    ) -> Path:
        destination_root = Path(
            require_path_value(destination, "download destination")
        ).expanduser()
        record = self.get(identifier, version=version)
        target = destination_root / record.name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(record.root, target)
        return target

    def list(self) -> tuple[PackageRecord, ...]:
        return tuple(
            record.model_copy(deep=True)
            for record in sorted(self._records.values(), key=lambda record: record.key)
        )

    def card(self, identifier: str, *, version: str | None = None) -> str:
        return render_package_card(self.get(identifier, version=version))

    def agent_card(self, identifier: str, *, version: str | None = None) -> str:
        return render_agent_card(self.get(identifier, version=version))

    def config_template(self, identifier: str, *, version: str | None = None) -> str:
        return render_config_template(self.get(identifier, version=version))

    def _package_destination(self, manifest: PackageManifest) -> Path:
        return (
            self.packages_dir
            / manifest.package.org
            / manifest.package.name
            / manifest.package.version
        )

    def _load(self) -> None:
        if not self.index_path.is_file():
            return
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid local hub index: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("Invalid local hub index: root must be an object.")
        records = data.get("records", [])
        if not isinstance(records, list):
            raise ValueError("Invalid local hub index: records must be a list.")

        loaded: dict[str, PackageRecord] = {}
        for index, item in enumerate(records):
            if not isinstance(item, dict):
                raise ValueError(
                    f"Invalid local hub index record {index}: must be an object."
                )
            key = item.get("key")
            if not isinstance(key, str) or not key.strip():
                raise ValueError(
                    f"Invalid local hub index record {index}: key must be a string."
                )
            raw_record = item.get("record")
            if not isinstance(raw_record, dict):
                raise ValueError(
                    f"Invalid local hub index record {index}: record must be an object."
                )
            record = PackageRecord.model_validate(raw_record)
            if key != record.key:
                raise ValueError(
                    f"Invalid local hub index record {index}: key does not match record."
                )
            if key in loaded:
                raise ValueError(
                    f"Invalid local hub index record {index}: duplicate key."
                )
            loaded[key] = record
        self._records = loaded

    def _write(self) -> None:
        payload: dict[str, Any] = {
            "records": [
                {
                    "key": record.key,
                    "record": record.model_dump(mode="json"),
                }
                for record in self.list()
            ]
        }
        self.index_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def record_from_manifest(
    manifest: PackageManifest,
    *,
    validation: ValidationReport | None = None,
) -> PackageRecord:
    resources: list[HubResource] = []
    for name, schema in manifest.schemas.items():
        resources.append(
            HubResource(
                kind="schema",
                name=name,
                ref=manifest.ref("schema", name),
                entry=schema.entry,
                description=schema.description,
                metadata={**_resource_extra(schema), **schema.metadata},
            )
        )
    for name, tactic in manifest.tactics.items():
        resources.append(
            HubResource(
                kind="tactic",
                name=name,
                ref=manifest.ref("tactic", name),
                entry=tactic.entry,
                description=tactic.description,
                metadata={
                    "runtime": tactic.runtime,
                    "input": tactic.input,
                    "output": tactic.output,
                    **_resource_extra(tactic),
                    **tactic.metadata,
                    "examples": list(tactic.examples),
                },
            )
        )
    for name, service in manifest.services.items():
        resources.append(
            HubResource(
                kind="service",
                name=name,
                ref=manifest.ref("service", name),
                entry=service.entry,
                description=service.description,
                metadata={
                    "tactic": service.tactic,
                    "transport": service.transport,
                    "subscribes": list(service.subscribes),
                    "publishes": list(service.publishes),
                    **_resource_extra(service),
                    **service.metadata,
                },
            )
        )
    for name, channel in manifest.channels.items():
        resources.append(
            HubResource(
                kind="channel",
                name=name,
                ref=manifest.ref("channel", name),
                description=channel.description,
                metadata={
                    "schema": channel.schema,
                    "form": channel.form,
                    **_resource_extra(channel),
                    **channel.metadata,
                },
            )
        )
    for name, snapshot in manifest.snapshots.items():
        resources.append(
            HubResource(
                kind="snapshot",
                name=name,
                ref=manifest.ref("snapshot", name),
                description=snapshot.description,
                metadata={
                    "schema": snapshot.schema,
                    "channel": snapshot.channel,
                    **_resource_extra(snapshot),
                    **snapshot.metadata,
                },
            )
        )
    for name, run in manifest.runs.items():
        resources.append(
            HubResource(
                kind="run",
                name=name,
                ref=manifest.ref("run", name),
                description=run.description,
                metadata={
                    "services": list(run.services),
                    "tactics": list(run.tactics),
                    "channels": list(run.channels),
                    "snapshots": list(run.snapshots),
                    **_resource_extra(run),
                    **run.metadata,
                },
            )
        )
    if manifest.config is not None:
        resources.append(
            HubResource(
                kind="config",
                name="default",
                ref=manifest.ref("config", "default"),
                description=manifest.config.description,
                metadata={
                    "schema": manifest.config.schema,
                    "defaults": manifest.config.defaults,
                    **_resource_extra(manifest.config),
                    **manifest.config.metadata,
                },
            )
        )
    for name, doc in manifest.docs.items():
        resources.append(
            HubResource(
                kind="doc",
                name=name,
                ref=manifest.ref("doc", name),
                entry=doc.path,
                description=doc.description,
                metadata={
                    "title": doc.title,
                    "path": doc.path,
                    **_resource_extra(doc),
                    **doc.metadata,
                },
            )
        )
    for name, example in manifest.examples.items():
        resources.append(
            HubResource(
                kind="example",
                name=name,
                ref=manifest.ref("example", name),
                entry=example.path,
                description=example.description,
                metadata={
                    "path": example.path,
                    "command": example.command,
                    **_resource_extra(example),
                    **example.metadata,
                },
            )
        )
    for name, asset in manifest.assets.items():
        resources.append(
            HubResource(
                kind="asset",
                name=name,
                ref=manifest.ref("asset", name),
                entry=asset.path,
                description=asset.description,
                metadata={
                    "path": asset.path,
                    "media_type": asset.media_type,
                    **_resource_extra(asset),
                    **asset.metadata,
                },
            )
        )
    return PackageRecord(
        org=manifest.package.org,
        name=manifest.package.name,
        version=manifest.package.version,
        kind=manifest.package.kind,
        description=manifest.package.description,
        root=manifest.base_dir or Path.cwd(),
        manifest_path=(manifest.base_dir or Path.cwd()) / "psi.toml",
        resources=tuple(resources),
        validation=validation or ValidationReport(ok=False),
        card=manifest.card,
    )


def _resource_extra(resource: Any) -> dict[str, Any]:
    return dict(getattr(resource, "model_extra", None) or {})


def _publish_ignore(directory: str, names: list[str]) -> set[str]:
    del directory
    return {name for name in names if _should_ignore_publish_name(name)}


def _should_ignore_publish_name(name: str) -> bool:
    if name in PUBLISH_IGNORE_NAMES:
        return True
    if name == ".env":
        return True
    if name.startswith(".env.") and name not in SAFE_ENV_TEMPLATE_NAMES:
        return True
    return (
        name.endswith(".egg-info")
        or name.endswith(".pyc")
        or name.endswith(".pyo")
        or name == ".coverage"
    )


def _split_identifier(identifier: str) -> tuple[str, str]:
    if not isinstance(identifier, str) or not identifier.strip():
        raise ValueError("Package identifier must have shape org/name.")
    parts = identifier.split("/")
    if len(parts) != 2:
        raise ValueError("Package identifier must have shape org/name.")
    org, name = parts
    _validate_identifier_segment(org, "package identifier org")
    _validate_identifier_segment(name, "package identifier name")
    return org, name


def _validate_identifier_segment(value: str, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value in {".", ".."}
        or any(ch.isspace() for ch in value)
        or any(ch in value for ch in "/:\\%")
    ):
        raise ValueError(f"{field_name} must be a non-empty path segment.")


def _version_sort_key(version: str) -> tuple[Any, ...]:
    public, _, _local = version.partition("+")
    release, prerelease_separator, prerelease = public.partition("-")
    release_parts = release.split(".")
    if release_parts and all(part.isdecimal() for part in release_parts):
        return (
            1,
            tuple(int(part) for part in release_parts),
            1 if not prerelease_separator else 0,
            _natural_text_key(prerelease),
        )
    return (0, _natural_text_key(version))


def _natural_text_key(text: str) -> tuple[tuple[int, int | str], ...]:
    parts: list[tuple[int, int | str]] = []
    current = ""
    current_is_digit: bool | None = None
    for char in text:
        is_digit = char.isdigit()
        if current and current_is_digit != is_digit:
            parts.append(_natural_text_part(current, current_is_digit))
            current = char
            current_is_digit = is_digit
            continue
        current += char
        current_is_digit = is_digit
    if current:
        parts.append(_natural_text_part(current, current_is_digit))
    return tuple(parts)


def _natural_text_part(text: str, is_digit: bool | None) -> tuple[int, int | str]:
    if is_digit:
        return (0, int(text))
    return (1, text.lower())
