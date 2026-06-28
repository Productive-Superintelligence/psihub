from pathlib import Path

import pytest

from psihub import (
    LocalConfigResolver,
    LocalHub,
    PublishValidationError,
    init_package,
    load_manifest,
    validate_package,
)
from psihub.cli import main


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


def test_validate_lifecycle_package(tmp_path):
    package = make_lifecycle_package(tmp_path)

    report = validate_package(package)

    assert report.ok
    assert report.issues == ()


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
            'input = "psi://other/package/schemas/payload"',
        ),
        encoding="utf-8",
    )
    external_report = validate_package(package)

    assert external_report.ok


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


def test_validate_catches_missing_declared_doc(tmp_path):
    package = make_rich_metadata_package(tmp_path)
    (package / "docs" / "guide.md").unlink()

    report = validate_package(package)

    assert not report.ok
    assert any(issue.code == "doc_path_missing" for issue in report.issues)


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
    assert "psi://demo/echo/tactics/echo" in card
    assert "psi://demo/echo/services/api" in card
    assert "Agent Card: demo/echo" in agent_card
    assert "PsiHub describes packages, refs, config, and metadata" in agent_card
    assert "tactic `echo`: `psi://demo/echo/tactics/echo`" in agent_card
    assert 'policy_url="http://policy"' in card
    assert '[refs."psi://demo/echo/tactics/echo"]' in config
    assert '[refs."psi://demo/echo/services/api"]' in config
    assert 'policy_url = "http://policy"' in config
    resolver = LocalConfigResolver.from_text(config, root=tmp_path / "workspace")
    assert (
        resolver.resolve("psi://demo/echo/services/api").metadata["policy_url"]
        == "http://policy"
    )


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
    assert "psi://demo/combo/services/analyzer" in card
    assert "Endpoint: `POST /analyze`" in card
    assert "Endpoint: `GET /channels/events/range`" in card
    assert "Endpoint: `POST /analyze`" in agent_card
    assert '[refs."psi://demo/combo/tactics/analyze"]' in config
    assert '[refs."psi://demo/combo/tactics/monitor"]' in config
    assert '[refs."psi://demo/combo/channels/events"]' in config
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

[schemas.echo_input]
entry = "demo.schemas:EchoInput"

[schemas.echo_output]
entry = "demo.schemas:EchoOutput"

[tactics.echo]
entry = "demo.tactics:EchoTactic"
input = "echo_input"
output = "echo_output"

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
