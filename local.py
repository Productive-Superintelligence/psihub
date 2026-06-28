"""Disk-backed local PsiHub."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .cards import render_agent_card, render_config_template, render_package_card
from .manifest import load_manifest, manifest_path
from .models import HubResource, PackageManifest, PackageRecord, ValidationReport
from .validator import validate_package


class PublishValidationError(ValueError):
    """Raised when validated publish receives an invalid package."""

    def __init__(self, report: ValidationReport) -> None:
        self.report = report
        super().__init__("Package validation failed.")


class LocalHub:
    """A deterministic local package hub."""

    def __init__(self, root: str | Path = ".psihub") -> None:
        self.root = Path(root).expanduser().resolve()
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
            ignore=shutil.ignore_patterns(
                ".git",
                "__pycache__",
                ".pytest_cache",
                "*.egg-info",
                "build",
                "dist",
            ),
        )
        manifest = load_manifest(destination)
        record = record_from_manifest(manifest, validation=report)
        self._records[record.key] = record
        self._write()
        return record

    def get(self, identifier: str, *, version: str | None = None) -> PackageRecord:
        org, name = _split_identifier(identifier)
        matches = [
            record
            for record in self._records.values()
            if record.org == org and record.name == name
        ]
        if version is not None:
            matches = [record for record in matches if record.version == version]
        if not matches:
            raise KeyError(f"Package not found: {identifier}")
        return sorted(matches, key=lambda record: record.version)[-1]

    def download(
        self,
        identifier: str,
        destination: str | Path,
        *,
        version: str | None = None,
    ) -> Path:
        record = self.get(identifier, version=version)
        target = Path(destination).expanduser() / record.name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(record.root, target)
        return target

    def list(self) -> tuple[PackageRecord, ...]:
        return tuple(sorted(self._records.values(), key=lambda record: record.key))

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
        data = json.loads(self.index_path.read_text(encoding="utf-8"))
        self._records = {
            item["key"]: PackageRecord.model_validate(item["record"])
            for item in data.get("records", [])
        }

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


def _split_identifier(identifier: str) -> tuple[str, str]:
    if "/" not in identifier:
        raise ValueError("Package identifier must have shape org/name.")
    org, name = identifier.split("/", 1)
    return org, name
