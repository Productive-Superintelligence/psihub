import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

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
    cli_html = (site_dir / "reference" / "cli" / "index.html").read_text(
        encoding="utf-8"
    )
    lifecycle_html = (
        site_dir / "tutorials" / "local-package-lifecycle" / "index.html"
    ).read_text(encoding="utf-8")
    local_hub_api_html = (
        site_dir / "reference" / "local-hub-api" / "index.html"
    ).read_text(encoding="utf-8")
    manifest_html = (site_dir / "reference" / "manifest" / "index.html").read_text(
        encoding="utf-8"
    )
    refs_html = (
        site_dir / "concepts" / "refs-and-config" / "index.html"
    ).read_text(encoding="utf-8")
    custom_css = (site_dir / "stylesheets" / "custom.css").read_text(
        encoding="utf-8"
    )

    assert "PsiHub is the local-first package hub" in index_html
    assert "does not launch services" in index_html
    assert "assets/logo.svg" in index_html
    assert "serve" in cli_html
    assert "8787" in cli_html
    assert "Local Package Lifecycle" in lifecycle_html
    assert "agent-card" in lifecycle_html
    assert "Local Hub API" in local_hub_api_html
    assert "/packages/{org}/{name}/download" in local_hub_api_html
    assert "?version=0.2.0" in local_hub_api_html
    assert "0.10.0" in local_hub_api_html
    assert "does not launch package services" in local_hub_api_html
    assert "test_server.py" in local_hub_api_html
    assert "Custom endpoint metadata uses plain route paths" in manifest_html
    assert "percent escapes in those fields" in manifest_html
    assert "Downloaded Package Contracts" in refs_html
    assert "Ref segments must be non-empty path segments without whitespace" in refs_html
    assert "percent" in refs_html
    assert "escapes" in refs_html
    assert "absolute HTTP(S) URLs" in refs_html
    assert "text targets must not contain" in refs_html
    assert "whitespace" in refs_html
    assert "preferred local service port" in refs_html
    assert "psi://demo/events/schemas/event_payload" in refs_html
    assert "psi://demo/echo/schemas/echo_output" in refs_html
    assert ".md-header," in custom_css
    assert "background-color: #ffffff;" in custom_css


def test_cli_reference_lists_local_lifecycle_commands():
    reference = (ROOT / "docs" / "reference" / "cli.md").read_text(
        encoding="utf-8"
    )
    expected = [
        "psihub init PATH --org ORG --name NAME --kind KIND",
        "psihub validate PATH",
        "psihub --hub .psihub publish PATH --local",
        "psihub --hub .psihub list",
        "psihub --hub .psihub card ORG/NAME",
        "psihub --hub .psihub agent-card ORG/NAME",
        "psihub --hub .psihub config-template ORG/NAME",
        "psihub --hub .psihub get ORG/NAME --dest downloaded",
        "psihub --hub .psihub serve --host 127.0.0.1 --port 8787",
    ]

    for command in expected:
        assert command in reference


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


def test_documented_example_paths_exist():
    pattern = re.compile(r"`(examples/[^`]+)`")
    text_paths = [ROOT / "README.md"]
    text_paths.extend((ROOT / "docs").rglob("*.md"))

    missing = []
    for path in sorted(text_paths):
        for match in pattern.finditer(path.read_text(encoding="utf-8")):
            example_path = ROOT / match.group(1)
            if not example_path.exists():
                missing.append(f"{path.relative_to(ROOT)} -> {match.group(1)}")

    assert missing == []


def test_public_text_does_not_use_workspace_names():
    text_paths = [ROOT / "README.md"]
    text_paths.extend((ROOT / "docs").rglob("*.md"))
    text_paths.extend(
        path
        for path in (ROOT / "examples").rglob("*")
        if path.suffix in {".md", ".py", ".toml", ".yaml", ".yml"}
    )

    for path in text_paths:
        text = path.read_text(encoding="utf-8")
        assert "LLLM v2" not in text, path
        assert "lllmv2" not in text, path
        assert "SSSN v2" not in text, path
        assert "sssnv2" not in text, path


def test_readme_and_docs_local_links_resolve():
    pattern = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
    text_paths = [ROOT / "README.md"]
    text_paths.extend((ROOT / "docs").rglob("*.md"))
    skip_prefixes = ("http://", "https://", "mailto:", "#")

    missing = []
    for path in sorted(text_paths):
        for match in pattern.finditer(path.read_text(encoding="utf-8")):
            target = match.group(1).strip()
            if not target or target.startswith(skip_prefixes) or "://" in target:
                continue
            target = target.split("#", 1)[0].split("?", 1)[0]
            if not target:
                continue
            if not (path.parent / unquote(target)).resolve().exists():
                missing.append(f"{path.relative_to(ROOT)} -> {match.group(1)}")

    assert missing == []


def test_docs_local_asset_references_resolve():
    patterns = [
        re.compile(r'\bsrc="([^"]+)"'),
        re.compile(r"url\([\"']?([^\"')]+)[\"']?\)"),
        re.compile(r"!\[[^\]]*\]\(([^)]+)\)"),
    ]
    text_paths = [ROOT / "README.md"]
    text_paths.extend((ROOT / "docs").rglob("*.md"))
    text_paths.extend((ROOT / "docs" / "stylesheets").glob("*.css"))
    skip_prefixes = ("http://", "https://", "mailto:", "data:", "#")

    missing = []
    for path in sorted(text_paths):
        text = path.read_text(encoding="utf-8")
        for pattern in patterns:
            for match in pattern.finditer(text):
                target = match.group(1).strip()
                if (
                    not target
                    or target.startswith(skip_prefixes)
                    or "://" in target
                ):
                    continue
                target = target.split("#", 1)[0].split("?", 1)[0]
                if not target:
                    continue
                if not (path.parent / unquote(target)).resolve().exists():
                    missing.append(
                        f"{path.relative_to(ROOT)} -> {match.group(1)}"
                    )

    assert missing == []
