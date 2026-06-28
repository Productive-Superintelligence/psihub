"""PsiHub package models."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

PackageKind = Literal["tactic", "channel", "service", "app", "library", "mixed"]
ResourceKind = Literal["schema", "tactic", "service", "channel", "run"]


class PackageInfo(BaseModel):
    """Top-level `[package]` metadata."""

    model_config = ConfigDict(extra="forbid")

    psi_version: str = "0.1"
    name: str
    org: str = "local"
    version: str = "0.1.0"
    kind: PackageKind = "mixed"
    primary: str | None = None
    description: str = ""
    license: str | None = None
    authors: tuple[str, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _validate_identity(self) -> "PackageInfo":
        _validate_segment(self.org, "package.org")
        _validate_segment(self.name, "package.name")
        return self

    @computed_field
    @property
    def identifier(self) -> str:
        return f"{self.org}/{self.name}"


class SchemaResource(BaseModel):
    model_config = ConfigDict(extra="allow")

    entry: str | None = None
    description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class TacticResource(BaseModel):
    model_config = ConfigDict(extra="allow")

    entry: str
    input: str | None = None
    output: str | None = None
    runtime: str = "python"
    description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ServiceResource(BaseModel):
    model_config = ConfigDict(extra="allow")

    entry: str | None = None
    tactic: str | None = None
    transport: str = "fastapi"
    description: str = ""
    subscribes: tuple[str, ...] = Field(default_factory=tuple)
    publishes: tuple[str, ...] = Field(default_factory=tuple)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChannelResource(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_ref: str | None = Field(default=None, alias="schema")
    form: str = "log"
    description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def schema(self) -> str | None:
        return self.schema_ref


class RunResource(BaseModel):
    model_config = ConfigDict(extra="allow")

    services: tuple[str, ...] = Field(default_factory=tuple)
    tactics: tuple[str, ...] = Field(default_factory=tuple)
    channels: tuple[str, ...] = Field(default_factory=tuple)
    description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class PackageManifest(BaseModel):
    """Machine-readable `psi.toml` package contract."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    package: PackageInfo
    schemas: dict[str, SchemaResource] = Field(default_factory=dict)
    tactics: dict[str, TacticResource] = Field(default_factory=dict)
    services: dict[str, ServiceResource] = Field(default_factory=dict)
    channels: dict[str, ChannelResource] = Field(default_factory=dict)
    runs: dict[str, RunResource] = Field(default_factory=dict)
    base_dir: Path | None = None

    @property
    def identifier(self) -> str:
        return self.package.identifier

    def ref(self, kind: ResourceKind, name: str) -> str:
        plural = f"{kind}s" if kind != "schema" else "schemas"
        return f"psi://{self.package.org}/{self.package.name}/{plural}/{name}"


class HubResource(BaseModel):
    """Indexed package resource."""

    model_config = ConfigDict(frozen=True)

    kind: ResourceKind
    name: str
    ref: str
    entry: str | None = None
    description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ValidationIssue(BaseModel):
    model_config = ConfigDict(frozen=True)

    level: Literal["error", "warning"]
    code: str
    message: str
    resource: str | None = None


class ValidationReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    ok: bool
    issues: tuple[ValidationIssue, ...] = Field(default_factory=tuple)


class PackageRecord(BaseModel):
    """A package stored in the local hub index."""

    model_config = ConfigDict(frozen=True)

    org: str
    name: str
    version: str
    kind: PackageKind
    description: str = ""
    root: Path
    manifest_path: Path
    resources: tuple[HubResource, ...] = Field(default_factory=tuple)
    validation: ValidationReport = Field(
        default_factory=lambda: ValidationReport(ok=False)
    )

    @computed_field
    @property
    def identifier(self) -> str:
        return f"{self.org}/{self.name}"

    @computed_field
    @property
    def key(self) -> str:
        return f"{self.identifier}@{self.version}"

    def resources_by_kind(self, kind: ResourceKind) -> tuple[HubResource, ...]:
        return tuple(resource for resource in self.resources if resource.kind == kind)


def _validate_segment(value: str, field_name: str) -> None:
    if not value or any(ch in value for ch in "/:\\"):
        raise ValueError(f"{field_name} must be a non-empty path segment.")
