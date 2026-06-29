"""Local validation for PsiHub packages."""

from __future__ import annotations

import importlib
import sys
from contextlib import contextmanager
from pathlib import Path, PureWindowsPath
from typing import Any, Iterator

from .manifest import load_manifest, manifest_path
from .models import PackageManifest, ValidationIssue, ValidationReport
from .refs import parse_psi_ref

BUILTIN_SCHEMAS = {
    "Any",
    "any",
    "str",
    "string",
    "int",
    "integer",
    "float",
    "bool",
    "boolean",
    "dict",
    "object",
    "list",
    "array",
}
HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
ENDPOINT_MODES = {"run", "stream", "events"}
ENDPOINT_SCOPES = {"store", "channel", "subscription", "artifact", "snapshot"}


def validate_package(path: str | Path) -> ValidationReport:
    issues: list[ValidationIssue] = []
    try:
        manifest = load_manifest(path)
    except Exception as exc:
        return ValidationReport(
            ok=False,
            issues=(_manifest_load_issue(exc),),
        )

    issues.extend(_validate_resource_names(manifest))
    issues.extend(_validate_readme(manifest))
    issues.extend(_validate_card_metadata(manifest))
    issues.extend(_validate_primary(manifest))
    issues.extend(_validate_schemas(manifest))
    issues.extend(_validate_tactics(manifest))
    issues.extend(_validate_services(manifest))
    issues.extend(_validate_channels(manifest))
    issues.extend(_validate_snapshots(manifest))
    issues.extend(_validate_runs(manifest))
    issues.extend(_validate_config(manifest))
    issues.extend(_validate_docs(manifest))
    issues.extend(_validate_examples(manifest))
    issues.extend(_validate_assets(manifest))
    return ValidationReport(
        ok=not any(issue.level == "error" for issue in issues),
        issues=tuple(issues),
    )


def _manifest_load_issue(exc: Exception) -> ValidationIssue:
    message = str(exc)
    return ValidationIssue(
        level="error",
        code=(
            "manifest_duplicate_name"
            if _looks_like_duplicate_toml_name(message)
            else "manifest_load_failed"
        ),
        message=message,
    )


def _looks_like_duplicate_toml_name(message: str) -> bool:
    normalized = message.lower()
    return (
        ("cannot declare" in normalized and "twice" in normalized)
        or ("duplicate" in normalized and "key" in normalized)
        or ("duplicate" in normalized and "table" in normalized)
    )


def import_entrypoint(entry: str, *, base_dir: Path | None = None) -> Any:
    if (
        not isinstance(entry, str)
        or not entry
        or entry != entry.strip()
    ):
        raise ValueError(f"Entrypoint must have shape module:attribute: {entry}")
    module_name, sep, attr_path = entry.partition(":")
    if (
        not sep
        or not _entrypoint_segments(module_name)
        or not _entrypoint_segments(attr_path)
    ):
        raise ValueError(f"Entrypoint must have shape module:attribute: {entry}")
    root_module = module_name.split(".", 1)[0]
    with _import_path(base_dir, root_module=root_module):
        module = importlib.import_module(module_name)
        value: Any = module
        for part in attr_path.split("."):
            value = getattr(value, part)
        return value


def _entrypoint_segments(value: str) -> bool:
    return all(
        part and "%" not in part and not any(ch.isspace() for ch in part)
        for part in value.split(".")
    )


def _validate_readme(manifest: PackageManifest) -> list[ValidationIssue]:
    if manifest.base_dir is None or (manifest.base_dir / "README.md").is_file():
        return []
    return [
        ValidationIssue(
            level="warning",
            code="readme_missing",
            message="Package should include README.md.",
        )
    ]


def _validate_resource_names(manifest: PackageManifest) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    tables = {
        "schemas": manifest.schemas,
        "tactics": manifest.tactics,
        "services": manifest.services,
        "channels": manifest.channels,
        "snapshots": manifest.snapshots,
        "runs": manifest.runs,
        "docs": manifest.docs,
        "examples": manifest.examples,
        "assets": manifest.assets,
    }
    codes = {
        "schemas": "schema_name_invalid",
        "tactics": "tactic_name_invalid",
        "services": "service_name_invalid",
        "channels": "channel_name_invalid",
        "snapshots": "snapshot_name_invalid",
        "runs": "run_name_invalid",
        "docs": "doc_name_invalid",
        "examples": "example_name_invalid",
        "assets": "asset_name_invalid",
    }
    for section, table in tables.items():
        for name in table:
            if _invalid_segment(name):
                issues.append(
                    ValidationIssue(
                        level="error",
                        code=codes[section],
                        message=(
                            f"Resource name must be a non-empty path segment: "
                            f"{section}.{name}"
                        ),
                        resource=f"{section}.{name}",
                    )
                )
    return issues


def _invalid_segment(value: str) -> bool:
    return (
        not isinstance(value, str)
        or not value.strip()
        or value in {".", ".."}
        or any(ch.isspace() for ch in value)
        or any(ch in value for ch in "/:\\%")
    )


def _validate_card_metadata(manifest: PackageManifest) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if manifest.card is None:
        issues.append(
            ValidationIssue(
                level="warning",
                code="card_metadata_missing",
                message="Package should declare [card] metadata for generated cards.",
                resource="card",
            )
        )
    elif not manifest.card.summary and not manifest.package.description:
        issues.append(
            ValidationIssue(
                level="warning",
                code="card_summary_missing",
                message="Package card should include a summary or package description.",
                resource="card.summary",
            )
        )
    if (
        manifest.base_dir is not None
        and (manifest.base_dir / "README.md").is_file()
        and "readme" not in manifest.docs
    ):
        issues.append(
            ValidationIssue(
                level="warning",
                code="readme_doc_missing",
                message="Package README.md should be declared as [docs.readme].",
                resource=manifest.ref("doc", "readme"),
            )
        )
    return issues


def _validate_primary(manifest: PackageManifest) -> list[ValidationIssue]:
    primary = manifest.package.primary
    if not primary:
        if manifest.package.kind in {"tactic", "channel", "service", "app"}:
            return [
                ValidationIssue(
                    level="warning",
                    code="primary_missing_for_kind",
                    message=(
                        f"Package kind {manifest.package.kind!r} should declare "
                        "package.primary."
                    ),
                    resource="package.primary",
                )
            ]
        return []
    if "." not in primary:
        return [
            ValidationIssue(
                level="error",
                code="primary_invalid",
                message="package.primary must look like resources.name.",
                resource="package.primary",
            )
        ]
    section, name = primary.split(".", 1)
    kind_issue = _validate_primary_kind(manifest.package.kind, section, primary)
    if kind_issue is not None:
        return [kind_issue]
    table = {
        "schemas": manifest.schemas,
        "tactics": manifest.tactics,
        "services": manifest.services,
        "channels": manifest.channels,
        "snapshots": manifest.snapshots,
        "runs": manifest.runs,
        "config": {"default": manifest.config} if manifest.config is not None else {},
        "docs": manifest.docs,
        "examples": manifest.examples,
        "assets": manifest.assets,
    }.get(section)
    if table is None or name not in table:
        return [
            ValidationIssue(
                level="error",
                code="primary_missing",
                message=f"package.primary references missing resource {primary!r}.",
                resource="package.primary",
            )
        ]
    return []


def _validate_primary_kind(
    package_kind: str,
    section: str,
    primary: str,
) -> ValidationIssue | None:
    expected = {
        "tactic": {"tactics"},
        "channel": {"channels", "snapshots"},
        "service": {"services"},
        "app": {"services", "runs"},
    }.get(package_kind)
    if expected is None or section in expected:
        return None
    allowed = ", ".join(sorted(expected))
    return ValidationIssue(
        level="error",
        code="primary_kind_mismatch",
        message=(
            f"Package kind {package_kind!r} expects package.primary in "
            f"{allowed}, got {primary!r}."
        ),
        resource="package.primary",
    )


def _validate_schemas(manifest: PackageManifest) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for name, schema in manifest.schemas.items():
        if _invalid_segment(name):
            continue
        if schema.entry:
            issues.extend(_validate_import(schema.entry, manifest, manifest.ref("schema", name)))
    return issues


def _validate_tactics(manifest: PackageManifest) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for name, tactic in manifest.tactics.items():
        if _invalid_segment(name):
            continue
        ref = manifest.ref("tactic", name)
        issues.extend(_validate_import(tactic.entry, manifest, ref))
        for schema_ref in (tactic.input, tactic.output):
            if schema_ref:
                issues.extend(_validate_schema_ref(schema_ref, manifest, ref))
        for index, example in enumerate(tactic.examples, start=1):
            if not any(key in example for key in ("input", "output", "command")):
                issues.append(
                    ValidationIssue(
                        level="warning",
                        code="tactic_example_empty",
                        message=(
                            f"Tactic {name!r} example #{index} should declare "
                            "input, output, or command."
                        ),
                        resource=ref,
                    )
                )
        issues.extend(_validate_endpoint_metadata(tactic, ref))
    return issues


def _validate_services(manifest: PackageManifest) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for name, service in manifest.services.items():
        if _invalid_segment(name):
            continue
        ref = manifest.ref("service", name)
        if not service.entry and not service.tactic:
            issues.append(
                ValidationIssue(
                    level="error",
                    code="service_unbound",
                    message=(
                        f"Service {name!r} must declare an entrypoint or tactic."
                    ),
                    resource=ref,
                )
            )
        if service.entry:
            issues.extend(_validate_import(service.entry, manifest, ref))
        issues.extend(_validate_endpoint_metadata(service, ref))
        issues.extend(_validate_service_port_metadata(service, ref))
        if service.tactic and service.tactic not in manifest.tactics:
            issues.append(
                ValidationIssue(
                    level="error",
                    code="service_tactic_missing",
                    message=f"Service {name!r} references missing tactic {service.tactic!r}.",
                    resource=ref,
                )
            )
        for channel in (*service.subscribes, *service.publishes):
            if channel not in manifest.channels:
                issues.append(
                    ValidationIssue(
                        level="error",
                        code="service_channel_missing",
                        message=f"Service {name!r} references missing channel {channel!r}.",
                        resource=ref,
                    )
                )
    return issues


def _validate_service_port_metadata(service: Any, ref: str) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for port in _declared_service_ports(service):
        if (
            isinstance(port, bool)
            or not isinstance(port, int)
            or not (1 <= port <= 65535)
        ):
            issues.append(
                ValidationIssue(
                    level="error",
                    code="service_port_invalid",
                    message=(
                        "Service port metadata must be an integer between "
                        f"1 and 65535: {port!r}."
                    ),
                    resource=ref,
                )
            )
    return issues


def _declared_service_ports(service: Any) -> tuple[Any, ...]:
    ports: list[Any] = []
    extra = _resource_extra(service)
    if "port" in extra:
        ports.append(extra["port"])
    if "port" in service.metadata:
        ports.append(service.metadata["port"])
    return tuple(ports)


def _validate_channels(manifest: PackageManifest) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for name, channel in manifest.channels.items():
        if _invalid_segment(name):
            continue
        ref = manifest.ref("channel", name)
        if channel.schema:
            issues.extend(
                _validate_schema_ref(
                    channel.schema,
                    manifest,
                    ref,
                )
            )
        issues.extend(_validate_endpoint_metadata(channel, ref))
    return issues


def _validate_snapshots(manifest: PackageManifest) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for name, snapshot in manifest.snapshots.items():
        if _invalid_segment(name):
            continue
        ref = manifest.ref("snapshot", name)
        if snapshot.schema:
            issues.extend(_validate_schema_ref(snapshot.schema, manifest, ref))
        if snapshot.channel and snapshot.channel not in manifest.channels:
            issues.append(
                ValidationIssue(
                    level="error",
                    code="snapshot_channel_missing",
                    message=(
                        f"Snapshot {name!r} references missing channel "
                        f"{snapshot.channel!r}."
                    ),
                    resource=ref,
                )
            )
        issues.extend(_validate_endpoint_metadata(snapshot, ref))
    return issues


def _validate_runs(manifest: PackageManifest) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for name, run in manifest.runs.items():
        if _invalid_segment(name):
            continue
        ref = manifest.ref("run", name)
        for service in run.services:
            if service not in manifest.services:
                issues.append(_missing(ref, "run_service_missing", name, service))
        for tactic in run.tactics:
            if tactic not in manifest.tactics:
                issues.append(_missing(ref, "run_tactic_missing", name, tactic))
        for channel in run.channels:
            if channel not in manifest.channels:
                issues.append(_missing(ref, "run_channel_missing", name, channel))
        for snapshot in run.snapshots:
            if snapshot not in manifest.snapshots:
                issues.append(_missing(ref, "run_snapshot_missing", name, snapshot))
    return issues


def _validate_config(manifest: PackageManifest) -> list[ValidationIssue]:
    config = manifest.config
    if config is None or not config.schema:
        return []
    issues: list[ValidationIssue] = []
    unknown_defaults = sorted(set(config.defaults) - set(config.schema))
    for key in unknown_defaults:
        issues.append(
            ValidationIssue(
                level="warning",
                code="config_default_without_schema",
                message=f"Config default {key!r} has no schema entry.",
                resource=manifest.ref("config", "default"),
            )
        )
    return issues


def _validate_docs(manifest: PackageManifest) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for name, doc in manifest.docs.items():
        if _invalid_segment(name):
            continue
        issues.extend(
            _validate_declared_file(
                manifest,
                path=doc.path,
                resource=manifest.ref("doc", name),
                code="doc_path_missing",
                label=f"Doc {name!r}",
            )
        )
    return issues


def _validate_examples(manifest: PackageManifest) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for name, example in manifest.examples.items():
        if _invalid_segment(name):
            continue
        ref = manifest.ref("example", name)
        if not example.path and not example.command:
            issues.append(
                ValidationIssue(
                    level="warning",
                    code="example_empty",
                    message=f"Example {name!r} should declare a path or command.",
                    resource=ref,
                )
            )
        if example.path:
            issues.extend(
                _validate_declared_file(
                    manifest,
                    path=example.path,
                    resource=ref,
                    code="example_path_missing",
                    label=f"Example {name!r}",
                )
            )
    return issues


def _validate_assets(manifest: PackageManifest) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for name, asset in manifest.assets.items():
        if _invalid_segment(name):
            continue
        issues.extend(
            _validate_declared_file(
                manifest,
                path=asset.path,
                resource=manifest.ref("asset", name),
                code="asset_path_missing",
                label=f"Asset {name!r}",
            )
        )
    return issues


def _validate_import(
    entry: str,
    manifest: PackageManifest,
    resource: str,
) -> list[ValidationIssue]:
    try:
        import_entrypoint(entry, base_dir=manifest.base_dir)
    except Exception as exc:
        return [
            ValidationIssue(
                level="error",
                code="entrypoint_import_failed",
                message=str(exc),
                resource=resource,
            )
        ]
    return []


def _validate_declared_file(
    manifest: PackageManifest,
    *,
    path: str,
    resource: str,
    code: str,
    label: str,
) -> list[ValidationIssue]:
    if manifest.base_dir is None:
        return []
    if Path(path).is_absolute() or PureWindowsPath(path).is_absolute():
        return [
            ValidationIssue(
                level="error",
                code=code.replace("_missing", "_absolute_path"),
                message=f"{label} file path must be relative to the package: {path}",
                resource=resource,
            )
        ]
    base_dir = manifest.base_dir.resolve()
    target = (base_dir / path).resolve()
    if not _is_relative_to(target, base_dir):
        return [
            ValidationIssue(
                level="error",
                code=code.replace("_missing", "_outside_package"),
                message=f"{label} file must stay inside the package: {path}",
                resource=resource,
            )
        ]
    if target.is_file():
        return []
    return [
        ValidationIssue(
            level="error",
            code=code,
            message=f"{label} file does not exist: {path}",
            resource=resource,
        )
    ]


def _is_relative_to(path: Path, base_dir: Path) -> bool:
    try:
        path.relative_to(base_dir)
    except ValueError:
        return False
    return True


def _validate_schema_ref(
    schema_ref: str,
    manifest: PackageManifest,
    resource: str,
) -> list[ValidationIssue]:
    if schema_ref in BUILTIN_SCHEMAS or schema_ref in manifest.schemas:
        return []
    if schema_ref.startswith("psi://"):
        try:
            parsed = parse_psi_ref(schema_ref)
        except ValueError:
            return [
                ValidationIssue(
                    level="error",
                    code="schema_ref_invalid",
                    message=f"Schema ref {schema_ref!r} is not a valid psi:// ref.",
                    resource=resource,
                )
            ]
        if parsed.resource_kind != "schemas":
            return [
                ValidationIssue(
                    level="error",
                    code="schema_ref_kind_mismatch",
                    message=(
                        f"Schema ref {schema_ref!r} must point at schemas, "
                        f"not {parsed.resource_kind!r}."
                    ),
                    resource=resource,
                )
            ]
        if (
            parsed.org == manifest.package.org
            and parsed.package == manifest.package.name
            and parsed.name not in manifest.schemas
        ):
            return [
                ValidationIssue(
                    level="error",
                    code="schema_ref_missing",
                    message=f"Schema ref {schema_ref!r} is not declared.",
                    resource=resource,
                )
            ]
        return []
    if ":" in schema_ref:
        return _validate_import(schema_ref, manifest, resource)
    return [
        ValidationIssue(
            level="error",
            code="schema_ref_missing",
            message=f"Schema ref {schema_ref!r} is not declared.",
            resource=resource,
        )
    ]


def _validate_endpoint_metadata(
    resource_model: Any,
    resource: str,
) -> list[ValidationIssue]:
    endpoints = _resource_extra(resource_model).get("endpoints")
    metadata = getattr(resource_model, "metadata", None)
    if endpoints is None and isinstance(metadata, dict):
        endpoints = metadata.get("endpoints")
    if endpoints is None:
        return []
    if not isinstance(endpoints, list):
        return [
            ValidationIssue(
                level="error",
                code="endpoint_metadata_invalid",
                message="Endpoint metadata must be a list.",
                resource=resource,
            )
        ]
    issues: list[ValidationIssue] = []
    for index, endpoint in enumerate(endpoints, start=1):
        if not isinstance(endpoint, dict):
            issues.append(
                ValidationIssue(
                    level="error",
                    code="endpoint_metadata_invalid",
                    message=f"Endpoint #{index} must be a table/object.",
                    resource=resource,
                )
            )
            continue
        method_value = endpoint.get("method")
        method = (
            method_value.upper()
            if isinstance(method_value, str)
            and method_value
            and not any(ch.isspace() for ch in method_value)
            else ""
        )
        if method not in HTTP_METHODS:
            issues.append(
                ValidationIssue(
                    level="error",
                    code="endpoint_method_invalid",
                    message=f"Endpoint #{index} declares invalid method {method!r}.",
                    resource=resource,
                )
            )
        path = endpoint.get("path")
        if not _valid_endpoint_path(path):
            issues.append(
                ValidationIssue(
                    level="error",
                    code="endpoint_path_invalid",
                    message=(
                        f"Endpoint #{index} path must be an absolute route path "
                        "without whitespace, percent escapes, query, fragment, "
                        "or network-path prefix."
                    ),
                    resource=resource,
                )
            )
        name = endpoint.get("name")
        if name is not None and not _valid_endpoint_label(name):
            issues.append(
                ValidationIssue(
                    level="error",
                    code="endpoint_name_invalid",
                    message=(
                        f"Endpoint #{index} declares invalid name {name!r}; "
                        "names must not contain whitespace or percent escapes."
                    ),
                    resource=resource,
                )
            )
        mode = endpoint.get("mode")
        if mode is not None and mode not in ENDPOINT_MODES:
            issues.append(
                ValidationIssue(
                    level="error",
                    code="endpoint_mode_invalid",
                    message=f"Endpoint #{index} declares invalid mode {mode!r}.",
                    resource=resource,
                )
            )
        scope = endpoint.get("scope")
        if scope is not None and scope not in ENDPOINT_SCOPES:
            issues.append(
                ValidationIssue(
                    level="error",
                    code="endpoint_scope_invalid",
                    message=f"Endpoint #{index} declares invalid scope {scope!r}.",
                    resource=resource,
                )
            )
        description = endpoint.get("description")
        if description is not None and not isinstance(description, str):
            issues.append(
                ValidationIssue(
                    level="error",
                    code="endpoint_description_invalid",
                    message=f"Endpoint #{index} description must be a string.",
                    resource=resource,
                )
            )
        tags = endpoint.get("tags")
        if tags is not None and not _valid_endpoint_tags(tags):
            issues.append(
                ValidationIssue(
                    level="error",
                    code="endpoint_tags_invalid",
                    message=(
                        f"Endpoint #{index} tags must be non-empty strings "
                        "without whitespace or percent escapes."
                    ),
                    resource=resource,
                )
            )
    return issues


def _valid_endpoint_path(path: Any) -> bool:
    return (
        isinstance(path, str)
        and path.startswith("/")
        and not path.startswith("//")
        and "%" not in path
        and not any(ch.isspace() for ch in path)
        and "?" not in path
        and "#" not in path
        and "://" not in path
    )


def _valid_endpoint_label(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and "%" not in value
        and not any(ch.isspace() for ch in value)
    )


def _valid_endpoint_tags(tags: Any) -> bool:
    return (
        isinstance(tags, list)
        and all(_valid_endpoint_label(tag) for tag in tags)
    )


def _resource_extra(resource_model: Any) -> dict[str, Any]:
    return dict(getattr(resource_model, "model_extra", None) or {})


def _missing(ref: str, code: str, run_name: str, missing_name: str) -> ValidationIssue:
    return ValidationIssue(
        level="error",
        code=code,
        message=f"Run {run_name!r} references missing resource {missing_name!r}.",
        resource=ref,
    )


@contextmanager
def _import_path(
    base_dir: Path | None,
    *,
    root_module: str | None = None,
) -> Iterator[None]:
    if base_dir is None:
        yield
        return
    value = str(base_dir)
    isolated_modules: dict[str, Any] = {}
    isolate = root_module is not None and (
        (base_dir / root_module).exists() or (base_dir / f"{root_module}.py").exists()
    )
    if isolate:
        for name in list(sys.modules):
            if name == root_module or name.startswith(f"{root_module}."):
                isolated_modules[name] = sys.modules.pop(name)
    sys.path.insert(0, value)
    importlib.invalidate_caches()
    try:
        yield
    finally:
        try:
            sys.path.remove(value)
        except ValueError:
            pass
        if isolate:
            for name in list(sys.modules):
                if name == root_module or name.startswith(f"{root_module}."):
                    sys.modules.pop(name, None)
            sys.modules.update(isolated_modules)
        importlib.invalidate_caches()
