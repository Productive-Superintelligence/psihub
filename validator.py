"""Local validation for PsiHub packages."""

from __future__ import annotations

import importlib
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .manifest import load_manifest, manifest_path
from .models import PackageManifest, ValidationIssue, ValidationReport

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


def validate_package(path: str | Path) -> ValidationReport:
    issues: list[ValidationIssue] = []
    try:
        manifest = load_manifest(path)
    except Exception as exc:
        return ValidationReport(
            ok=False,
            issues=(
                ValidationIssue(
                    level="error",
                    code="manifest_load_failed",
                    message=str(exc),
                ),
            ),
        )

    issues.extend(_validate_readme(manifest))
    issues.extend(_validate_primary(manifest))
    issues.extend(_validate_schemas(manifest))
    issues.extend(_validate_tactics(manifest))
    issues.extend(_validate_services(manifest))
    issues.extend(_validate_channels(manifest))
    issues.extend(_validate_runs(manifest))
    issues.extend(_validate_config(manifest))
    issues.extend(_validate_docs(manifest))
    issues.extend(_validate_examples(manifest))
    issues.extend(_validate_assets(manifest))
    return ValidationReport(
        ok=not any(issue.level == "error" for issue in issues),
        issues=tuple(issues),
    )


def import_entrypoint(entry: str, *, base_dir: Path | None = None) -> Any:
    module_name, sep, attr_path = entry.partition(":")
    if not sep or not module_name or not attr_path:
        raise ValueError(f"Entrypoint must have shape module:attribute: {entry}")
    root_module = module_name.split(".", 1)[0]
    with _import_path(base_dir, root_module=root_module):
        module = importlib.import_module(module_name)
        value: Any = module
        for part in attr_path.split("."):
            value = getattr(value, part)
        return value


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
        "channel": {"channels"},
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
        if schema.entry:
            issues.extend(_validate_import(schema.entry, manifest, manifest.ref("schema", name)))
    return issues


def _validate_tactics(manifest: PackageManifest) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for name, tactic in manifest.tactics.items():
        ref = manifest.ref("tactic", name)
        issues.extend(_validate_import(tactic.entry, manifest, ref))
        for schema_ref in (tactic.input, tactic.output):
            if schema_ref:
                issues.extend(_validate_schema_ref(schema_ref, manifest, ref))
    return issues


def _validate_services(manifest: PackageManifest) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for name, service in manifest.services.items():
        ref = manifest.ref("service", name)
        if service.entry:
            issues.extend(_validate_import(service.entry, manifest, ref))
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


def _validate_channels(manifest: PackageManifest) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for name, channel in manifest.channels.items():
        if channel.schema:
            issues.extend(
                _validate_schema_ref(
                    channel.schema,
                    manifest,
                    manifest.ref("channel", name),
                )
            )
    return issues


def _validate_runs(manifest: PackageManifest) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for name, run in manifest.runs.items():
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
    target = manifest.base_dir / path
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


def _validate_schema_ref(
    schema_ref: str,
    manifest: PackageManifest,
    resource: str,
) -> list[ValidationIssue]:
    if schema_ref in BUILTIN_SCHEMAS or schema_ref in manifest.schemas:
        return []
    if schema_ref.startswith("psi://"):
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
