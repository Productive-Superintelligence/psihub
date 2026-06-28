from pathlib import Path

from psihub import LocalHub, init_package, validate_package


def run_workflow(root: str | Path):
    """Run the local package lifecycle without a hosted hub."""

    root = Path(root)
    package = root / "demo-package"
    hub_root = root / ".psihub"
    download_root = root / "downloaded"

    manifest_path = init_package(
        package,
        org="demo",
        name="echo",
        kind="tactic",
        force=True,
    )
    report = validate_package(package)
    hub = LocalHub(hub_root)
    record = hub.publish(package)
    downloaded = hub.download("demo/echo", download_root)
    card = hub.card("demo/echo")
    agent_card = hub.agent_card("demo/echo")
    config = hub.config_template("demo/echo")

    return {
        "manifest_path": manifest_path,
        "report": report,
        "record": record,
        "listed": hub.list(),
        "downloaded": downloaded,
        "card": card,
        "agent_card": agent_card,
        "config": config,
    }
