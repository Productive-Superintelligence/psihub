import importlib.util
import json
from copy import deepcopy
from pathlib import Path
from types import MappingProxyType

import pytest
from pydantic import ValidationError
import psihub

from psihub import (
    LocalConfigResolver,
    LocalHub,
    PublishValidationError,
    import_entrypoint,
    init_package,
    load_manifest,
    manifest_path,
    record_from_manifest,
    render_agent_card,
    render_package_card,
    validate_package,
)
from psihub.models import (
    AssetResource,
    CardResource,
    ChannelResource,
    ConfigResource,
    DocResource,
    ExampleResource,
    HubResource,
    PackageInfo,
    PackageManifest,
    PackageRecord,
    RunResource,
    SchemaResource,
    ServiceResource,
    SnapshotResource,
    TacticResource,
    ValidationIssue,
    ValidationReport,
)
from psihub.refs import parse_psi_ref, validate_psi_ref
from psihub.cli import main


ROOT = Path(__file__).resolve().parents[1]


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_public_package_exports_resource_models():
    assert psihub.SchemaResource is SchemaResource
    assert psihub.TacticResource is TacticResource
    assert psihub.ServiceResource is ServiceResource
    assert psihub.ChannelResource is ChannelResource
    assert psihub.SnapshotResource is SnapshotResource
    assert psihub.RunResource is RunResource


def test_init_creates_manifest_and_readme(tmp_path):
    target = tmp_path / "new-package"
    manifest_path = init_package(target, org="demo", name="new-package", kind="tactic")

    assert manifest_path == target / "psi.toml"
    assert (target / "README.md").exists()
    manifest = load_manifest(target)
    assert manifest.package.identifier == "demo/new-package"
    assert manifest.package.kind == "tactic"
    assert manifest.card is not None
    assert "readme" in manifest.docs


def test_init_escapes_manifest_identity_strings(tmp_path):
    target = tmp_path / "quoted"
    init_package(target, org='demo"org', name='quote"pkg', kind="tactic")

    manifest = load_manifest(target)

    assert manifest.package.org == 'demo"org'
    assert manifest.package.name == 'quote"pkg'


def test_init_rejects_invalid_manifest_identity_before_write(tmp_path):
    target = tmp_path / "invalid"
    encoded_target = tmp_path / "bad%2Fpkg"

    with pytest.raises(ValueError, match="path segment"):
        init_package(target, org="demo", name="")
    with pytest.raises(ValueError, match="path segment"):
        init_package(target, org="..", name="pkg")
    with pytest.raises(ValueError, match="Input should be"):
        init_package(target, org="demo", name="pkg", kind="unknown")
    with pytest.raises(ValueError, match="path segment"):
        init_package(encoded_target, org="demo")
    assert not (target / "psi.toml").exists()
    assert not target.exists()
    assert not encoded_target.exists()


def test_public_path_helpers_reject_blank_or_non_path_values(tmp_path):
    for value in ("   ", " package ", 123):
        with pytest.raises(ValueError, match="manifest path"):
            manifest_path(value)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="package path"):
            init_package(value)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="config path"):
            LocalConfigResolver.from_file(value)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="config root"):
            LocalConfigResolver.from_text("[refs]\n", root=value)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="hub root"):
            LocalHub(value)  # type: ignore[arg-type]

    hub = LocalHub(tmp_path / "hub")
    with pytest.raises(ValueError, match="download destination"):
        hub.download("demo/missing", "   ")

    spaced_root = tmp_path / "package with space"
    created = init_package(spaced_root, org="demo", name="spaced")
    assert manifest_path(spaced_root) == created


def test_local_hub_rejects_download_destinations_inside_hub_root(tmp_path):
    package = make_lifecycle_package(tmp_path)
    hub_root = tmp_path / "hub"
    hub = LocalHub(hub_root)
    record = hub.publish(package)
    stored_manifest = record.root / "psi.toml"

    with pytest.raises(ValueError, match="outside the local hub root"):
        hub.download("demo/echo", hub_root / "packages" / "demo")

    assert stored_manifest.exists()
    assert hub.get("demo/echo").key == "demo/echo@0.1.0"


def test_local_hub_rejects_download_file_target_collisions(tmp_path):
    package = make_lifecycle_package(tmp_path)
    hub = LocalHub(tmp_path / "hub")
    hub.publish(package)
    destination = tmp_path / "downloaded"
    destination.mkdir()
    existing_target = destination / "echo"
    existing_target.write_text("not a directory", encoding="utf-8")

    with pytest.raises(ValueError, match="not a directory"):
        hub.download("demo/echo", destination)

    assert existing_target.read_text(encoding="utf-8") == "not a directory"


def test_local_config_resolver_from_text_rejects_non_string_text(tmp_path):
    for index, value in enumerate((None, 123, b"[refs]\n"), start=1):
        root = tmp_path / f"workspace-{index}"
        with pytest.raises(ValueError, match="config text"):
            LocalConfigResolver.from_text(value, root=root)  # type: ignore[arg-type]
        assert not root.exists()


def test_package_models_isolate_mutable_inputs():
    tactic_examples = ({"input": {"items": ["one"]}},)
    tactic_metadata = {"labels": ["tactic"]}
    tactic = TacticResource(
        entry="demo.tactics:Echo",
        examples=tactic_examples,
        metadata=tactic_metadata,
        custom={"items": ["extra"]},
    )
    config_schema = {"properties": {"model": {"type": "string"}}}
    defaults = {"service": {"metadata": {"port": 8000}}}
    config = ConfigResource(schema=config_schema, defaults=defaults)
    manifest = PackageManifest(
        package=PackageInfo(org="demo", name="pkg"),
        tactics={"echo": tactic},
        config=config,
    )
    hub_metadata = {"labels": ["hub"]}
    resource = HubResource(
        kind="tactic",
        name="echo",
        ref="psi://demo/pkg/tactics/echo",
        metadata=hub_metadata,
    )
    card_metadata = {"labels": ["card"]}
    record = PackageRecord(
        org="demo",
        name="pkg",
        version="0.1.0",
        kind="tactic",
        root=Path("."),
        manifest_path=Path("psi.toml"),
        resources=(resource,),
        validation=ValidationReport(ok=True),
        card=CardResource(metadata=card_metadata),
    )

    tactic_examples[0]["input"]["items"].append("changed")
    tactic_metadata["labels"].append("changed")
    tactic.custom["items"].append("mutated")
    config_schema["properties"]["model"]["type"] = "integer"
    defaults["service"]["metadata"]["port"] = 9000
    tactic.metadata["labels"].append("post-manifest")
    config.defaults["service"]["metadata"]["port"] = 7000
    config_schema_view = config.schema
    config_schema_view["properties"]["model"]["type"] = "number"
    assert manifest.config is not None
    manifest_schema_view = manifest.config.schema
    manifest_schema_view["properties"]["model"]["type"] = "boolean"
    hub_metadata["labels"].append("changed")
    resource.metadata["labels"].append("mutated")
    card_metadata["labels"].append("changed")

    assert tactic.examples == ({"input": {"items": ["one"]}},)
    assert tactic.metadata == {"labels": ["tactic", "post-manifest"]}
    assert tactic.custom == {"items": ["extra", "mutated"]}
    assert config.schema == {"properties": {"model": {"type": "string"}}}
    assert config.defaults == {"service": {"metadata": {"port": 7000}}}
    assert manifest.tactics["echo"].metadata == {"labels": ["tactic"]}
    assert manifest.tactics["echo"].custom == {"items": ["extra"]}
    assert manifest.config.schema == {"properties": {"model": {"type": "string"}}}
    assert manifest.config.defaults == {"service": {"metadata": {"port": 8000}}}
    assert resource.metadata == {"labels": ["hub", "mutated"]}
    assert record.resources[0].metadata == {"labels": ["hub"]}
    assert record.card is not None
    assert record.card.metadata == {"labels": ["card"]}
    tactic_resources = record.resources_by_kind("tactic")
    tactic_resources[0].metadata["labels"].append("from-query")
    assert record.resources[0].metadata == {"labels": ["hub"]}
    for kind in ("widget", "", None, 123):
        with pytest.raises(ValueError, match="resource kind"):
            record.resources_by_kind(kind)  # type: ignore[arg-type]


def test_package_models_accept_nested_read_only_mapping_inputs():
    example_inner = {"items": ["one"]}
    tactic_inner = {"labels": ["tactic"]}
    custom_inner = {"label": "extra"}
    schema_inner = {"type": "string"}
    default_inner = {"port": 8000}
    config_inner = {"labels": ["config"]}
    schema_meta_inner = {"labels": ["schema"]}
    service_inner = {"labels": ["service"]}
    channel_inner = {"labels": ["channel"]}
    snapshot_inner = {"labels": ["snapshot"]}
    run_inner = {"labels": ["run"]}
    doc_inner = {"labels": ["doc"]}
    example_meta_inner = {"labels": ["example"]}
    asset_inner = {"labels": ["asset"]}
    card_inner = {"labels": ["card"]}
    hub_inner = {"labels": ["hub"]}

    tactic = TacticResource(
        entry="demo.tactics:Echo",
        examples=({"input": MappingProxyType(example_inner)},),
        metadata={"nested": MappingProxyType(tactic_inner)},
        custom=MappingProxyType(custom_inner),
    )
    config = ConfigResource(
        schema={"properties": {"model": MappingProxyType(schema_inner)}},
        defaults={"service": MappingProxyType(default_inner)},
        metadata={"nested": MappingProxyType(config_inner)},
    )
    manifest = PackageManifest(
        package=PackageInfo(org="demo", name="pkg"),
        schemas={
            "event": SchemaResource(
                entry="demo.schemas:Event",
                metadata={"nested": MappingProxyType(schema_meta_inner)},
            )
        },
        tactics={"echo": tactic},
        services={
            "api": ServiceResource(
                entry="demo.service:app",
                metadata={"nested": MappingProxyType(service_inner)},
            )
        },
        channels={
            "events": ChannelResource(
                schema="demo.schemas:Event",
                metadata={"nested": MappingProxyType(channel_inner)},
            )
        },
        snapshots={
            "state": SnapshotResource(
                channel="events",
                metadata={"nested": MappingProxyType(snapshot_inner)},
            )
        },
        runs={"demo": RunResource(metadata={"nested": MappingProxyType(run_inner)})},
        config=config,
        docs={
            "readme": DocResource(
                path="README.md",
                metadata={"nested": MappingProxyType(doc_inner)},
            )
        },
        examples={
            "demo": ExampleResource(
                command="python examples/demo.py",
                metadata={"nested": MappingProxyType(example_meta_inner)},
            )
        },
        assets={
            "logo": AssetResource(
                path="assets/logo.svg",
                metadata={"nested": MappingProxyType(asset_inner)},
            )
        },
        card=CardResource(metadata={"nested": MappingProxyType(card_inner)}),
    )
    resource = HubResource(
        kind="tactic",
        name="echo",
        ref="psi://demo/pkg/tactics/echo",
        metadata={"nested": MappingProxyType(hub_inner)},
    )
    record = PackageRecord(
        org="demo",
        name="pkg",
        version="0.1.0",
        kind="tactic",
        root=Path("."),
        manifest_path=Path("psi.toml"),
        resources=(resource,),
        validation=ValidationReport(ok=True),
        card=manifest.card,
    )

    example_inner["items"].append("changed")
    tactic_inner["labels"].append("changed")
    custom_inner["label"] = "changed"
    schema_inner["type"] = "integer"
    default_inner["port"] = 9000
    config_inner["labels"].append("changed")
    schema_meta_inner["labels"].append("changed")
    service_inner["labels"].append("changed")
    channel_inner["labels"].append("changed")
    snapshot_inner["labels"].append("changed")
    run_inner["labels"].append("changed")
    doc_inner["labels"].append("changed")
    example_meta_inner["labels"].append("changed")
    asset_inner["labels"].append("changed")
    card_inner["labels"].append("changed")
    hub_inner["labels"].append("changed")

    assert tactic.examples == ({"input": {"items": ["one"]}},)
    assert tactic.metadata == {"nested": {"labels": ["tactic"]}}
    assert tactic.custom == {"label": "extra"}
    assert config.schema == {"properties": {"model": {"type": "string"}}}
    assert config.defaults == {"service": {"port": 8000}}
    assert config.metadata == {"nested": {"labels": ["config"]}}
    assert manifest.schemas["event"].metadata == {"nested": {"labels": ["schema"]}}
    assert manifest.tactics["echo"].metadata == {"nested": {"labels": ["tactic"]}}
    assert manifest.services["api"].metadata == {"nested": {"labels": ["service"]}}
    assert manifest.channels["events"].metadata == {"nested": {"labels": ["channel"]}}
    assert manifest.snapshots["state"].metadata == {"nested": {"labels": ["snapshot"]}}
    assert manifest.runs["demo"].metadata == {"nested": {"labels": ["run"]}}
    assert manifest.docs["readme"].metadata == {"nested": {"labels": ["doc"]}}
    assert manifest.examples["demo"].metadata == {"nested": {"labels": ["example"]}}
    assert manifest.assets["logo"].metadata == {"nested": {"labels": ["asset"]}}
    assert manifest.card is not None
    assert manifest.card.metadata == {"nested": {"labels": ["card"]}}
    assert record.resources[0].metadata == {"nested": {"labels": ["hub"]}}
    assert record.card is not None
    assert record.card.metadata == {"nested": {"labels": ["card"]}}


def test_record_from_manifest_preserves_canonical_resource_metadata(tmp_path):
    manifest = PackageManifest(
        package=PackageInfo(org="demo", name="canonical", version="0.1.0"),
        tactics={
            "echo": TacticResource(
                entry="demo.tactics:Echo",
                input="demo.schemas:EchoInput",
                output="demo.schemas:EchoOutput",
                runtime="pydantic-ai",
                examples=({"input": {"text": "hello"}},),
                metadata={
                    "runtime": "spoofed-runtime",
                    "input": "spoofed-input",
                    "output": "spoofed-output",
                    "examples": [{"input": {"text": "spoofed"}}],
                    "label": "user",
                },
            ),
        },
        services={
            "api": ServiceResource(
                entry="demo.service:app",
                tactic="echo",
                transport="fastapi",
                subscribes=("events",),
                publishes=("analysis",),
                metadata={
                    "tactic": "spoofed",
                    "transport": "zmq",
                    "subscribes": ["spoofed"],
                    "publishes": ["spoofed"],
                    "port": 8800,
                },
            ),
        },
        channels={
            "events": ChannelResource(
                schema="demo.schemas:Event",
                form="log",
                metadata={"schema": "spoofed", "form": "queue"},
            ),
        },
        snapshots={
            "latest": SnapshotResource(
                schema="demo.schemas:Analysis",
                channel="analysis",
                metadata={"schema": "spoofed", "channel": "spoofed"},
            ),
        },
        runs={
            "demo": RunResource(
                services=("api",),
                tactics=("echo",),
                channels=("events",),
                snapshots=("latest",),
                metadata={
                    "services": ["spoofed"],
                    "tactics": ["spoofed"],
                    "channels": ["spoofed"],
                    "snapshots": ["spoofed"],
                },
            ),
        },
        config=ConfigResource(
            schema={"properties": {"model": {"type": "string"}}},
            defaults={"sample_rate": 2},
            metadata={
                "schema": {"properties": {"model": {"type": "integer"}}},
                "defaults": {"sample_rate": 99},
            },
        ),
        docs={
            "guide": DocResource(
                path="docs/guide.md",
                title="Guide",
                metadata={"path": "spoofed.md", "title": "Spoofed"},
            ),
        },
        examples={
            "quickstart": ExampleResource(
                path="examples/run.py",
                command="python examples/run.py",
                metadata={
                    "path": "spoofed.py",
                    "command": "python spoofed.py",
                },
            ),
        },
        assets={
            "logo": AssetResource(
                path="assets/logo.svg",
                media_type="image/svg+xml",
                metadata={
                    "path": "spoofed.svg",
                    "media_type": "text/plain",
                },
            ),
        },
        base_dir=tmp_path,
    )

    record = record_from_manifest(manifest, validation=ValidationReport(ok=True))
    resources = {(resource.kind, resource.name): resource for resource in record.resources}

    tactic = resources[("tactic", "echo")]
    assert tactic.metadata["runtime"] == "pydantic-ai"
    assert tactic.metadata["input"] == "demo.schemas:EchoInput"
    assert tactic.metadata["output"] == "demo.schemas:EchoOutput"
    assert tactic.metadata["examples"] == [{"input": {"text": "hello"}}]
    assert tactic.metadata["label"] == "user"

    service = resources[("service", "api")]
    assert service.metadata["tactic"] == "echo"
    assert service.metadata["transport"] == "fastapi"
    assert service.metadata["subscribes"] == ["events"]
    assert service.metadata["publishes"] == ["analysis"]
    assert service.metadata["port"] == 8800

    assert resources[("channel", "events")].metadata["schema"] == "demo.schemas:Event"
    assert resources[("channel", "events")].metadata["form"] == "log"
    assert resources[("snapshot", "latest")].metadata["schema"] == "demo.schemas:Analysis"
    assert resources[("snapshot", "latest")].metadata["channel"] == "analysis"
    assert resources[("run", "demo")].metadata["services"] == ["api"]
    assert resources[("run", "demo")].metadata["tactics"] == ["echo"]
    assert resources[("run", "demo")].metadata["channels"] == ["events"]
    assert resources[("run", "demo")].metadata["snapshots"] == ["latest"]
    assert resources[("config", "default")].metadata["schema"] == {
        "properties": {"model": {"type": "string"}}
    }
    assert resources[("config", "default")].metadata["defaults"] == {"sample_rate": 2}
    assert resources[("doc", "guide")].metadata["path"] == "docs/guide.md"
    assert resources[("doc", "guide")].metadata["title"] == "Guide"
    assert resources[("example", "quickstart")].metadata["path"] == "examples/run.py"
    assert (
        resources[("example", "quickstart")].metadata["command"]
        == "python examples/run.py"
    )
    assert resources[("asset", "logo")].metadata["path"] == "assets/logo.svg"
    assert resources[("asset", "logo")].metadata["media_type"] == "image/svg+xml"


@pytest.mark.parametrize(
    "factory",
    [
        lambda: PackageInfo(org="demo", name=b"pkg"),
        lambda: PackageInfo(org="demo", name="pkg", authors=(b"author",)),
        lambda: SchemaResource(entry=b"demo.schemas:Event"),
        lambda: TacticResource(entry=b"demo.tactics:Echo"),
        lambda: TacticResource(entry="demo.tactics:Echo", input=b"demo.schemas:In"),
        lambda: ServiceResource(entry=b"demo.service:app"),
        lambda: ServiceResource(subscribes=(b"events",)),
        lambda: ChannelResource(schema=b"demo.schemas:Event"),
        lambda: SnapshotResource(channel=b"state"),
        lambda: RunResource(services=(b"api",)),
        lambda: ConfigResource(description=b"config"),
        lambda: DocResource(path=b"README.md"),
        lambda: ExampleResource(command=b"python examples/demo.py"),
        lambda: AssetResource(path=b"assets/logo.svg"),
        lambda: AssetResource(path="assets/logo.svg", media_type=b"image/svg+xml"),
        lambda: CardResource(tags=(b"demo",)),
        lambda: HubResource(kind="tactic", name="echo", ref=b"psi://demo/pkg/tactics/echo"),
        lambda: ValidationIssue(level="error", code=b"bad", message="bad"),
        lambda: PackageRecord(
            org="demo",
            name=b"pkg",
            version="0.1.0",
            kind="mixed",
            root=Path("."),
            manifest_path=Path("psi.toml"),
            validation=ValidationReport(ok=True),
        ),
        lambda: PackageManifest(
            package=PackageInfo(org="demo", name="pkg"),
            tactics={b"echo": TacticResource(entry="demo.tactics:Echo")},
        ),
    ],
)
def test_package_models_reject_bytes_for_declared_string_fields(factory):
    with pytest.raises(ValidationError):
        factory()


@pytest.mark.parametrize(
    "factory",
    [
        lambda: PackageInfo(org="demo", name="   "),
        lambda: PackageInfo(org="   ", name="pkg"),
        lambda: PackageInfo(org="demo", name="pkg", version="   "),
        lambda: PackageInfo(org="demo org", name="pkg"),
        lambda: PackageInfo(org="demo%2Forg", name="pkg"),
        lambda: PackageInfo(org="demo", name="bad pkg"),
        lambda: PackageInfo(org="demo", name="bad%2Fpkg"),
        lambda: PackageInfo(org="demo", name="pkg", version="0.1.0 beta"),
        lambda: PackageInfo(org="demo", name="pkg", version="0.1.0%20beta"),
        lambda: HubResource(
            kind="tactic",
            name="bad tactic",
            ref="psi://demo/pkg/tactics/bad-tactic",
        ),
        lambda: HubResource(
            kind="tactic",
            name="bad%2Ftactic",
            ref="psi://demo/pkg/tactics/bad%2Ftactic",
        ),
        lambda: PackageRecord(
            org="demo",
            name="   ",
            version="0.1.0",
            kind="mixed",
            root=Path("."),
            manifest_path=Path("psi.toml"),
            validation=ValidationReport(ok=True),
        ),
        lambda: PackageRecord(
            org="demo",
            name="bad pkg",
            version="0.1.0",
            kind="mixed",
            root=Path("."),
            manifest_path=Path("psi.toml"),
            validation=ValidationReport(ok=True),
        ),
        lambda: PackageRecord(
            org="demo",
            name="bad%2Fpkg",
            version="0.1.0",
            kind="mixed",
            root=Path("."),
            manifest_path=Path("psi.toml"),
            validation=ValidationReport(ok=True),
        ),
        lambda: PackageManifest(package=PackageInfo(org="demo", name="pkg")).ref(
            "tactic",
            "   ",
        ),
        lambda: PackageManifest(package=PackageInfo(org="demo", name="pkg")).ref(
            "tactic",
            "bad tactic",
        ),
        lambda: PackageManifest(package=PackageInfo(org="demo", name="pkg")).ref(
            "tactic",
            "bad%2Ftactic",
        ),
    ],
)
def test_package_identity_models_reject_malformed_segments(factory):
    with pytest.raises(ValueError, match="path segment"):
        factory()


@pytest.mark.parametrize(
    "value",
    (
        "",
        "   ",
        ".",
        "..",
        "bad token",
        "bad/token",
        "bad:token",
        "bad\\token",
        "bad%2Ftoken",
    ),
)
def test_package_resource_metadata_rejects_malformed_tokens(value):
    with pytest.raises(ValidationError):
        TacticResource(entry="demo.tactics:Echo", runtime=value)
    with pytest.raises(ValidationError):
        ServiceResource(entry="demo.service:app", transport=value)
    with pytest.raises(ValidationError):
        ChannelResource(form=value)


def test_package_resource_metadata_allows_common_token_separators():
    tactic = TacticResource(entry="demo.tactics:Echo", runtime="pydantic-ai")
    service = ServiceResource(entry="demo.service:app", transport="fastapi")
    channel = ChannelResource(form="time-series")

    assert tactic.runtime == "pydantic-ai"
    assert service.transport == "fastapi"
    assert channel.form == "time-series"


@pytest.mark.parametrize(
    "value",
    ("", "   ", ".", "..", "bad code", "bad/code", "bad:code", "bad\\code"),
)
def test_validation_issue_rejects_malformed_codes(value):
    with pytest.raises(ValidationError):
        ValidationIssue(level="error", code=value, message="broken")


def test_validation_issue_allows_common_code_separators():
    issue = ValidationIssue(
        level="error",
        code="schema_ref_kind_mismatch",
        message="broken",
    )

    assert issue.code == "schema_ref_kind_mismatch"


def test_package_manifest_ref_rejects_invalid_resource_kind():
    manifest = PackageManifest(package=PackageInfo(org="demo", name="pkg"))

    for kind in ("widget", "", None, 123):
        with pytest.raises(ValueError, match="resource kind"):
            manifest.ref(kind, "local")  # type: ignore[arg-type]


def test_hub_resource_validates_ref_identity():
    resource = HubResource(
        kind="tactic",
        name="echo",
        ref="psi://demo/pkg/tactics/echo",
    )

    assert resource.ref == "psi://demo/pkg/tactics/echo"

    for kwargs in (
        {
            "kind": "tactic",
            "name": "echo",
            "ref": "not-a-ref",
        },
        {
            "kind": "tactic",
            "name": "echo",
            "ref": "psi://demo/pkg/channels/echo",
        },
        {
            "kind": "tactic",
            "name": "echo",
            "ref": "psi://demo/pkg/tactics/other",
        },
    ):
        with pytest.raises(ValidationError):
            HubResource(**kwargs)


def test_local_package_lifecycle_example_runs(tmp_path):
    module = load_module(
        ROOT / "examples" / "local_package_lifecycle" / "workflow.py",
        "local_package_lifecycle_workflow",
    )

    result = module.run_workflow(tmp_path)

    assert result["manifest_path"] == tmp_path / "demo-package" / "psi.toml"
    assert result["report"].ok
    assert result["record"].key == "demo/echo@0.1.0"
    assert [record.key for record in result["listed"]] == ["demo/echo@0.1.0"]
    assert (result["downloaded"] / "psi.toml").exists()
    assert "# demo/echo" in result["card"]
    assert "Agent Card: demo/echo" in result["agent_card"]
    assert isinstance(result["config"], str)

    padded_root = tmp_path / "padded-workflow"
    for bad_root in ("", "   ", 123, f" {padded_root} "):
        with pytest.raises(ValueError, match="workflow root"):
            module.run_workflow(bad_root)

    assert not padded_root.exists()


def test_validate_lifecycle_package(tmp_path):
    package = make_lifecycle_package(tmp_path)

    report = validate_package(package)

    assert report.ok
    assert report.issues == ()


def test_validate_warns_on_missing_card_and_readme_metadata(tmp_path):
    package = make_lifecycle_package(tmp_path)
    text = (package / "psi.toml").read_text(encoding="utf-8")
    text = text.replace(
        """
[card]
summary = "Echo tactic package."
tags = ["demo", "tactic"]
suggested_commands = ["python -m demo.app"]

[docs.readme]
path = "README.md"
title = "README"
description = "Source-facing package guide."

""".lstrip(),
        "",
    )
    (package / "psi.toml").write_text(text, encoding="utf-8")

    report = validate_package(package)

    assert report.ok
    assert any(issue.code == "card_metadata_missing" for issue in report.issues)
    assert any(issue.code == "readme_doc_missing" for issue in report.issues)


def test_validate_catches_missing_service_tactic(tmp_path):
    package = make_lifecycle_package(tmp_path)
    text = (package / "psi.toml").read_text(encoding="utf-8")
    (package / "psi.toml").write_text(
        text.replace('tactic = "echo"', 'tactic = "missing"'),
        encoding="utf-8",
    )

    report = validate_package(package)

    assert not report.ok
    assert any(issue.code == "service_tactic_missing" for issue in report.issues)


def test_validate_catches_duplicate_resource_table_names(tmp_path):
    package = make_lifecycle_package(tmp_path)
    with (package / "psi.toml").open("a", encoding="utf-8") as handle:
        handle.write('\n[tactics.echo]\nentry = "demo.tactics:EchoTactic"\n')

    report = validate_package(package)

    assert not report.ok
    assert any(issue.code == "manifest_duplicate_name" for issue in report.issues)
    assert any("twice" in issue.message for issue in report.issues)


def test_validate_catches_unbound_service(tmp_path):
    package = make_lifecycle_package(tmp_path)
    text = (package / "psi.toml").read_text(encoding="utf-8")
    (package / "psi.toml").write_text(
        text.replace('entry = "demo.app:create_app"\ntactic = "echo"\n', ""),
        encoding="utf-8",
    )

    report = validate_package(package)

    assert not report.ok
    assert any(issue.code == "service_unbound" for issue in report.issues)


def test_validate_catches_missing_service_channel_refs(tmp_path):
    replacements = [
        ("subscribe", 'subscribes = ["events"]', 'subscribes = ["missing"]'),
        ("publish", 'publishes = ["analysis"]', 'publishes = ["missing"]'),
    ]
    for name, old, new in replacements:
        package = make_combined_package(tmp_path / name)
        manifest = package / "psi.toml"
        manifest.write_text(
            manifest.read_text(encoding="utf-8").replace(old, new, 1),
            encoding="utf-8",
        )

        report = validate_package(package)

        assert not report.ok
        assert any(issue.code == "service_channel_missing" for issue in report.issues)


def test_validate_checks_all_run_resource_refs(tmp_path):
    cases = [
        (
            "service",
            make_lifecycle_package,
            'services = ["api"]',
            'services = ["missing"]',
            "run_service_missing",
        ),
        (
            "tactic",
            make_lifecycle_package,
            'services = ["api"]',
            'services = ["api"]\ntactics = ["missing"]',
            "run_tactic_missing",
        ),
        (
            "channel",
            make_combined_package,
            'channels = ["events", "analysis"]',
            'channels = ["missing"]',
            "run_channel_missing",
        ),
        (
            "snapshot",
            make_combined_package,
            'snapshots = ["latest_analysis"]',
            'snapshots = ["missing"]',
            "run_snapshot_missing",
        ),
    ]
    for name, factory, old, new, code in cases:
        package = factory(tmp_path / name)
        manifest = package / "psi.toml"
        manifest.write_text(
            manifest.read_text(encoding="utf-8").replace(old, new, 1),
            encoding="utf-8",
        )

        report = validate_package(package)

        assert not report.ok
        assert any(issue.code == code for issue in report.issues)


def test_validate_checks_schema_psi_refs(tmp_path):
    package = make_lifecycle_package(tmp_path)
    original = (package / "psi.toml").read_text(encoding="utf-8")

    (package / "psi.toml").write_text(
        original.replace('input = "echo_input"', 'input = "psi://demo/echo"'),
        encoding="utf-8",
    )
    invalid_report = validate_package(package)

    assert not invalid_report.ok
    assert any(issue.code == "schema_ref_invalid" for issue in invalid_report.issues)

    (package / "psi.toml").write_text(
        original.replace(
            'input = "echo_input"',
            'input = "psi://demo/echo/channels/events"',
        ),
        encoding="utf-8",
    )
    wrong_kind_report = validate_package(package)

    assert not wrong_kind_report.ok
    assert any(
        issue.code == "schema_ref_kind_mismatch"
        for issue in wrong_kind_report.issues
    )

    (package / "psi.toml").write_text(
        original.replace(
            'input = "echo_input"',
            'input = "psi://demo/echo/schemas/missing"',
        ),
        encoding="utf-8",
    )
    local_missing_report = validate_package(package)

    assert not local_missing_report.ok
    assert any(issue.code == "schema_ref_missing" for issue in local_missing_report.issues)

    (package / "psi.toml").write_text(
        original.replace(
            'input = "echo_input"',
            'input = "psi://other/package/schemas/payload?env=dev"',
        ),
        encoding="utf-8",
    )
    external_invalid_report = validate_package(package)

    assert not external_invalid_report.ok
    assert any(
        issue.code == "schema_ref_invalid"
        for issue in external_invalid_report.issues
    )

    (package / "psi.toml").write_text(
        original.replace(
            'input = "echo_input"',
            'input = "psi://other/package/schemas/payload"',
        ),
        encoding="utf-8",
    )
    external_report = validate_package(package)

    assert external_report.ok


def test_validate_warns_on_empty_tactic_examples(tmp_path):
    package = make_lifecycle_package(tmp_path)
    text = (package / "psi.toml").read_text(encoding="utf-8")
    (package / "psi.toml").write_text(
        text.replace(
            'input = { text = "hello" }\noutput = { text = "HELLO" }\n',
            "",
        ),
        encoding="utf-8",
    )

    report = validate_package(package)

    assert report.ok
    assert any(issue.code == "tactic_example_empty" for issue in report.issues)


def test_validate_checks_endpoint_metadata(tmp_path):
    package = make_combined_package(tmp_path)
    original = (package / "psi.toml").read_text(encoding="utf-8")

    (package / "psi.toml").write_text(
        original.replace('method = "POST"', 'method = "TRACE"'),
        encoding="utf-8",
    )
    method_report = validate_package(package)

    assert not method_report.ok
    assert any(
        issue.code == "endpoint_method_invalid" for issue in method_report.issues
    )

    (package / "psi.toml").write_text(
        original.replace('path = "/analyze"', 'path = "analyze"'),
        encoding="utf-8",
    )
    path_report = validate_package(package)

    assert not path_report.ok
    assert any(issue.code == "endpoint_path_invalid" for issue in path_report.issues)

    (package / "psi.toml").write_text(
        original.replace('path = "/analyze"', 'path = "/bad path"'),
        encoding="utf-8",
    )
    whitespace_path_report = validate_package(package)

    assert not whitespace_path_report.ok
    assert any(
        issue.code == "endpoint_path_invalid"
        for issue in whitespace_path_report.issues
    )

    (package / "psi.toml").write_text(
        original.replace('path = "/analyze"', 'path = "/bad%2Fpath"'),
        encoding="utf-8",
    )
    percent_path_report = validate_package(package)

    assert not percent_path_report.ok
    assert any(
        issue.code == "endpoint_path_invalid"
        for issue in percent_path_report.issues
    )

    (package / "psi.toml").write_text(
        original.replace('path = "/analyze"', 'path = "//example.com/analyze"'),
        encoding="utf-8",
    )
    network_path_report = validate_package(package)

    assert not network_path_report.ok
    assert any(
        issue.code == "endpoint_path_invalid"
        for issue in network_path_report.issues
    )

    (package / "psi.toml").write_text(
        original.replace('name = "analyze"', 'name = "bad name"'),
        encoding="utf-8",
    )
    name_report = validate_package(package)

    assert not name_report.ok
    assert any(issue.code == "endpoint_name_invalid" for issue in name_report.issues)

    (package / "psi.toml").write_text(
        original.replace('name = "analyze"', 'name = "bad%2Fname"'),
        encoding="utf-8",
    )
    percent_name_report = validate_package(package)

    assert not percent_name_report.ok
    assert any(
        issue.code == "endpoint_name_invalid" for issue in percent_name_report.issues
    )

    (package / "psi.toml").write_text(
        original.replace('mode = "run"', 'mode = "batch"'),
        encoding="utf-8",
    )
    mode_report = validate_package(package)

    assert not mode_report.ok
    assert any(issue.code == "endpoint_mode_invalid" for issue in mode_report.issues)

    (package / "psi.toml").write_text(
        original.replace('scope = "channel"', 'scope = "wrong"'),
        encoding="utf-8",
    )
    scope_report = validate_package(package)

    assert not scope_report.ok
    assert any(
        issue.code == "endpoint_scope_invalid" for issue in scope_report.issues
    )

    (package / "psi.toml").write_text(
        original.replace('mode = "run"', 'mode = "run"\ntags = ["bad%2Ftag"]'),
        encoding="utf-8",
    )
    percent_tag_report = validate_package(package)

    assert not percent_tag_report.ok
    assert any(
        issue.code == "endpoint_tags_invalid" for issue in percent_tag_report.issues
    )


def test_validate_checks_service_port_metadata(tmp_path):
    cases = [
        (
            "direct-extra",
            "[services.api]\n",
            '[services.api]\nport = "bad"\n',
        ),
        (
            "metadata",
            '[services.api.metadata]\npolicy_url = "http://policy"',
            '[services.api.metadata]\nport = 70000\npolicy_url = "http://policy"',
        ),
    ]

    for name, old, new in cases:
        package = make_lifecycle_package(tmp_path / name)
        manifest = package / "psi.toml"
        manifest.write_text(
            manifest.read_text(encoding="utf-8").replace(old, new),
            encoding="utf-8",
        )

        report = validate_package(package)

        assert not report.ok
        assert any(issue.code == "service_port_invalid" for issue in report.issues)


def test_validate_checks_snapshot_refs(tmp_path):
    package = make_combined_package(tmp_path)
    original = (package / "psi.toml").read_text(encoding="utf-8")

    (package / "psi.toml").write_text(
        original.replace('channel = "analysis"', 'channel = "missing"'),
        encoding="utf-8",
    )
    missing_channel_report = validate_package(package)

    assert not missing_channel_report.ok
    assert any(
        issue.code == "snapshot_channel_missing"
        for issue in missing_channel_report.issues
    )

    (package / "psi.toml").write_text(
        original.replace('snapshots = ["latest_analysis"]', 'snapshots = ["missing"]'),
        encoding="utf-8",
    )
    missing_snapshot_report = validate_package(package)

    assert not missing_snapshot_report.ok
    assert any(
        issue.code == "run_snapshot_missing"
        for issue in missing_snapshot_report.issues
    )


def test_local_publish_rejects_invalid_packages_by_default(tmp_path):
    package = make_lifecycle_package(tmp_path)
    text = (package / "psi.toml").read_text(encoding="utf-8")
    (package / "psi.toml").write_text(
        text.replace('tactic = "echo"', 'tactic = "missing"'),
        encoding="utf-8",
    )
    hub = LocalHub(tmp_path / "hub")

    with pytest.raises(PublishValidationError) as exc_info:
        hub.publish(package)

    assert any(
        issue.code == "service_tactic_missing" for issue in exc_info.value.report.issues
    )
    assert hub.list() == ()
    record = hub.publish(package, validate=False)
    assert record.key == "demo/echo@0.1.0"


def test_validate_checks_package_kind_primary_metadata(tmp_path):
    package = make_lifecycle_package(tmp_path)
    text = (package / "psi.toml").read_text(encoding="utf-8")
    (package / "psi.toml").write_text(
        text.replace('primary = "tactics.echo"\n', ""),
        encoding="utf-8",
    )

    missing_report = validate_package(package)

    assert missing_report.ok
    assert any(issue.code == "primary_missing_for_kind" for issue in missing_report.issues)

    (package / "psi.toml").write_text(
        text.replace('primary = "tactics.echo"', 'primary = "channels.events"'),
        encoding="utf-8",
    )

    mismatch_report = validate_package(package)

    assert not mismatch_report.ok
    assert any(issue.code == "primary_kind_mismatch" for issue in mismatch_report.issues)


def test_validate_rejects_path_control_package_identity_segments(tmp_path):
    replacements = [
        ("org", 'org = "demo"', 'org = ".."'),
        ("name", 'name = "echo"', 'name = "."'),
        ("version", 'version = "0.1.0"', 'version = ".."'),
    ]
    for field, original, replacement in replacements:
        package = make_lifecycle_package(tmp_path / field)
        manifest_path = package / "psi.toml"
        manifest_path.write_text(
            manifest_path.read_text(encoding="utf-8").replace(original, replacement),
            encoding="utf-8",
        )

        report = validate_package(package)

        assert not report.ok
        assert any(issue.code == "manifest_load_failed" for issue in report.issues)


def test_validate_rejects_whitespace_package_identity_segments(tmp_path):
    replacements = [
        ("org", 'org = "demo"', 'org = "demo org"'),
        ("name", 'name = "echo"', 'name = "bad echo"'),
        ("version", 'version = "0.1.0"', 'version = "0.1.0 beta"'),
    ]
    for field, original, replacement in replacements:
        package = make_lifecycle_package(tmp_path / f"whitespace-{field}")
        manifest_path = package / "psi.toml"
        manifest_path.write_text(
            manifest_path.read_text(encoding="utf-8").replace(original, replacement),
            encoding="utf-8",
        )

        report = validate_package(package)

        assert not report.ok
        assert any(issue.code == "manifest_load_failed" for issue in report.issues)


def test_validate_rejects_path_control_resource_names(tmp_path):
    package = tmp_path / "invalid-resource"
    package.mkdir()
    (package / "README.md").write_text("# Invalid resource\n", encoding="utf-8")
    (package / "demo.py").write_text(
        "class Echo:\n    pass\n",
        encoding="utf-8",
    )
    (package / "psi.toml").write_text(
        """
[package]
psi_version = "0.1"
org = "demo"
name = "invalid-resource"
version = "0.1.0"
kind = "library"

[tactics."bad/name"]
entry = "demo:Echo"
""".lstrip(),
        encoding="utf-8",
    )

    report = validate_package(package)

    assert not report.ok
    assert any(issue.code == "tactic_name_invalid" for issue in report.issues)


def test_validate_rejects_whitespace_resource_names(tmp_path):
    package = tmp_path / "whitespace-resource"
    package.mkdir()
    (package / "README.md").write_text("# Invalid resource\n", encoding="utf-8")
    (package / "demo.py").write_text(
        "class Echo:\n    pass\n",
        encoding="utf-8",
    )
    (package / "psi.toml").write_text(
        """
[package]
psi_version = "0.1"
org = "demo"
name = "invalid-resource"
version = "0.1.0"
kind = "library"

[tactics."bad tactic"]
entry = "demo:Echo"
""".lstrip(),
        encoding="utf-8",
    )

    report = validate_package(package)

    assert not report.ok
    assert any(issue.code == "tactic_name_invalid" for issue in report.issues)


def test_validate_catches_missing_declared_doc(tmp_path):
    package = make_rich_metadata_package(tmp_path)
    (package / "docs" / "guide.md").unlink()

    report = validate_package(package)

    assert not report.ok
    assert any(issue.code == "doc_path_missing" for issue in report.issues)


def test_validate_rejects_declared_files_outside_package(tmp_path):
    replacements = [
        ("docs/guide.md", "doc_path_outside_package"),
        ("examples/run.py", "example_path_outside_package"),
        ("assets/logo.txt", "asset_path_outside_package"),
    ]
    for path, code in replacements:
        case_root = tmp_path / code
        case_root.mkdir()
        outside = case_root / "outside.txt"
        outside.write_text("outside\n", encoding="utf-8")
        package = make_rich_metadata_package(case_root)
        text = (package / "psi.toml").read_text(encoding="utf-8")
        (package / "psi.toml").write_text(
            text.replace(f'path = "{path}"', 'path = "../outside.txt"'),
            encoding="utf-8",
        )

        report = validate_package(package)

        assert not report.ok
        assert any(issue.code == code for issue in report.issues)


def test_validate_rejects_absolute_declared_file_paths(tmp_path):
    replacements = [
        ("docs/guide.md", "doc_path_absolute_path"),
        ("examples/run.py", "example_path_absolute_path"),
        ("assets/logo.txt", "asset_path_absolute_path"),
    ]
    for path, code in replacements:
        package = make_rich_metadata_package(tmp_path / code)
        absolute_path = package / path
        text = (package / "psi.toml").read_text(encoding="utf-8")
        (package / "psi.toml").write_text(
            text.replace(f'path = "{path}"', f'path = "{absolute_path}"'),
            encoding="utf-8",
        )

        report = validate_package(package)

        assert not report.ok
        assert any(issue.code == code for issue in report.issues)

        windows_path = f"C:/tmp/{Path(path).name}"
        text = (package / "psi.toml").read_text(encoding="utf-8")
        (package / "psi.toml").write_text(
            text.replace(f'path = "{absolute_path}"', f'path = "{windows_path}"'),
            encoding="utf-8",
        )

        windows_report = validate_package(package)

        assert not windows_report.ok
        assert any(issue.code == code for issue in windows_report.issues)


@pytest.mark.parametrize(
    "bad_path",
    [
        "",
        "   ",
        " docs/guide.md ",
        "docs/bad guide.md",
        "docs/bad%2Fguide.md",
        "docs\\guide.md",
        "docs:guide.md",
        "//host/guide.md",
        "http://example.com/guide.md",
    ],
)
def test_validate_rejects_malformed_declared_file_paths(tmp_path, bad_path):
    case_name = f"case-{len(bad_path)}-{sum(ord(ch) for ch in bad_path)}"
    replacements = [
        ("docs/guide.md", "doc_path_invalid"),
        ("examples/run.py", "example_path_invalid"),
        ("assets/logo.txt", "asset_path_invalid"),
    ]
    for path, code in replacements:
        package = make_rich_metadata_package(tmp_path / code / case_name)
        text = (package / "psi.toml").read_text(encoding="utf-8")
        (package / "psi.toml").write_text(
            text.replace(f'path = "{path}"', f"path = {json.dumps(bad_path)}"),
            encoding="utf-8",
        )

        report = validate_package(package)

        assert not report.ok
        assert any(issue.code == code for issue in report.issues)


def test_validate_isolates_entrypoint_imports_between_package_roots(tmp_path):
    first = make_entrypoint_cache_package(
        tmp_path / "first",
        module_body="""
def create_app():
    return {"service": "first"}
""".lstrip(),
    )
    second = make_entrypoint_cache_package(
        tmp_path / "second",
        module_body="""
def other_app():
    return {"service": "second"}
""".lstrip(),
    )

    assert validate_package(first).ok

    report = validate_package(second)

    assert not report.ok
    assert any(issue.code == "entrypoint_import_failed" for issue in report.issues)


@pytest.mark.parametrize(
    "entrypoint",
    [
        None,
        123,
        "",
        "   ",
        "sharedpkg.app",
        ":create_app",
        "sharedpkg.app:",
        "sharedpkg..app:create_app",
        "sharedpkg.app:create app",
        "sharedpkg%2Fapp:create_app",
        "sharedpkg.app:create%2Fapp",
        " sharedpkg.app:create_app ",
    ],
)
def test_import_entrypoint_rejects_malformed_values(entrypoint):
    with pytest.raises(ValueError, match="Entrypoint"):
        import_entrypoint(entrypoint)  # type: ignore[arg-type]


def test_validate_reports_malformed_entrypoints_as_import_issues(tmp_path):
    package = make_entrypoint_cache_package(
        tmp_path / "malformed-entrypoint",
        module_body="""
def create_app():
    return {"service": "demo"}
""".lstrip(),
    )
    text = (package / "psi.toml").read_text(encoding="utf-8")
    (package / "psi.toml").write_text(
        text.replace(
            'entry = "sharedpkg.app:create_app"',
            'entry = " sharedpkg.app:create_app "',
        ),
        encoding="utf-8",
    )

    report = validate_package(package)

    assert not report.ok
    assert any(
        issue.code == "entrypoint_import_failed"
        and "Entrypoint must have shape" in issue.message
        for issue in report.issues
    )


def test_local_publish_indexes_rich_package_metadata(tmp_path):
    package = make_rich_metadata_package(tmp_path)
    hub = LocalHub(tmp_path / "hub")

    record = hub.publish(package)
    card = hub.card("demo/rich")
    agent_card = hub.agent_card("demo/rich")
    config = hub.config_template("demo/rich")

    assert record.validation.ok
    assert record.card is not None
    assert record.card.summary == "Rich package card."
    assert {resource.kind for resource in record.resources} >= {
        "config",
        "doc",
        "example",
        "asset",
    }
    assert "Safety: Offline demo only." in card
    assert "Latency: Local call under 10 ms." in card
    assert "`python examples/run.py`" in card
    assert "psi://demo/rich/docs/guide" in card
    assert "psi://demo/rich/examples/quickstart" in card
    assert "psi://demo/rich/assets/logo" in card
    assert "Safety: Offline demo only." in agent_card
    assert "example `quickstart`: `psi://demo/rich/examples/quickstart`" in agent_card
    assert "[settings]" in config
    assert "sample_rate = 2" in config
    resolver = LocalConfigResolver.from_text(config, root=tmp_path / "workspace")
    assert resolver.settings() == {"sample_rate": 2}
    assert resolver.setting("sample_rate") == 2
    assert resolver.setting("missing", "fallback") == "fallback"


def test_local_publish_download_card_and_config(tmp_path):
    package = make_lifecycle_package(tmp_path)
    hub = LocalHub(tmp_path / "hub")

    record = hub.publish(package)
    downloaded = hub.download("demo/echo", tmp_path / "downloaded")
    card = hub.card("demo/echo")
    agent_card = hub.agent_card("demo/echo")
    config = hub.config_template("demo/echo")

    assert record.key == "demo/echo@0.1.0"
    assert record.validation.ok
    assert (downloaded / "psi.toml").exists()
    echo = next(
        resource
        for resource in record.resources
        if resource.kind == "tactic" and resource.name == "echo"
    )
    assert echo.metadata["examples"] == [
        {
            "description": "Uppercase text.",
            "input": {"text": "hello"},
            "output": {"text": "HELLO"},
        }
    ]
    assert "psi://demo/echo/tactics/echo" in card
    assert "psi://demo/echo/services/api" in card
    example_line = (
        'Example: Uppercase text. `input={"text":"hello"}` -> '
        '`output={"text":"HELLO"}`'
    )
    assert example_line in card
    assert "Agent Card: demo/echo" in agent_card
    assert "PsiHub describes packages, refs, config, and metadata" in agent_card
    assert "tactic `echo`: `psi://demo/echo/tactics/echo`" in agent_card
    assert example_line in agent_card
    assert 'policy_url="http://policy"' in card
    assert '[refs."psi://demo/echo/tactics/echo"]' in config
    assert '[refs."psi://demo/echo/services/api"]' in config
    assert '[refs."psi://demo/echo/services/api".metadata]' in config
    assert "[services.api]" in config
    assert "port = 8000" in config
    assert 'policy_url = "http://policy"' in config
    resolver = LocalConfigResolver.from_text(config, root=tmp_path / "workspace")
    assert (
        resolver.resolve("psi://demo/echo/services/api").metadata["policy_url"]
        == "http://policy"
    )
    assert resolver.service("api") == {"port": 8000}


def test_config_template_escapes_quoted_ref_table_keys(tmp_path):
    root = tmp_path / "quoted-package"
    root.mkdir()
    manifest_path = root / "psi.toml"
    manifest_path.write_text("", encoding="utf-8")
    ref = 'psi://demo"org/quote"pkg/services/api'
    record = PackageRecord(
        org='demo"org',
        name='quote"pkg',
        version="0.1.0",
        kind="app",
        root=root,
        manifest_path=manifest_path,
        resources=(
            HubResource(
                kind="service",
                name="api",
                ref=ref,
                metadata={"policy_url": "http://policy"},
            ),
        ),
        validation=ValidationReport(ok=True),
    )

    config = psihub.render_config_template(record)
    resolver = LocalConfigResolver.from_text(config, root=tmp_path / "workspace")

    assert '[refs."psi://demo\\"org/quote\\"pkg/services/api"]' in config
    assert '[refs."psi://demo\\"org/quote\\"pkg/services/api".metadata]' in config
    assert resolver.resolve(ref).metadata == {"policy_url": "http://policy"}


def test_card_rendering_skips_malformed_endpoint_metadata(tmp_path):
    record = PackageRecord(
        org="demo",
        name="cards",
        version="0.1.0",
        kind="service",
        description="Card rendering boundary.",
        root=tmp_path,
        manifest_path=tmp_path / "psi.toml",
        validation=ValidationReport(ok=True),
        resources=(
            HubResource(
                kind="service",
                name="api",
                ref="psi://demo/cards/services/api",
                metadata={
                    "endpoints": [
                        {
                            "method": "POST",
                            "path": "/ok",
                            "name": "ok",
                            "mode": "run",
                        },
                        {"method": 123, "path": "/coerced-method"},
                        {"method": "GET", "path": 123},
                        {"method": "GET", "path": "/bad name"},
                        {"method": "TRACE", "path": "/trace"},
                        {"method": "GET", "path": "/bad-label", "name": 123},
                    ]
                },
            ),
        ),
    )

    card = render_package_card(record)
    agent_card = render_agent_card(record)

    for text in (card, agent_card):
        assert "Endpoint: `POST /ok` (ok, run)" in text
        assert "coerced-method" not in text
        assert "GET 123" not in text
        assert "/bad name" not in text
        assert "/trace" not in text
        assert "/bad-label" not in text


def test_card_rendering_skips_malformed_example_metadata(tmp_path):
    record = PackageRecord(
        org="demo",
        name="cards",
        version="0.1.0",
        kind="tactic",
        description="Card rendering boundary.",
        root=tmp_path,
        manifest_path=tmp_path / "psi.toml",
        validation=ValidationReport(ok=True),
        resources=(
            HubResource(
                kind="tactic",
                name="echo",
                ref="psi://demo/cards/tactics/echo",
                metadata={
                    "examples": [
                        {
                            "description": "Uppercase text.",
                            "input": {"text": "hello"},
                            "output": {"text": "HELLO"},
                        },
                        {"description": 123, "input": {"text": "bad"}},
                        {"name": object(), "input": {"text": "bad"}},
                        {"description": "Bad input.", "input": object()},
                        {
                            "description": "Partial output.",
                            "input": {"text": "ok"},
                            "output": object(),
                        },
                    ]
                },
            ),
        ),
    )

    card = render_package_card(record)
    agent_card = render_agent_card(record)

    for text in (card, agent_card):
        assert 'Example: Uppercase text. `input={"text":"hello"}`' in text
        assert 'Example: Partial output. `input={"text":"ok"}`' in text
        assert "123" not in text
        assert "object at" not in text
        assert "Bad input" not in text
        assert '{"text":"bad"}' not in text


def test_local_publish_excludes_local_secret_config_and_cache_files(tmp_path):
    package = make_lifecycle_package(tmp_path)
    (package / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    (package / ".env.local").write_text("TOKEN=local-secret\n", encoding="utf-8")
    (package / ".env.example").write_text("TOKEN=\n", encoding="utf-8")
    (package / ".psi").mkdir()
    (package / ".psi" / "config.toml").write_text("[refs]\n", encoding="utf-8")
    (package / ".psihub").mkdir()
    (package / ".psihub" / "index.json").write_text("{}", encoding="utf-8")
    (package / "__pycache__").mkdir()
    (package / "__pycache__" / "demo.cpython-312.pyc").write_bytes(b"cache")
    (package / "demo.egg-info").mkdir()
    (package / "demo.egg-info" / "PKG-INFO").write_text("cache\n", encoding="utf-8")
    hub = LocalHub(tmp_path / "hub")

    record = hub.publish(package)
    downloaded = hub.download("demo/echo", tmp_path / "downloaded")

    excluded = (
        ".env",
        ".env.local",
        ".psi/config.toml",
        ".psihub/index.json",
        "__pycache__/demo.cpython-312.pyc",
        "demo.egg-info/PKG-INFO",
    )
    for root in (record.root, downloaded):
        for relative in excluded:
            assert not (root / relative).exists()
        assert (root / ".env.example").read_text(encoding="utf-8") == "TOKEN=\n"


def test_local_hub_returns_isolated_package_records(tmp_path):
    package = make_lifecycle_package(tmp_path)
    hub = LocalHub(tmp_path / "hub")

    published = hub.publish(package)
    fetched = hub.get("demo/echo")
    listed = hub.list()[0]
    for record in (published, fetched, listed):
        tactic = next(
            resource for resource in record.resources if resource.kind == "tactic"
        )
        tactic.metadata["examples"][0]["input"]["text"] = "mutated"

    stored = hub.get("demo/echo")
    tactic = next(
        resource for resource in stored.resources if resource.kind == "tactic"
    )

    assert tactic.metadata["examples"][0]["input"] == {"text": "hello"}


def test_config_template_honors_service_metadata_port(tmp_path):
    package = make_lifecycle_package(tmp_path)
    manifest = package / "psi.toml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            '[services.api.metadata]\npolicy_url = "http://policy"',
            '[services.api.metadata]\nport = 8700\npolicy_url = "http://policy"',
        ),
        encoding="utf-8",
    )
    hub = LocalHub(tmp_path / "hub")

    hub.publish(package)
    config = hub.config_template("demo/echo")
    resolver = LocalConfigResolver.from_text(config, root=tmp_path / "workspace")

    assert "[services.api]" in config
    assert "port = 8700" in config
    assert 'url = "http://127.0.0.1:8700"' in config
    assert '[refs."psi://demo/echo/services/api".metadata]' in config
    assert resolver.service("api") == {"port": 8700}
    assert resolver.resolve("psi://demo/echo/services/api").metadata["port"] == 8700


def test_local_publish_replaces_same_package_version_deterministically(tmp_path):
    package = make_lifecycle_package(tmp_path)
    hub = LocalHub(tmp_path / "hub")

    first = hub.publish(package)
    text = (package / "psi.toml").read_text(encoding="utf-8")
    (package / "psi.toml").write_text(
        text.replace(
            'summary = "Echo tactic package."',
            'summary = "Updated echo package."',
        ),
        encoding="utf-8",
    )
    second = hub.publish(package)

    assert first.key == second.key == "demo/echo@0.1.0"
    assert [record.key for record in hub.list()] == ["demo/echo@0.1.0"]
    assert "Updated echo package." in hub.card("demo/echo")


def test_local_hub_get_uses_numeric_version_order_for_latest(tmp_path):
    package = make_lifecycle_package(tmp_path)
    manifest = package / "psi.toml"
    hub = LocalHub(tmp_path / "hub")

    text = manifest.read_text(encoding="utf-8")
    manifest.write_text(
        text.replace('version = "0.1.0"', 'version = "0.2.0"'),
        encoding="utf-8",
    )
    older = hub.publish(package)

    text = manifest.read_text(encoding="utf-8")
    manifest.write_text(
        text.replace('version = "0.2.0"', 'version = "0.10.0"').replace(
            'summary = "Echo tactic package."',
            'summary = "Newer numeric echo package."',
        ),
        encoding="utf-8",
    )
    newer = hub.publish(package)

    assert older.key == "demo/echo@0.2.0"
    assert newer.key == "demo/echo@0.10.0"
    assert hub.get("demo/echo").version == "0.10.0"
    assert hub.get("demo/echo", version="0.2.0").version == "0.2.0"
    assert "Newer numeric echo package." in hub.card("demo/echo")
    assert "Echo tactic package." in hub.card("demo/echo", version="0.2.0")


def test_local_hub_rejects_malformed_version_selectors(tmp_path):
    package = make_lifecycle_package(tmp_path)
    hub = LocalHub(tmp_path / "hub")
    hub.publish(package)

    helpers = (
        lambda value: hub.get("demo/echo", version=value),
        lambda value: hub.card("demo/echo", version=value),
        lambda value: hub.agent_card("demo/echo", version=value),
        lambda value: hub.config_template("demo/echo", version=value),
        lambda value: hub.download(
            "demo/echo",
            tmp_path / "downloaded",
            version=value,
        ),
    )

    for value in (
        None,
        123,
        b"0.1.0",
        "",
        "   ",
        ".",
        "..",
        "0.1.0 beta",
        "bad/version",
        "0.1.0%2Fbad",
    ):
        if value is None:
            assert hub.get("demo/echo", version=value).version == "0.1.0"
            continue
        for helper in helpers:
            with pytest.raises(ValueError, match="package version"):
                helper(value)  # type: ignore[arg-type]


def test_local_hub_reopens_published_index(tmp_path):
    package = make_lifecycle_package(tmp_path)
    hub_root = tmp_path / "hub"
    hub = LocalHub(hub_root)

    published = hub.publish(package)
    reopened = LocalHub(hub_root)
    downloaded = reopened.download("demo/echo", tmp_path / "downloaded")

    assert [record.key for record in reopened.list()] == [published.key]
    assert reopened.get("demo/echo").key == published.key
    assert "psi://demo/echo/tactics/echo" in reopened.card("demo/echo")
    assert "Agent Card: demo/echo" in reopened.agent_card("demo/echo")
    assert '[refs."psi://demo/echo/services/api"]' in reopened.config_template(
        "demo/echo"
    )
    assert (downloaded / "psi.toml").exists()


def test_local_hub_rejects_path_control_record_identity_on_load(tmp_path):
    package = make_lifecycle_package(tmp_path)
    hub_root = tmp_path / "hub"
    LocalHub(hub_root).publish(package)
    index_path = hub_root / "index" / "packages.json"
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    payload["records"][0]["record"]["name"] = ".."
    index_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="path segment"):
        LocalHub(hub_root)


def test_local_hub_rejects_duplicate_index_keys_on_load(tmp_path):
    package = make_lifecycle_package(tmp_path)
    hub_root = tmp_path / "hub"
    LocalHub(hub_root).publish(package)
    index_path = hub_root / "index" / "packages.json"
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    payload["records"].append(deepcopy(payload["records"][0]))
    index_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate key"):
        LocalHub(hub_root)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ("[]", "root must be an object"),
        ('{"records": {}}', "records must be a list"),
        ('{"records": [null]}', "record 0: must be an object"),
        ('{"records": [{"key": "", "record": {}}]}', "key must be a string"),
        ('{"records": [{"key": "demo/echo@0.1.0"}]}', "record must be an object"),
    ],
)
def test_local_hub_rejects_malformed_index_shape(tmp_path, payload, message):
    hub_root = tmp_path / "hub"
    index_path = hub_root / "index" / "packages.json"
    index_path.parent.mkdir(parents=True)
    index_path.write_text(payload, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        LocalHub(hub_root)


def test_local_hub_rejects_invalid_package_identifiers(tmp_path):
    hub = LocalHub(tmp_path / "hub")

    for identifier in (
        "demo",
        "demo/",
        "/pkg",
        "../pkg",
        "demo/..",
        "demo org/pkg",
        "demo/bad pkg",
        "demo%2Forg/pkg",
        "demo/bad%2Fpkg",
    ):
        with pytest.raises(ValueError, match="path segment|org/name"):
            hub.get(identifier)

    with pytest.raises(ValueError, match="org/name"):
        hub.get("demo/pkg/extra")


def test_cli_validate_publish_get_and_card(tmp_path, capsys):
    package = make_lifecycle_package(tmp_path)
    hub = tmp_path / "hub"
    dest = tmp_path / "clean"

    assert main(["--hub", str(hub), "validate", str(package)]) == 0
    assert "ok" in capsys.readouterr().out

    assert main(["--hub", str(hub), "publish", str(package), "--local"]) == 0
    assert "demo/echo@0.1.0" in capsys.readouterr().out

    assert main(["--hub", str(hub), "get", "demo/echo", "--dest", str(dest)]) == 0
    assert (dest / "echo" / "psi.toml").exists()

    assert main(["--hub", str(hub), "card", "demo/echo"]) == 0
    assert "psi://demo/echo/tactics/echo" in capsys.readouterr().out

    assert main(["--hub", str(hub), "agent-card", "demo/echo"]) == 0
    assert "Agent Card: demo/echo" in capsys.readouterr().out


@pytest.mark.parametrize(
    "args",
    [
        ["serve", "--host", ""],
        ["serve", "--host", " 127.0.0.1 "],
        ["serve", "--host", "bad host"],
        ["serve", "--host", "http://127.0.0.1"],
        ["serve", "--port", "0"],
        ["serve", "--port", "70000"],
    ],
)
def test_cli_serve_rejects_malformed_bindings_before_hub(tmp_path, capsys, args):
    hub = tmp_path / "hub"

    with pytest.raises(SystemExit) as exc_info:
        main(["--hub", str(hub), *args])

    assert exc_info.value.code == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert "serve " in output.err
    assert not hub.exists()


def test_cli_rejects_blank_hub_without_traceback(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main(["--hub", "   ", "list"])

    assert exc_info.value.code == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert "hub root must be a non-empty path string" in output.err
    assert "Traceback" not in output.err


@pytest.mark.parametrize("payload", ["[]", '{"records": [null]}'])
def test_cli_reports_malformed_hub_index_without_traceback(tmp_path, capsys, payload):
    hub = tmp_path / "hub"
    index_path = hub / "index" / "packages.json"
    index_path.parent.mkdir(parents=True)
    index_path.write_text(payload, encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        main(["--hub", str(hub), "list"])

    assert exc_info.value.code == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert "Invalid local hub index" in output.err
    assert "Traceback" not in output.err


@pytest.mark.parametrize(
    "args",
    [
        ["init", "--org", ".."],
        ["init", "--name", ""],
        ["init", "--name", "bad/name"],
        ["init", "--name", "bad%2Fname"],
        ["init", "--kind", "unknown"],
    ],
)
def test_cli_init_rejects_invalid_identity_without_traceback(tmp_path, capsys, args):
    target = tmp_path / "pkg"
    with pytest.raises(SystemExit) as exc_info:
        main([*args, str(target)])

    assert exc_info.value.code == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert "Traceback" not in output.err
    assert not target.exists()


@pytest.mark.parametrize(
    "args",
    [
        ["publish", "   ", "--local"],
        ["get", "demo"],
        ["card", "demo/.."],
        ["agent-card", "demo/missing"],
        ["config-template", "demo"],
    ],
)
def test_cli_reports_hub_lookup_errors_without_traceback(tmp_path, capsys, args):
    with pytest.raises(SystemExit) as exc_info:
        main(["--hub", str(tmp_path / "hub"), *args])

    assert exc_info.value.code == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert "Traceback" not in output.err


def test_cli_publish_rejects_invalid_package(tmp_path, capsys):
    package = make_lifecycle_package(tmp_path)
    text = (package / "psi.toml").read_text(encoding="utf-8")
    (package / "psi.toml").write_text(
        text.replace('tactic = "echo"', 'tactic = "missing"'),
        encoding="utf-8",
    )
    hub = tmp_path / "hub"

    assert main(["--hub", str(hub), "publish", str(package), "--local"]) == 1
    output = capsys.readouterr()

    assert "failed" in output.out
    assert "service_tactic_missing" in output.err
    assert LocalHub(hub).list() == ()


def test_lifecycle_covers_tactic_channel_and_combined_packages(tmp_path):
    tactic_package = make_lifecycle_package(tmp_path)
    channel_package = make_channel_package(tmp_path)
    combined_package = make_combined_package(tmp_path)
    hub = LocalHub(tmp_path / "hub")

    for package in (tactic_package, channel_package, combined_package):
        assert validate_package(package).ok
        hub.publish(package)

    downloaded = hub.download("demo/combo", tmp_path / "downloaded")
    card = hub.card("demo/combo")
    agent_card = hub.agent_card("demo/combo")
    config = hub.config_template("demo/combo")
    resolver = LocalConfigResolver.from_text(config, root=tmp_path / "workspace")

    assert validate_package(downloaded).ok
    assert "demo/echo@0.1.0" in [record.key for record in hub.list()]
    assert "demo/events@0.1.0" in [record.key for record in hub.list()]
    assert "demo/combo@0.1.0" in [record.key for record in hub.list()]
    assert "psi://demo/combo/tactics/analyze" in card
    assert "psi://demo/combo/channels/events" in card
    assert "psi://demo/combo/snapshots/latest_analysis" in card
    assert "psi://demo/combo/services/analyzer" in card
    assert "Endpoint: `POST /analyze`" in card
    assert "Endpoint: `GET /channels/events/range`" in card
    assert "Endpoint: `POST /analyze`" in agent_card
    assert '[refs."psi://demo/combo/tactics/analyze"]' in config
    assert '[refs."psi://demo/combo/tactics/monitor"]' in config
    assert '[refs."psi://demo/combo/channels/events"]' in config
    assert '[refs."psi://demo/combo/snapshots/latest_analysis"]' in config
    assert "[services.analyzer]" in config
    assert "[services.monitor]" in config
    assert "[stores.default]" in config
    assert resolver.resolve("psi://demo/combo/tactics/analyze").url == (
        "http://127.0.0.1:8000/tactics/analyze"
    )
    assert resolver.resolve("psi://demo/combo/tactics/monitor").url == (
        "http://127.0.0.1:8001/tactics/monitor"
    )
    assert resolver.resolve("psi://demo/combo/services/analyzer").url == (
        "http://127.0.0.1:8000"
    )
    assert resolver.resolve("psi://demo/combo/services/monitor").url == (
        "http://127.0.0.1:8001"
    )
    assert resolver.resolve("psi://demo/combo/channels/events").store == ".sssn"
    assert (
        resolver.resolve("psi://demo/combo/snapshots/latest_analysis").store == ".sssn"
    )
    assert resolver.service("analyzer") == {"port": 8000}
    assert resolver.service("monitor") == {"port": 8001}
    assert resolver.store("default") == {"path": ".sssn"}


def test_downloaded_packages_can_seed_downstream_composition_package(tmp_path):
    tactic_package = make_lifecycle_package(tmp_path)
    channel_package = make_channel_package(tmp_path)
    hub = LocalHub(tmp_path / "hub")
    hub.publish(tactic_package)
    hub.publish(channel_package)

    downloaded_root = tmp_path / "downloaded"
    downloaded_tactic = hub.download("demo/echo", downloaded_root)
    downloaded_channel = hub.download("demo/events", downloaded_root)
    tactic_manifest = load_manifest(downloaded_tactic)
    channel_manifest = load_manifest(downloaded_channel)
    event_schema_ref = channel_manifest.ref("schema", "event_payload")
    output_schema_ref = tactic_manifest.ref("schema", "echo_output")

    downstream = tmp_path / "downstream"
    module = downstream / "consumer"
    module.mkdir(parents=True)
    (downstream / "README.md").write_text(
        "# Downstream\n\nComposes downloaded package contracts.\n",
        encoding="utf-8",
    )
    (module / "__init__.py").write_text("", encoding="utf-8")
    (module / "tactics.py").write_text(
        """
class Summarize:
    name = "summarize"

    def run(self, input_value, *, context=None):
        if isinstance(input_value, dict):
            text = input_value["text"]
        else:
            text = input_value.text
        return {"text": text.upper()}
""".lstrip(),
        encoding="utf-8",
    )
    (module / "service.py").write_text(
        """
def create_app():
    return {"service": "downstream"}
""".lstrip(),
        encoding="utf-8",
    )
    (downstream / "psi.toml").write_text(
        f"""
[package]
psi_version = "0.1"
org = "demo"
name = "downstream"
version = "0.1.0"
kind = "app"
primary = "services.analyzer"
description = "Downstream package built from downloaded package contracts."

[card]
summary = "Downstream composition package."

[docs.readme]
path = "README.md"
title = "README"

[tactics.summarize]
entry = "consumer.tactics:Summarize"
input = "{event_schema_ref}"
output = "{output_schema_ref}"

[channels.events]
schema = "{event_schema_ref}"
form = "log"

[channels.analysis]
schema = "{output_schema_ref}"
form = "log"

[services.analyzer]
entry = "consumer.service:create_app"
tactic = "summarize"
subscribes = ["events"]
publishes = ["analysis"]

[runs.local]
services = ["analyzer"]
channels = ["events", "analysis"]
""".lstrip(),
        encoding="utf-8",
    )

    report = validate_package(downstream)
    downstream_record = hub.publish(downstream)
    downloaded_downstream = hub.download("demo/downstream", tmp_path / "consumer-copy")
    config = hub.config_template("demo/downstream")
    resolver = LocalConfigResolver.from_text(config, root=tmp_path / "workspace")

    assert validate_package(downloaded_tactic).ok
    assert validate_package(downloaded_channel).ok
    assert report.ok
    assert not [issue for issue in report.issues if issue.level == "error"]
    assert downstream_record.validation.ok
    assert validate_package(downloaded_downstream).ok
    assert event_schema_ref == "psi://demo/events/schemas/event_payload"
    assert output_schema_ref == "psi://demo/echo/schemas/echo_output"
    assert '[refs."psi://demo/downstream/tactics/summarize"]' in config
    assert '[refs."psi://demo/downstream/channels/events"]' in config
    assert resolver.resolve("psi://demo/downstream/tactics/summarize").url == (
        "http://127.0.0.1:8000/tactics/summarize"
    )
    assert resolver.resolve("psi://demo/downstream/channels/analysis").store == ".sssn"


def test_local_config_resolver_supports_registered_objects():
    resolver = LocalConfigResolver()
    obj = object()

    resolver.bind("psi://demo/pkg/tactics/local", object=obj)

    assert resolver.resolve("psi://demo/pkg/tactics/local").object is obj


def test_local_config_resolver_rejects_invalid_refs(tmp_path):
    with pytest.raises(ValueError, match="psi://"):
        LocalConfigResolver.from_text(
            """
[refs."not-a-ref"]
url = "http://service"
""".lstrip(),
            root=tmp_path / "workspace",
        )

    resolver = LocalConfigResolver()

    with pytest.raises(ValueError, match="query"):
        resolver.bind("psi://demo/pkg/tactics/local?env=dev", url="http://service")

    with pytest.raises(ValueError, match="unknown resource"):
        resolver.bind("psi://demo/pkg/widgets/local", url="http://service")

    for ref in (
        "psi://../pkg/tactics/local",
        "psi://demo/./tactics/local",
        "psi://demo/pkg/tactics/..",
    ):
        with pytest.raises(ValueError, match="invalid segment"):
            resolver.bind(ref, url="http://service")
        with pytest.raises(ValueError, match="invalid segment"):
            resolver.resolve(ref)

    for ref in (
        "psi://demo/pkg/tactics//local",
        "psi://demo/pkg//tactics/local",
        "psi://demo/pkg/tactics/local/",
    ):
        with pytest.raises(ValueError, match="shape"):
            resolver.bind(ref, url="http://service")
        with pytest.raises(ValueError, match="shape"):
            resolver.resolve(ref)

    for ref in (
        "psi://demo/   /tactics/local",
        "psi://demo/pkg/tactics/   ",
    ):
        with pytest.raises(ValueError, match="empty segment"):
            resolver.bind(ref, url="http://service")
        with pytest.raises(ValueError, match="empty segment"):
            resolver.resolve(ref)

    for ref in (
        "psi://demo org/pkg/tactics/local",
        "psi://demo/pkg name/tactics/local",
        "psi://demo/pkg/tact ics/local",
        "psi://demo/pkg/tactics/local name",
    ):
        with pytest.raises(ValueError, match="whitespace-bearing"):
            parse_psi_ref(ref)
        with pytest.raises(ValueError, match="whitespace-bearing"):
            validate_psi_ref(ref)
        with pytest.raises(ValueError, match="whitespace-bearing"):
            resolver.bind(ref, url="http://service")
        with pytest.raises(ValueError, match="whitespace-bearing"):
            resolver.resolve(ref)

    for ref in (
        "psi://demo%2Forg/pkg/tactics/local",
        "psi://demo/pkg%2Fname/tactics/local",
        "psi://demo/pkg/tactics/local%2Fname",
        "psi://demo/pkg/tactics/local%5Cname",
        "psi://demo/pkg/tactics/%2E%2E",
        "psi://demo/pkg/tactics/local%20name",
        "psi://demo/pkg/tactics/local%3Aname",
    ):
        with pytest.raises(ValueError, match="invalid segment|whitespace-bearing"):
            parse_psi_ref(ref)
        with pytest.raises(ValueError, match="invalid segment|whitespace-bearing"):
            validate_psi_ref(ref)
        with pytest.raises(ValueError, match="invalid segment|whitespace-bearing"):
            resolver.bind(ref, url="http://service")
        with pytest.raises(ValueError, match="invalid segment|whitespace-bearing"):
            resolver.resolve(ref)


def test_psi_ref_helpers_reject_non_string_and_blank_refs():
    resolver = LocalConfigResolver()

    for ref in (None, 123, b"psi://demo/pkg/tactics/local", "", "   "):
        with pytest.raises(ValueError, match="non-empty string"):
            parse_psi_ref(ref)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="non-empty string"):
            validate_psi_ref(ref)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="non-empty string"):
            resolver.bind(ref, url="http://service")  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="non-empty string"):
            resolver.resolve(ref)  # type: ignore[arg-type]


def test_local_config_resolver_requires_one_concrete_target(tmp_path):
    with pytest.raises(ValueError, match="one concrete target"):
        LocalConfigResolver.from_text(
            """
[refs."psi://demo/pkg/tactics/local"]
""".lstrip(),
            root=tmp_path / "workspace",
        )

    with pytest.raises(ValueError, match="only one concrete target"):
        LocalConfigResolver.from_text(
            """
[refs."psi://demo/pkg/tactics/local"]
url = "http://service"
store = ".sssn"
""".lstrip(),
            root=tmp_path / "workspace",
        )

    resolver = LocalConfigResolver.from_text(
        """
[refs."psi://demo/pkg/tactics/local"]
url = "http://service"
policy_url = "http://policy"
""".lstrip(),
        root=tmp_path / "workspace",
    )

    binding = resolver.resolve("psi://demo/pkg/tactics/local")
    assert binding.url == "http://service"
    assert binding.metadata == {"policy_url": "http://policy"}


def test_local_config_resolver_flattens_ref_metadata_table(tmp_path):
    resolver = LocalConfigResolver.from_text(
        """
[refs."psi://demo/pkg/tactics/local"]
url = "http://service"
policy_url = "http://legacy"
label = "legacy-extra"

[refs."psi://demo/pkg/tactics/local".metadata]
policy_url = "http://policy"
headers = { x_policy = "demo" }
""".lstrip(),
        root=tmp_path / "workspace",
    )

    binding = resolver.resolve("psi://demo/pkg/tactics/local")
    assert binding.metadata == {
        "policy_url": "http://policy",
        "label": "legacy-extra",
        "headers": {"x_policy": "demo"},
    }


def test_local_config_resolver_rejects_non_mapping_metadata():
    resolver = LocalConfigResolver()

    with pytest.raises(ValueError, match="metadata"):
        resolver.bind(
            "psi://demo/pkg/tactics/local",
            url="http://service",
            metadata=["bad"],  # type: ignore[arg-type]
        )


def test_local_config_resolver_rejects_non_table_ref_metadata(tmp_path):
    with pytest.raises(ValueError, match=r"\[refs\."):
        LocalConfigResolver.from_text(
            """
[refs."psi://demo/pkg/tactics/local"]
url = "http://service"
metadata = "bad"
""".lstrip(),
            root=tmp_path / "workspace",
        )


def test_local_config_resolver_returns_isolated_binding_metadata():
    resolver = LocalConfigResolver()
    headers = {"x-policy": "demo"}
    metadata = {"headers": MappingProxyType(headers)}
    resolver.bind(
        "psi://demo/pkg/tactics/local",
        url="http://service",
        metadata=MappingProxyType(metadata),
    )

    headers["x-policy"] = "changed"
    resolved = resolver.resolve("psi://demo/pkg/tactics/local")
    assert resolved.metadata == {"headers": {"x-policy": "demo"}}

    assert resolved.metadata is not None
    resolved.metadata["headers"]["x-policy"] = "mutated"
    assert resolver.resolve("psi://demo/pkg/tactics/local").metadata == {
        "headers": {"x-policy": "demo"}
    }


def test_local_config_resolver_rejects_non_string_targets(tmp_path):
    for target_line in (
        "url = 123",
        "url = \"\"",
        "url = \"   \"",
        "url = \"http://bad host\"",
        "store = false",
        "store = \"\"",
        "store = \"   \"",
        "store = \"bad store\"",
        'path = ["x"]',
        "path = \"\"",
        "path = \"   \"",
        "path = \"bad path\"",
    ):
        with pytest.raises(ValueError, match="non-empty string"):
            LocalConfigResolver.from_text(
                f"""
[refs."psi://demo/pkg/tactics/local"]
{target_line}
""".lstrip(),
                root=tmp_path / target_line.split(" ", 1)[0],
            )


def test_local_config_resolver_rejects_malformed_url_targets(tmp_path):
    resolver = LocalConfigResolver()
    for url in ("service", "/service", "ftp://service", "http://"):
        with pytest.raises(ValueError, match="absolute HTTP"):
            resolver.bind("psi://demo/pkg/tactics/local", url=url)

    for index, url in enumerate(("service", "/service", "ftp://service"), start=1):
        with pytest.raises(ValueError, match="absolute HTTP"):
            LocalConfigResolver.from_text(
                f"""
[refs."psi://demo/pkg/tactics/local"]
url = "{url}"
""".lstrip(),
                root=tmp_path / f"url-{index}",
            )


def test_local_config_resolver_rejects_invalid_settings_table(tmp_path):
    with pytest.raises(ValueError, match=r"\[settings\]"):
        LocalConfigResolver.from_text(
            """
settings = "not-a-table"
""".lstrip(),
            root=tmp_path / "workspace",
        )


def test_local_config_resolver_reads_service_and_store_tables(tmp_path):
    resolver = LocalConfigResolver.from_text(
        """
[services.api]
port = 8000

[stores.default]
path = ".sssn"
""".lstrip(),
        root=tmp_path / "workspace",
    )

    assert resolver.services() == {"api": {"port": 8000}}
    assert resolver.service("api") == {"port": 8000}
    assert resolver.stores() == {"default": {"path": ".sssn"}}
    assert resolver.store("default") == {"path": ".sssn"}

    with pytest.raises(KeyError):
        resolver.service("missing")
    with pytest.raises(KeyError):
        resolver.store("missing")

    for invalid_name in (None, 123, "", "   ", ".", "..", "bad/name", "bad name"):
        with pytest.raises(ValueError, match="path-segment"):
            resolver.service(invalid_name)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="path-segment"):
            resolver.store(invalid_name)  # type: ignore[arg-type]


def test_local_config_resolver_returns_isolated_nested_config_tables(tmp_path):
    resolver = LocalConfigResolver.from_text(
        """
[settings]
tags = ["alpha"]

[services.api]
port = 8000

[services.api.metadata]
policy_url = "http://policy"

[stores.default]
path = ".sssn"

[stores.default.metadata]
owner = "demo"
""".lstrip(),
        root=tmp_path / "workspace",
    )

    settings = resolver.settings()
    settings["tags"].append("beta")
    assert resolver.settings() == {"tags": ["alpha"]}

    tag_setting = resolver.setting("tags")
    tag_setting.append("gamma")
    assert resolver.setting("tags") == ["alpha"]

    service = resolver.service("api")
    service["metadata"]["policy_url"] = "http://changed"
    assert resolver.service("api")["metadata"]["policy_url"] == "http://policy"

    services = resolver.services()
    services["api"]["metadata"]["policy_url"] = "http://changed-again"
    assert resolver.services()["api"]["metadata"]["policy_url"] == "http://policy"

    store = resolver.store("default")
    store["metadata"]["owner"] = "changed"
    assert resolver.store("default")["metadata"]["owner"] == "demo"

    stores = resolver.stores()
    stores["default"]["metadata"]["owner"] = "changed-again"
    assert resolver.stores()["default"]["metadata"]["owner"] == "demo"


def test_local_config_resolver_rejects_invalid_service_store_tables(tmp_path):
    with pytest.raises(ValueError, match=r"\[services\.api\]"):
        LocalConfigResolver.from_text(
            """
[services]
api = "not-a-table"
""".lstrip(),
            root=tmp_path / "workspace",
        )

    with pytest.raises(ValueError, match=r"\[stores\.default\]"):
        LocalConfigResolver.from_text(
            """
[stores]
default = ".sssn"
""".lstrip(),
            root=tmp_path / "workspace",
        )

    for section, name in (
        ("services", "../api"),
        ("services", "."),
        ("services", "bad api"),
        ("services", "api%2Fhidden"),
        ("stores", "bad/name"),
        ("stores", ".."),
        ("stores", "bad store"),
        ("stores", "default%20bad"),
    ):
        with pytest.raises(ValueError, match="path-segment"):
            LocalConfigResolver.from_text(
                f"""
[{section}."{name}"]
path = ".sssn"
""".lstrip(),
                root=tmp_path / f"{section}-{name.replace('/', '-')}",
            )


def test_local_config_resolver_rejects_invalid_service_store_values(tmp_path):
    for index, port in enumerate(('"bad"', "70000", "false"), start=1):
        with pytest.raises(ValueError, match="port"):
            LocalConfigResolver.from_text(
                f"""
[services.api]
port = {port}
""".lstrip(),
                root=tmp_path / f"port-{index}",
            )

    for index, path in enumerate(("123", '""', '"   "', '"bad path"'), start=1):
        with pytest.raises(ValueError, match="path"):
            LocalConfigResolver.from_text(
                f"""
[stores.default]
path = {path}
""".lstrip(),
                root=tmp_path / f"path-{index}",
            )

    for index, (section, name, value) in enumerate(
        (
            ("services", "api", "[]"),
            ("services", "api", '"bad"'),
            ("stores", "default", "[]"),
            ("stores", "default", '"bad"'),
        ),
        start=1,
    ):
        with pytest.raises(ValueError, match=rf"\[{section}\.{name}\.metadata\]"):
            LocalConfigResolver.from_text(
                f"""
[{section}.{name}]
metadata = {value}
""".lstrip(),
                root=tmp_path / f"metadata-{index}",
            )


def make_lifecycle_package(tmp_path: Path) -> Path:
    package = tmp_path / "echo"
    module = package / "demo"
    module.mkdir(parents=True)
    (package / "README.md").write_text("# Echo\n\nDemo package.\n", encoding="utf-8")
    (module / "__init__.py").write_text("", encoding="utf-8")
    (module / "schemas.py").write_text(
        """
from pydantic import BaseModel


class EchoInput(BaseModel):
    text: str


class EchoOutput(BaseModel):
    text: str
""".lstrip(),
        encoding="utf-8",
    )
    (module / "tactics.py").write_text(
        """
from .schemas import EchoInput, EchoOutput


class EchoTactic:
    name = "echo"
    input_type = EchoInput
    output_type = EchoOutput

    def run(self, input_value, *, context=None):
        return EchoOutput(text=input_value.text.upper())
""".lstrip(),
        encoding="utf-8",
    )
    (module / "app.py").write_text(
        """
from .tactics import EchoTactic


def create_app():
    return {"tactic": EchoTactic.name}
""".lstrip(),
        encoding="utf-8",
    )
    (package / "psi.toml").write_text(
        """
[package]
psi_version = "0.1"
org = "demo"
name = "echo"
version = "0.1.0"
kind = "tactic"
primary = "tactics.echo"
description = "Echo tactic package."

[card]
summary = "Echo tactic package."
tags = ["demo", "tactic"]
suggested_commands = ["python -m demo.app"]

[docs.readme]
path = "README.md"
title = "README"
description = "Source-facing package guide."

[schemas.echo_input]
entry = "demo.schemas:EchoInput"

[schemas.echo_output]
entry = "demo.schemas:EchoOutput"

[tactics.echo]
entry = "demo.tactics:EchoTactic"
input = "echo_input"
output = "echo_output"

[[tactics.echo.examples]]
description = "Uppercase text."
input = { text = "hello" }
output = { text = "HELLO" }

[services.api]
entry = "demo.app:create_app"
tactic = "echo"
transport = "fastapi"

[services.api.metadata]
policy_url = "http://policy"

[runs.local]
services = ["api"]
""".lstrip(),
        encoding="utf-8",
    )
    return package


def make_channel_package(tmp_path: Path) -> Path:
    package = tmp_path / "events"
    module = package / "demo_events"
    module.mkdir(parents=True)
    (package / "README.md").write_text("# Events\n\nChannel package.\n", encoding="utf-8")
    (module / "__init__.py").write_text("", encoding="utf-8")
    (module / "schemas.py").write_text(
        """
from pydantic import BaseModel


class EventPayload(BaseModel):
    text: str
""".lstrip(),
        encoding="utf-8",
    )
    (package / "psi.toml").write_text(
        """
[package]
psi_version = "0.1"
org = "demo"
name = "events"
version = "0.1.0"
kind = "channel"
primary = "channels.events"
description = "Events channel package."

[schemas.event_payload]
entry = "demo_events.schemas:EventPayload"

[channels.events]
schema = "event_payload"
form = "log"

[runs.local]
channels = ["events"]
""".lstrip(),
        encoding="utf-8",
    )
    return package


def make_entrypoint_cache_package(
    package: Path,
    *,
    module_body: str,
) -> Path:
    module = package / "sharedpkg"
    module.mkdir(parents=True)
    (package / "README.md").write_text("# Shared\n\nShared package.\n", encoding="utf-8")
    (module / "__init__.py").write_text("", encoding="utf-8")
    (module / "app.py").write_text(module_body, encoding="utf-8")
    (package / "psi.toml").write_text(
        """
[package]
psi_version = "0.1"
org = "demo"
name = "shared"
version = "0.1.0"
kind = "service"
primary = "services.api"
description = "Shared module-name package."

[services.api]
entry = "sharedpkg.app:create_app"
transport = "fastapi"
""".lstrip(),
        encoding="utf-8",
    )
    return package


def make_combined_package(tmp_path: Path) -> Path:
    package = tmp_path / "combo"
    module = package / "combo"
    module.mkdir(parents=True)
    (package / "README.md").write_text("# Combo\n\nCombined package.\n", encoding="utf-8")
    (module / "__init__.py").write_text("", encoding="utf-8")
    (module / "schemas.py").write_text(
        """
from pydantic import BaseModel


class AnalysisInput(BaseModel):
    text: str


class AnalysisOutput(BaseModel):
    summary: str
""".lstrip(),
        encoding="utf-8",
    )
    (module / "tactics.py").write_text(
        """
from .schemas import AnalysisOutput


class Analyze:
    def run(self, task, *, context=None):
        return AnalysisOutput(summary=task.text.upper())
""".lstrip(),
        encoding="utf-8",
    )
    (module / "services.py").write_text(
        """
def create_analyzer():
    return {"service": "analyzer"}


def create_monitor():
    return {"service": "monitor"}
""".lstrip(),
        encoding="utf-8",
    )
    (package / "psi.toml").write_text(
        """
[package]
psi_version = "0.1"
org = "demo"
name = "combo"
version = "0.1.0"
kind = "app"
primary = "services.analyzer"
description = "Combined tactic/channel package."

[schemas.analysis_input]
entry = "combo.schemas:AnalysisInput"

[schemas.analysis_output]
entry = "combo.schemas:AnalysisOutput"

[tactics.analyze]
entry = "combo.tactics:Analyze"
input = "analysis_input"
output = "analysis_output"

[[tactics.analyze.endpoints]]
name = "analyze"
method = "POST"
path = "/analyze"
mode = "run"

[tactics.monitor]
entry = "combo.tactics:Analyze"
input = "analysis_input"
output = "analysis_output"

[channels.events]
schema = "analysis_input"
form = "log"

[[channels.events.endpoints]]
name = "event_range"
method = "GET"
path = "/channels/events/range"
scope = "channel"

[channels.analysis]
schema = "analysis_output"
form = "log"

[snapshots.latest_analysis]
schema = "analysis_output"
channel = "analysis"
description = "Latest analysis result."

[services.analyzer]
entry = "combo.services:create_analyzer"
tactic = "analyze"
subscribes = ["events"]
publishes = ["analysis"]

[services.monitor]
entry = "combo.services:create_monitor"
tactic = "monitor"
transport = "fastapi"
subscribes = ["events"]

[runs.local]
services = ["analyzer", "monitor"]
channels = ["events", "analysis"]
snapshots = ["latest_analysis"]
""".lstrip(),
        encoding="utf-8",
    )
    return package


def make_rich_metadata_package(tmp_path: Path) -> Path:
    package = tmp_path / "rich"
    (package / "docs").mkdir(parents=True)
    (package / "examples").mkdir()
    (package / "assets").mkdir()
    (package / "README.md").write_text("# Rich\n\nRich package.\n", encoding="utf-8")
    (package / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")
    (package / "examples" / "run.py").write_text("print('rich')\n", encoding="utf-8")
    (package / "assets" / "logo.txt").write_text("rich\n", encoding="utf-8")
    (package / "psi.toml").write_text(
        """
[package]
psi_version = "0.1"
org = "demo"
name = "rich"
version = "0.1.0"
kind = "library"
primary = "docs.guide"
description = "Rich metadata package."

[card]
summary = "Rich package card."
tags = ["docs", "demo"]
safety = "Offline demo only."
latency = "Local call under 10 ms."
suggested_commands = ["python examples/run.py"]

[config.schema]
sample_rate = "int"

[config.defaults]
sample_rate = 2

[docs.guide]
path = "docs/guide.md"
title = "Guide"
description = "Package guide."

[examples.quickstart]
path = "examples/run.py"
command = "python examples/run.py"
description = "Run the quickstart."

[assets.logo]
path = "assets/logo.txt"
media_type = "text/plain"
description = "Text logo."
""".lstrip(),
        encoding="utf-8",
    )
    return package
