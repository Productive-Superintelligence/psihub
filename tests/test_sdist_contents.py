import subprocess
import sys
import tarfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_sdist_includes_repo_materials(tmp_path):
    pytest.importorskip("build")
    dist_dir = tmp_path / "dist"
    result = subprocess.run(
        [sys.executable, "-m", "build", "--sdist", "--outdir", str(dist_dir)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    archives = list(dist_dir.glob("*.tar.gz"))
    assert len(archives) == 1
    root = archives[0].name.removesuffix(".tar.gz")
    with tarfile.open(archives[0]) as archive:
        names = set(archive.getnames())

    required = [
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "assets/psihub-logo-text-dark.png",
        "assets/psihub-logo-text-white.png",
        "mkdocs.yml",
        "psihub/__init__.py",
        "psihub/endpoints.py",
        "psihub/entrypoints.py",
        "psihub/files.py",
        "psihub/py.typed",
        "psihub/refs.py",
        "psihub/server.py",
        "docs/index.md",
        "docs/assets/logo.svg",
        "docs/assets/psihub-logo-text-dark.png",
        "docs/assets/psihub-logo-text-white.png",
        "docs/client/index.md",
        "docs/javascripts/mermaid-init.20260629.js",
        "docs/javascripts/vendor/mermaid.min.js",
        "docs/javascripts/vendor/mermaid-LICENSE.txt",
        "docs/protocol/index.md",
        "docs/stylesheets/custom.20260629.css",
        "docs/tutorials/local-package-lifecycle.md",
        "examples/local_package_lifecycle/README.md",
        "examples/local_package_lifecycle/workflow.py",
    ]
    missing = [path for path in required if f"{root}/{path}" not in names]

    assert not missing
    assert not any(name.startswith(f"{root}/site/") for name in names)
