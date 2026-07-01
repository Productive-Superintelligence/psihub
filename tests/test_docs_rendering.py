import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

import pytest


ROOT = Path(__file__).resolve().parents[1]


def chromium_executable() -> str | None:
    return (
        shutil.which("chromium")
        or shutil.which("chromium-browser")
        or shutil.which("google-chrome")
    )


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
    local_hub_html = (site_dir / "guides" / "local-hub" / "index.html").read_text(
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
    custom_css = (
        site_dir / "stylesheets" / "custom.20260629.css"
    ).read_text(encoding="utf-8")
    mermaid_js = (
        site_dir / "javascripts" / "mermaid-init.20260629.js"
    ).read_text(encoding="utf-8")

    assert "PsiHub is the local-first package hub" in index_html
    assert "does not launch services" in index_html
    assert "assets/logo.svg" in index_html
    assert "assets/psihub-logo-text-dark.png#only-light" in index_html
    assert "assets/psihub-logo-text-white.png#only-dark" in index_html
    assert "psi-footer-wordmark" in index_html
    assert "serve" in cli_html
    assert "8787" in cli_html
    assert "outside the selected local hub root" in cli_html
    assert "outside <code>.psihub</code>" in local_hub_html
    assert "Symlinks are skipped" in local_hub_html
    assert "deterministic societal analysts fixture suite" in local_hub_html
    assert "does not make financial, political, cultural, or trading recommendations" in local_hub_html
    assert "Local Package Lifecycle" in lifecycle_html
    assert "agent-card" in lifecycle_html
    assert "Local Hub API" in local_hub_api_html
    assert "/packages/{org}/{name}/download" in local_hub_api_html
    assert "?version=0.2.0" in local_hub_api_html
    assert "0.10.0" in local_hub_api_html
    assert "does not launch package services" in local_hub_api_html
    assert "test_server.py" in local_hub_api_html
    assert "portable paths relative to the package" in manifest_html
    assert "regular package file rather than a symlink" in manifest_html
    assert "Absolute paths are rejected" in manifest_html
    assert "package-file" in manifest_html
    assert "paths must not contain" in manifest_html
    assert "URL schemes" in manifest_html
    assert "symlinks" in manifest_html
    assert "Custom endpoint metadata uses plain route paths" in manifest_html
    assert "empty or dot segments" in manifest_html
    assert "params" in manifest_html
    assert "network-path prefixes" in manifest_html
    assert "Downloaded Package Contracts" in refs_html
    assert "Ref segments must be non-empty path segments without whitespace" in refs_html
    assert "Resource sections must be known PSI sections" in refs_html
    assert "tactics" in refs_html
    assert "assets" in refs_html
    assert "percent" in refs_html
    assert "escapes" in refs_html
    assert "absolute HTTP(S) URLs" in refs_html
    assert "object</code> bindings" in refs_html
    assert "not serialized into" in refs_html
    assert "text targets must not contain" in refs_html
    assert "whitespace" in refs_html
    assert "store table" in refs_html
    assert "<code>path</code> values" in refs_html
    assert "must be non-empty strings without" in refs_html
    assert "preferred local service port" in refs_html
    assert "psi://demo/events/schemas/event_payload" in refs_html
    assert "psi://demo/echo/schemas/echo_output" in refs_html
    assert ".md-header," in custom_css
    assert "--md-text-font: \"Roboto\";" in custom_css
    assert "--md-code-font: \"Roboto Mono\";" in custom_css
    assert "background-color: #ffffff;" in custom_css
    assert ".psi-header-nav" in custom_css
    assert ".psi-header-nav__link" in custom_css
    assert ".psi-drawer-sections" in custom_css
    assert ".psi-drawer-sections__link" in custom_css
    assert ".psi-footer-wordmark" in custom_css
    assert 'background-image: url("../assets/psihub-logo-text-dark.png");' in custom_css
    assert ".md-typeset .mermaid svg" in custom_css
    assert "window.mermaid.startOnLoad = false" in mermaid_js
    assert "window.mermaid.render" in mermaid_js
    assert "data-mermaid-source" in mermaid_js
    assert "overflow-x: auto;" in custom_css
    assert "psi-header-nav" in index_html
    assert 'class="md-tabs"' not in index_html
    assert 'data-md-component="source"' in index_html
    assert "Productive-Superintelligence/psihub" in index_html


def test_docs_sidebar_scopes_to_active_top_nav_section(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    chromium = chromium_executable()
    if not chromium:
        pytest.skip("Chromium executable is not available")

    site_dir = build_docs(tmp_path)

    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=chromium,
            headless=True,
            args=["--no-sandbox"],
        )
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(
            (site_dir / "index.html").as_uri(), wait_until="domcontentloaded"
        )
        page.wait_for_selector(
            ".md-header__button.md-logo img, .md-header__button.md-logo svg"
        )
        metrics = page.evaluate(
            """
            () => {
              const inspect = (selector) => {
                const element = document.querySelector(selector);
                if (!element) {
                  return null;
                }
                const style = getComputedStyle(element);
                const rect = element.getBoundingClientRect();
                return {
                  backgroundColor: style.backgroundColor,
                  boxShadow: style.boxShadow,
                  color: style.color,
                  display: style.display,
                  fontFamily: style.fontFamily,
                  fontWeight: style.fontWeight,
                  height: rect.height,
                  src: element.getAttribute("src") || "",
                  width: rect.width,
                };
              };
              const brandImages = [...document.querySelectorAll(".psi-brand img")]
                .map((element) => {
                  const style = getComputedStyle(element);
                  const rect = element.getBoundingClientRect();
                  return {
                    display: style.display,
                    height: rect.height,
                    src: element.getAttribute("src") || "",
                    width: rect.width,
                  };
                });
              return {
                bodyFont: getComputedStyle(document.body)
                  .getPropertyValue("--md-text-font-family")
                  .trim(),
                codeFont: getComputedStyle(document.body)
                  .getPropertyValue("--md-code-font-family")
                  .trim(),
                footer: inspect(".md-footer-meta"),
                footerMark: inspect(".psi-footer-wordmark"),
                header: inspect(".md-header"),
                headerLogo: inspect(
                  ".md-header__button.md-logo img, .md-header__button.md-logo svg"
                ),
                headerNav: inspect(".psi-header-nav"),
                headerNavLinks: [...document.querySelectorAll(".psi-header-nav__link")]
                  .map((element) => element.textContent.trim().replace(/\\s+/g, " ")),
                sidebarText: document
                  .querySelector(".md-sidebar--primary .md-nav--primary > .md-nav__list")
                  ?.innerText.trim().replace(/\\s+/g, " ") || "",
                sourceRepository: document
                  .querySelector(".md-header__source .md-source__repository")
                  ?.textContent.trim().replace(/\\s+/g, " ") || "",
                tabs: inspect(".md-tabs"),
                title: inspect(".md-header__title"),
                brandImages,
              };
            }
            """
        )
        page.goto(
            (site_dir / "reference" / "manifest" / "index.html").as_uri(),
            wait_until="domcontentloaded",
        )
        reference_sidebar = page.locator(
            ".md-sidebar--primary .md-nav--primary > .md-nav__list"
        ).inner_text()
        page.goto(
            (site_dir / "guides" / "local-hub" / "index.html").as_uri(),
            wait_until="domcontentloaded",
        )
        guide_sidebar = page.locator(
            ".md-sidebar--primary .md-nav--primary > .md-nav__list"
        ).inner_text()
        page.close()
        browser.close()

    assert metrics["header"]["backgroundColor"] == "rgb(255, 255, 255)"
    assert metrics["tabs"] is None
    assert metrics["footer"]["backgroundColor"] == "rgb(255, 255, 255)"
    assert metrics["header"]["color"] == "rgb(5, 5, 5)"
    assert metrics["footer"]["color"] == "rgb(5, 5, 5)"
    assert metrics["header"]["boxShadow"] == "none"
    assert metrics["title"]["fontWeight"] == "700"
    assert metrics["headerLogo"]["width"] == pytest.approx(24, abs=1)
    assert metrics["headerLogo"]["height"] == pytest.approx(24, abs=1)
    assert metrics["headerNav"]["display"] == "flex"
    assert metrics["headerNavLinks"] == [
        "Overview",
        "Protocol",
        "Client",
        "Tutorials",
        "Reference",
    ]
    assert "Overview" in metrics["sidebarText"]
    assert "Getting Started" in metrics["sidebarText"]
    assert "Protocol" not in metrics["sidebarText"]
    assert "Client" not in metrics["sidebarText"]
    assert "Tutorials" not in metrics["sidebarText"]
    assert "Reference" not in metrics["sidebarText"]
    assert metrics["sourceRepository"].startswith("Productive-Superintelligence/psihub")
    assert metrics["footer"]["height"] == pytest.approx(44, abs=1)
    assert metrics["footerMark"]["width"] == pytest.approx(100, abs=2)
    assert metrics["footerMark"]["height"] == pytest.approx(27, abs=2)
    assert "Roboto" in metrics["bodyFont"]
    assert "Roboto Mono" in metrics["codeFont"]
    visible_brands = [
        image for image in metrics["brandImages"] if image["display"] == "block"
    ]
    hidden_brands = [
        image for image in metrics["brandImages"] if image["display"] == "none"
    ]
    assert len(visible_brands) == 1
    assert visible_brands[0]["src"] == "assets/psihub-logo-text-dark.png#only-light"
    assert visible_brands[0]["width"] == pytest.approx(320, abs=3)
    assert visible_brands[0]["height"] == pytest.approx(82, abs=3)
    assert any(
        image["src"] == "assets/psihub-logo-text-white.png#only-dark"
        for image in hidden_brands
    )
    assert "Manifest" in reference_sidebar
    assert "CLI" in reference_sidebar
    assert "Local Hub API" in reference_sidebar
    assert "Packages" not in reference_sidebar
    assert "Client" in guide_sidebar
    assert "Local Hub" in guide_sidebar
    assert "Cards And Agent Cards" in guide_sidebar
    assert "Manifest" not in guide_sidebar


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
