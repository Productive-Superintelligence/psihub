"""PsiHub package models."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, get_args

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictStr,
    ValidationInfo,
    computed_field,
    field_validator,
    model_validator,
)

from ._copy import (
    copy_boundary_value,
    mapping_field_value,
    mapping_sequence_field_value,
    metadata_field_value,
)
from .refs import parse_psi_ref

PackageKind = Literal["tactic", "channel", "service", "app", "library", "mixed"]
ResourceKind = Literal[
    "schema",
    "tactic",
    "service",
    "channel",
    "snapshot",
    "run",
    "config",
    "doc",
    "example",
    "asset",
]
RESOURCE_KIND_VALUES = frozenset(get_args(ResourceKind))
PRIMARY_SECTION_VALUES = frozenset(
    {
        "schemas",
        "tactics",
        "services",
        "channels",
        "snapshots",
        "runs",
        "config",
        "docs",
        "examples",
        "assets",
    }
)


class _MetadataModel(BaseModel):
    @field_validator("metadata", mode="before", check_fields=False)
    @classmethod
    def _validate_metadata(cls, value: Any) -> Any:
        return metadata_field_value("metadata", value)


class PackageInfo(BaseModel):
    """Top-level `[package]` metadata."""

    model_config = ConfigDict(extra="forbid")

    psi_version: StrictStr = "0.1"
    name: StrictStr
    org: StrictStr = "local"
    version: StrictStr = "0.1.0"
    kind: PackageKind = "mixed"
    primary: StrictStr | None = None
    description: StrictStr = ""
    license: StrictStr | None = None
    authors: tuple[StrictStr, ...] = Field(default_factory=tuple)

    def model_post_init(self, __context: Any) -> None:
        _isolate_fields(self, "authors")

    @model_validator(mode="after")
    def _validate_identity(self) -> "PackageInfo":
        _validate_segment(self.org, "package.org")
        _validate_segment(self.name, "package.name")
        _validate_segment(self.version, "package.version")
        if self.primary is not None:
            _validate_primary_ref(self.primary)
        return self

    @computed_field
    @property
    def identifier(self) -> str:
        return f"{self.org}/{self.name}"


class SchemaResource(_MetadataModel):
    model_config = ConfigDict(extra="allow")

    entry: StrictStr | None = None
    description: StrictStr = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        _isolate_fields(self, "metadata")


class TacticResource(_MetadataModel):
    model_config = ConfigDict(extra="allow")

    entry: StrictStr
    input: StrictStr | None = None
    output: StrictStr | None = None
    runtime: StrictStr = "python"
    description: StrictStr = ""
    examples: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        _isolate_fields(self, "examples", "metadata")

    @field_validator("examples", mode="before")
    @classmethod
    def _validate_examples(cls, value: Any) -> Any:
        return mapping_sequence_field_value("examples", value)

    @model_validator(mode="after")
    def _validate_metadata_tokens(self) -> "TacticResource":
        _validate_token(self.runtime, "tactic.runtime")
        return self


class ServiceResource(_MetadataModel):
    model_config = ConfigDict(extra="allow")

    entry: StrictStr | None = None
    tactic: StrictStr | None = None
    transport: StrictStr = "fastapi"
    description: StrictStr = ""
    subscribes: tuple[StrictStr, ...] = Field(default_factory=tuple)
    publishes: tuple[StrictStr, ...] = Field(default_factory=tuple)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        _isolate_fields(self, "subscribes", "publishes", "metadata")

    @model_validator(mode="after")
    def _validate_metadata_tokens(self) -> "ServiceResource":
        _validate_token(self.transport, "service.transport")
        return self


class ChannelResource(_MetadataModel):
    model_config = ConfigDict(extra="allow")

    schema_ref: StrictStr | None = Field(default=None, alias="schema")
    form: StrictStr = "log"
    description: StrictStr = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def schema(self) -> str | None:
        return self.schema_ref

    def model_post_init(self, __context: Any) -> None:
        _isolate_fields(self, "metadata")

    @model_validator(mode="after")
    def _validate_metadata_tokens(self) -> "ChannelResource":
        _validate_token(self.form, "channel.form")
        return self


class SnapshotResource(_MetadataModel):
    model_config = ConfigDict(extra="allow")

    schema_ref: StrictStr | None = Field(default=None, alias="schema")
    channel: StrictStr | None = None
    description: StrictStr = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def schema(self) -> str | None:
        return self.schema_ref

    def model_post_init(self, __context: Any) -> None:
        _isolate_fields(self, "metadata")


class RunResource(_MetadataModel):
    model_config = ConfigDict(extra="allow")

    services: tuple[StrictStr, ...] = Field(default_factory=tuple)
    tactics: tuple[StrictStr, ...] = Field(default_factory=tuple)
    channels: tuple[StrictStr, ...] = Field(default_factory=tuple)
    snapshots: tuple[StrictStr, ...] = Field(default_factory=tuple)
    description: StrictStr = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        _isolate_fields(
            self,
            "services",
            "tactics",
            "channels",
            "snapshots",
            "metadata",
        )


class ConfigResource(_MetadataModel):
    model_config = ConfigDict(extra="allow")

    config_schema: dict[str, Any] = Field(default_factory=dict, alias="schema")
    defaults: dict[str, Any] = Field(default_factory=dict)
    description: StrictStr = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def schema(self) -> dict[str, Any]:
        return copy_boundary_value(self.config_schema)

    def model_post_init(self, __context: Any) -> None:
        _isolate_fields(self, "config_schema", "defaults", "metadata")

    @field_validator("config_schema", "defaults", mode="before")
    @classmethod
    def _validate_public_maps(cls, value: Any, info: ValidationInfo) -> Any:
        return mapping_field_value(info.field_name, value)


class DocResource(_MetadataModel):
    model_config = ConfigDict(extra="allow")

    path: StrictStr
    title: StrictStr = ""
    description: StrictStr = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        _isolate_fields(self, "metadata")


class ExampleResource(_MetadataModel):
    model_config = ConfigDict(extra="allow")

    path: StrictStr | None = None
    command: StrictStr | None = None
    description: StrictStr = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        _isolate_fields(self, "metadata")


class AssetResource(_MetadataModel):
    model_config = ConfigDict(extra="allow")

    path: StrictStr
    media_type: StrictStr = "application/octet-stream"
    description: StrictStr = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        _isolate_fields(self, "metadata")


class CardResource(_MetadataModel):
    model_config = ConfigDict(extra="allow")

    summary: StrictStr = ""
    tags: tuple[StrictStr, ...] = Field(default_factory=tuple)
    safety: StrictStr = ""
    latency: StrictStr = ""
    suggested_commands: tuple[StrictStr, ...] = Field(default_factory=tuple)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        _isolate_fields(self, "tags", "suggested_commands", "metadata")


class PackageManifest(BaseModel):
    """Machine-readable `psi.toml` package contract."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    package: PackageInfo
    schemas: dict[StrictStr, SchemaResource] = Field(default_factory=dict)
    tactics: dict[StrictStr, TacticResource] = Field(default_factory=dict)
    services: dict[StrictStr, ServiceResource] = Field(default_factory=dict)
    channels: dict[StrictStr, ChannelResource] = Field(default_factory=dict)
    snapshots: dict[StrictStr, SnapshotResource] = Field(default_factory=dict)
    runs: dict[StrictStr, RunResource] = Field(default_factory=dict)
    config: ConfigResource | None = None
    docs: dict[StrictStr, DocResource] = Field(default_factory=dict)
    examples: dict[StrictStr, ExampleResource] = Field(default_factory=dict)
    assets: dict[StrictStr, AssetResource] = Field(default_factory=dict)
    card: CardResource | None = None
    base_dir: Path | None = None

    @property
    def identifier(self) -> str:
        return self.package.identifier

    def model_post_init(self, __context: Any) -> None:
        _isolate_fields(
            self,
            "schemas",
            "tactics",
            "services",
            "channels",
            "snapshots",
            "runs",
            "config",
            "docs",
            "examples",
            "assets",
            "card",
        )

    def ref(self, kind: ResourceKind, name: str) -> str:
        _validate_resource_kind(kind)
        _validate_segment(name, f"{kind}.name")
        plural = f"{kind}s" if kind != "schema" else "schemas"
        return f"psi://{self.package.org}/{self.package.name}/{plural}/{name}"


class HubResource(_MetadataModel):
    """Indexed package resource."""

    model_config = ConfigDict(frozen=True)

    kind: ResourceKind
    name: StrictStr
    ref: StrictStr
    entry: StrictStr | None = None
    description: StrictStr = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        _isolate_fields(self, "metadata")

    @model_validator(mode="after")
    def _validate_identity(self) -> "HubResource":
        _validate_segment(self.name, f"{self.kind}.name")
        parsed = parse_psi_ref(self.ref)
        expected_section = "schemas" if self.kind == "schema" else f"{self.kind}s"
        if parsed.resource_kind != expected_section or parsed.name != self.name:
            raise ValueError("resource ref must match resource kind and name.")
        return self


class ValidationIssue(BaseModel):
    model_config = ConfigDict(frozen=True)

    level: Literal["error", "warning"]
    code: StrictStr
    message: StrictStr
    resource: StrictStr | None = None

    @model_validator(mode="after")
    def _validate_code(self) -> "ValidationIssue":
        _validate_token(self.code, "issue.code")
        return self


class ValidationReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    ok: StrictBool
    issues: tuple[ValidationIssue, ...] = Field(default_factory=tuple)

    def model_post_init(self, __context: Any) -> None:
        _isolate_fields(self, "issues")


class PackageRecord(BaseModel):
    """A package stored in the local hub index."""

    model_config = ConfigDict(frozen=True)

    org: StrictStr
    name: StrictStr
    version: StrictStr
    kind: PackageKind
    description: StrictStr = ""
    root: Path
    manifest_path: Path
    resources: tuple[HubResource, ...] = Field(default_factory=tuple)
    validation: ValidationReport = Field(
        default_factory=lambda: ValidationReport(ok=False)
    )
    card: CardResource | None = None

    def model_post_init(self, __context: Any) -> None:
        _isolate_fields(self, "resources", "validation", "card")

    @model_validator(mode="after")
    def _validate_identity(self) -> "PackageRecord":
        _validate_segment(self.org, "record.org")
        _validate_segment(self.name, "record.name")
        _validate_segment(self.version, "record.version")
        for resource in self.resources:
            parsed = parse_psi_ref(resource.ref)
            if parsed.org != self.org or parsed.package != self.name:
                raise ValueError("resource ref must match record identifier.")
        return self

    @computed_field
    @property
    def identifier(self) -> str:
        return f"{self.org}/{self.name}"

    @computed_field
    @property
    def key(self) -> str:
        return f"{self.identifier}@{self.version}"

    def resources_by_kind(self, kind: ResourceKind) -> tuple[HubResource, ...]:
        _validate_resource_kind(kind)
        return tuple(
            resource.model_copy(deep=True)
            for resource in self.resources
            if resource.kind == kind
        )


def _validate_segment(value: str, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value in {".", ".."}
        or any(ch.isspace() for ch in value)
        or any(ch in value for ch in "/:\\%")
    ):
        raise ValueError(f"{field_name} must be a non-empty path segment.")


def _validate_primary_ref(value: str) -> None:
    if not isinstance(value, str) or "." not in value:
        raise ValueError("package.primary must have shape section.name.")
    section, name = value.split(".", 1)
    if section not in PRIMARY_SECTION_VALUES:
        expected = ", ".join(sorted(PRIMARY_SECTION_VALUES))
        raise ValueError(f"package.primary section must be one of: {expected}.")
    _validate_segment(name, "package.primary name")


def _validate_token(value: str, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value in {".", ".."}
        or any(ch.isspace() for ch in value)
        or any(ch in value for ch in "/:\\%")
    ):
        raise ValueError(f"{field_name} must be a non-empty token.")


def _validate_resource_kind(value: str) -> None:
    if not isinstance(value, str) or value not in RESOURCE_KIND_VALUES:
        expected = ", ".join(sorted(RESOURCE_KIND_VALUES))
        raise ValueError(f"resource kind must be one of: {expected}.")


def _isolate_fields(model: BaseModel, *field_names: str) -> None:
    for field_name in field_names:
        object.__setattr__(
            model,
            field_name,
            copy_boundary_value(getattr(model, field_name)),
        )
    extra = getattr(model, "__pydantic_extra__", None)
    if extra is not None:
        object.__setattr__(model, "__pydantic_extra__", copy_boundary_value(extra))
