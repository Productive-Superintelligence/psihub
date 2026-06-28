from pathlib import Path

from psihub import LocalConfigResolver, LocalHub, init_package, load_manifest, validate_package
from psihub.cli import main


def test_init_creates_manifest_and_readme(tmp_path):
    target = tmp_path / "new-package"
    manifest_path = init_package(target, org="demo", name="new-package", kind="tactic")

    assert manifest_path == target / "psi.toml"
    assert (target / "README.md").exists()
    manifest = load_manifest(target)
    assert manifest.package.identifier == "demo/new-package"
    assert manifest.package.kind == "tactic"


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


def test_local_publish_download_card_and_config(tmp_path):
    package = make_lifecycle_package(tmp_path)
    hub = LocalHub(tmp_path / "hub")

    record = hub.publish(package)
    downloaded = hub.download("demo/echo", tmp_path / "downloaded")
    card = hub.card("demo/echo")
    config = hub.config_template("demo/echo")

    assert record.key == "demo/echo@0.1.0"
    assert record.validation.ok
    assert (downloaded / "psi.toml").exists()
    assert "psi://demo/echo/tactics/echo" in card
    assert "psi://demo/echo/services/api" in card
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
    config = hub.config_template("demo/combo")
    resolver = LocalConfigResolver.from_text(config, root=tmp_path / "workspace")

    assert validate_package(downloaded).ok
    assert "demo/echo@0.1.0" in [record.key for record in hub.list()]
    assert "demo/events@0.1.0" in [record.key for record in hub.list()]
    assert "demo/combo@0.1.0" in [record.key for record in hub.list()]
    assert "psi://demo/combo/tactics/analyze" in card
    assert "psi://demo/combo/channels/events" in card
    assert "psi://demo/combo/services/analyzer" in card
    assert '[refs."psi://demo/combo/tactics/analyze"]' in config
    assert '[refs."psi://demo/combo/channels/events"]' in config
    assert resolver.resolve("psi://demo/combo/tactics/analyze").url.endswith(
        "/tactics/analyze"
    )
    assert resolver.resolve("psi://demo/combo/services/analyzer").url == "http://127.0.0.1:8000"
    assert resolver.resolve("psi://demo/combo/channels/events").store == ".sssn"


def test_local_config_resolver_supports_registered_objects():
    resolver = LocalConfigResolver()
    obj = object()

    resolver.bind("psi://demo/pkg/tactics/local", object=obj)

    assert resolver.resolve("psi://demo/pkg/tactics/local").object is obj


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

[channels.events]
schema = "analysis_input"
form = "log"

[channels.analysis]
schema = "analysis_output"
form = "log"

[services.analyzer]
entry = "combo.services:create_analyzer"
tactic = "analyze"
subscribes = ["events"]
publishes = ["analysis"]

[runs.local]
services = ["analyzer"]
channels = ["events", "analysis"]
""".lstrip(),
        encoding="utf-8",
    )
    return package
