"""Package card and config-template rendering."""

from __future__ import annotations

import json
import re
from typing import Any

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
                ]
            )
            lines.extend(_metadata_lines(resource.metadata))
            lines.append("")
        if resource.kind == "tactic":
            lines.extend(
                [
                    f"[refs.\"{resource.ref}\"]",
                    'url = "http://127.0.0.1:8000/tactics/'
                    f'{resource.name}"',
                ]
            )
            lines.extend(_metadata_lines(resource.metadata))
            lines.append("")
        if resource.kind == "channel":
            lines.extend(
                [
                    f"[refs.\"{resource.ref}\"]",
                    'store = ".sssn"',
                ]
            )
            lines.extend(_metadata_lines(resource.metadata))
            lines.append("")
    return "\n".join(lines).rstrip() + ("\n" if lines else "")


def _metadata_lines(metadata: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for key, value in sorted(metadata.items()):
        if key in {"url", "store", "path"} or value in (None, "", [], {}):
            continue
        rendered = _toml_value(value)
        if rendered is not None:
            lines.append(f"{_toml_key(key)} = {rendered}")
    return lines


def _toml_key(key: str) -> str:
    if re.match(r"^[A-Za-z_][A-Za-z0-9_-]*$", key):
        return key
    return json.dumps(key)


def _toml_value(value: Any) -> str | None:
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, (list, tuple)):
        rendered = [_toml_value(item) for item in value]
        if any(item is None for item in rendered):
            return None
        return "[" + ", ".join(rendered_item for rendered_item in rendered if rendered_item) + "]"
    return None
