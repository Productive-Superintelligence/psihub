import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def build_docs(tmp_path: Path) -> Path:
    pytest.importorskip("mkdocs")
    site_dir = tmp_path / "site"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mkdocs",
            "build",
            "--strict",
            "--site-dir",
            str(site_dir),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    return site_dir


def test_docs_site_builds_core_pages(tmp_path):
    site_dir = build_docs(tmp_path)
    index_html = (site_dir / "index.html").read_text(encoding="utf-8")
    lifecycle_html = (
        site_dir / "tutorials" / "local-package-lifecycle" / "index.html"
    ).read_text(encoding="utf-8")
    local_hub_api_html = (
        site_dir / "reference" / "local-hub-api" / "index.html"
    ).read_text(encoding="utf-8")
    custom_css = (site_dir / "stylesheets" / "custom.css").read_text(
        encoding="utf-8"
    )

    assert "PsiHub is the local-first package hub" in index_html
    assert "does not launch services" in index_html
    assert "Local Package Lifecycle" in lifecycle_html
    assert "agent-card" in lifecycle_html
    assert "Local Hub API" in local_hub_api_html
    assert "/packages/{org}/{name}/download" in local_hub_api_html
    assert "does not launch package services" in local_hub_api_html
    assert "test_server.py" in local_hub_api_html
    assert ".md-header," in custom_css
    assert "background-color: #ffffff;" in custom_css


def test_tutorials_keep_step_by_step_shape():
    required = [
        "Goal:",
        "## Prerequisites",
        "## Files Used",
        "## Verify",
        "Expected output:",
        "Next,",
    ]

    for path in sorted((ROOT / "docs" / "tutorials").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        for marker in required:
            assert marker in text, f"{path.relative_to(ROOT)} missing {marker}"
