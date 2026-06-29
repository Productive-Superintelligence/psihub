import importlib.util
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from psihub import (
    LocalConfigResolver,
    LocalHub,
    PublishValidationError,
    init_package,
    load_manifest,
    manifest_path,
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

    with pytest.raises(ValueError, match="path segment"):
        init_package(target, org="..", name="pkg")
    with pytest.raises(ValueError, match="Input should be"):
        init_package(target, org="demo", name="pkg", kind="unknown")
    assert not (target / "psi.toml").exists()


def test_public_path_helpers_reject_blank_or_non_path_values(tmp_path):
    for value in ("   ", 123):
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
        lambda: PackageRecord(
            org="demo",
            name="   ",
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
    ],
)
def test_package_identity_models_reject_whitespace_segments(factory):
    with pytest.raises(ValueError, match="path segment"):
        factory()


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
        original.replace('scope = "channel"', 'scope = "wrong"'),
        encoding="utf-8",
    )
    scope_report = validate_package(package)

    assert not scope_report.ok
    assert any(
        issue.code == "endpoint_scope_invalid" for issue in scope_report.issues
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
    assert "[services.api]" in config
    assert "port = 8000" in config
    assert 'policy_url = "http://policy"' in config
    resolver = LocalConfigResolver.from_text(config, root=tmp_path / "workspace")
    assert (
        resolver.resolve("psi://demo/echo/services/api").metadata["policy_url"]
        == "http://policy"
    )
    assert resolver.service("api") == {"port": 8000}


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


def test_local_hub_rejects_invalid_package_identifiers(tmp_path):
    hub = LocalHub(tmp_path / "hub")

    for identifier in ("demo", "demo/", "/pkg", "../pkg", "demo/.."):
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


def test_local_config_resolver_rejects_non_mapping_metadata():
    resolver = LocalConfigResolver()

    with pytest.raises(ValueError, match="metadata"):
        resolver.bind(
            "psi://demo/pkg/tactics/local",
            url="http://service",
            metadata=["bad"],  # type: ignore[arg-type]
        )


def test_local_config_resolver_returns_isolated_binding_metadata():
    resolver = LocalConfigResolver()
    metadata = {"headers": {"x-policy": "demo"}}
    resolver.bind(
        "psi://demo/pkg/tactics/local",
        url="http://service",
        metadata=metadata,
    )

    metadata["headers"]["x-policy"] = "changed"
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
        "store = false",
        "store = \"\"",
        "store = \"   \"",
        'path = ["x"]',
        "path = \"\"",
        "path = \"   \"",
    ):
        with pytest.raises(ValueError, match="non-empty string"):
            LocalConfigResolver.from_text(
                f"""
[refs."psi://demo/pkg/tactics/local"]
{target_line}
""".lstrip(),
                root=tmp_path / target_line.split(" ", 1)[0],
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
        ("stores", "bad/name"),
        ("stores", ".."),
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

    for index, path in enumerate(("123", '""', '"   "'), start=1):
        with pytest.raises(ValueError, match="path"):
            LocalConfigResolver.from_text(
                f"""
[stores.default]
path = {path}
""".lstrip(),
                root=tmp_path / f"path-{index}",
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
