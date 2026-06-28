"""Package card and config-template rendering."""

from __future__ import annotations

from .models import PackageRecord


def render_package_card(record: PackageRecord) -> str:
    lines = [
        f"# {record.identifier}",
        "",
        record.description or f"Psi package `{record.identifier}`.",
        "",
        f"- Version: `{record.version}`",
        f"- Kind: `{record.kind}`",
        f"- Validation: `{'ok' if record.validation.ok else 'failed'}`",
        "",
        "## Resources",
        "",
    ]
    if not record.resources:
        lines.append("No resources declared.")
    for resource in record.resources:
        lines.append(f"- `{resource.ref}` ({resource.kind})")
    lines.extend(["", "## Local Config Template", "", "```toml"])
    lines.append(render_config_template(record).rstrip())
    lines.extend(["```", ""])
    return "\n".join(lines).rstrip() + "\n"


def render_config_template(record: PackageRecord) -> str:
    lines: list[str] = []
    for resource in record.resources:
        if resource.kind == "service":
            lines.extend(
                [
                    f"[refs.\"{resource.ref}\"]",
                    'url = "http://127.0.0.1:8000"',
                    "",
                ]
            )
        if resource.kind == "tactic":
            lines.extend(
                [
                    f"[refs.\"{resource.ref}\"]",
                    'url = "http://127.0.0.1:8000/tactics/'
                    f'{resource.name}"',
                    "",
                ]
            )
        if resource.kind == "channel":
            lines.extend(
                [
                    f"[refs.\"{resource.ref}\"]",
                    'store = ".sssn"',
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + ("\n" if lines else "")
