"""Package card and config-template rendering."""

from __future__ import annotations

import json
import re
from typing import Any

from .models import PackageRecord
from .validator import HTTP_METHODS


def render_agent_card(record: PackageRecord) -> str:
    """Render concise package instructions for coding agents."""

    card = record.card
    summary = (
        card.summary
        if card is not None and card.summary
        else record.description
        or f"Psi package `{record.identifier}`."
    )
    lines = [
        f"# Agent Card: {record.identifier}",
        "",
        summary,
        "",
        "## Operating Notes",
        "",
        "- PsiHub describes packages, refs, config, and metadata; it does not launch services.",
        "- Resolve required services/channels through local `.psi/config.toml` bindings.",
        "- Prefer declared refs and resource metadata over guessing paths or URLs.",
        "",
    ]
    if card is not None:
        if card.safety:
            lines.append(f"- Safety: {card.safety}")
        if card.latency:
            lines.append(f"- Latency: {card.latency}")
        if card.tags:
            lines.append(f"- Tags: {', '.join(card.tags)}")
        if card.suggested_commands:
            lines.extend(["", "## Suggested Commands", ""])
            for command in card.suggested_commands:
                lines.append(f"- `{command}`")
            lines.append("")
    lines.extend(["## Resources", ""])
    if not record.resources:
        lines.append("No resources declared.")
    for resource in record.resources:
        lines.append(f"- {resource.kind} `{resource.name}`: `{resource.ref}`")
        if resource.entry:
            lines.append(f"  - entry/path: `{resource.entry}`")
        if resource.description:
            lines.append(f"  - {resource.description}")
        metadata = _metadata_summary(resource.metadata)
        if metadata:
            lines.append(f"  - Metadata: {metadata}")
        lines.extend(_endpoint_lines(resource.metadata))
        lines.extend(_example_lines(resource.metadata))
    template = render_config_template(record).rstrip()
    if template:
        lines.extend(["", "## Config Template", "", "```toml", template, "```"])
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_package_card(record: PackageRecord) -> str:
    summary = (
        record.card.summary
        if record.card is not None and record.card.summary
        else record.description
    )
    lines = [
        f"# {record.identifier}",
        "",
        summary or f"Psi package `{record.identifier}`.",
        "",
        f"- Version: `{record.version}`",
        f"- Kind: `{record.kind}`",
        f"- Validation: `{'ok' if record.validation.ok else 'failed'}`",
        "",
    ]
    lines.extend(_card_metadata_lines(record))
    lines.extend([
        "## Resources",
        "",
    ])
    if not record.resources:
        lines.append("No resources declared.")
    for resource in record.resources:
        lines.append(f"- `{resource.ref}` ({resource.kind})")
        if resource.description:
            lines.append(f"  - {resource.description}")
        metadata = _metadata_summary(resource.metadata)
        if metadata:
            lines.append(f"  - Metadata: {metadata}")
        lines.extend(_endpoint_lines(resource.metadata))
        lines.extend(_example_lines(resource.metadata))
        if resource.kind == "config":
            defaults = _mapping_summary(resource.metadata.get("defaults"))
            if defaults:
                lines.append(f"  - Defaults: {defaults}")
    lines.extend(["", "## Local Config Template", "", "```toml"])
    lines.append(render_config_template(record).rstrip())
    lines.extend(["```", ""])
    return "\n".join(lines).rstrip() + "\n"


def render_config_template(record: PackageRecord) -> str:
    lines: list[str] = []
    settings = _settings_lines(record)
    if settings:
        lines.extend(settings)
        lines.append("")
    resources = tuple(record.resources)
    service_ports = _service_ports(resources)
    tactic_ports = _tactic_ports(resources, service_ports)
    service_settings = _service_settings_lines(service_ports)
    if service_settings:
        lines.extend(service_settings)
        lines.append("")
    store_settings = _store_settings_lines(resources)
    if store_settings:
        lines.extend(store_settings)
        lines.append("")
    for resource in record.resources:
        if resource.kind == "service":
            lines.extend(
                [
                    f"[refs.\"{resource.ref}\"]",
                    f'url = "http://127.0.0.1:{service_ports[resource.name]}"',
                ]
            )
            lines.extend(_metadata_lines(resource.metadata))
            lines.append("")
        if resource.kind == "tactic":
            tactic_port = tactic_ports.get(resource.name, 8000)
            lines.extend(
                [
                    f"[refs.\"{resource.ref}\"]",
                    f'url = "http://127.0.0.1:{tactic_port}/tactics/'
                    f'{resource.name}"',
                ]
            )
            lines.extend(_metadata_lines(resource.metadata))
            lines.append("")
        if resource.kind in {"channel", "snapshot"}:
            lines.extend(
                [
                    f"[refs.\"{resource.ref}\"]",
                    'store = ".sssn"',
                ]
            )
            lines.extend(_metadata_lines(resource.metadata))
            lines.append("")
    return "\n".join(lines).rstrip() + ("\n" if lines else "")


def _service_settings_lines(service_ports: dict[str, int]) -> list[str]:
    lines: list[str] = []
    for name, port in service_ports.items():
        lines.extend([f"[services.{_toml_key(name)}]", f"port = {port}", ""])
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def _store_settings_lines(resources: tuple[Any, ...]) -> list[str]:
    if not any(resource.kind in {"channel", "snapshot"} for resource in resources):
        return []
    return ["[stores.default]", 'path = ".sssn"']


def _service_ports(resources: tuple[Any, ...]) -> dict[str, int]:
    ports: dict[str, int] = {}
    used: set[int] = set()
    next_port = 8000
    for resource in resources:
        if resource.kind != "service":
            continue
        port = _preferred_service_port(resource)
        if port is None or port in used:
            while next_port in used:
                next_port += 1
            port = next_port
        ports[resource.name] = port
        used.add(port)
        next_port += 1
    return ports


def _preferred_service_port(resource: Any) -> int | None:
    port = resource.metadata.get("port")
    if isinstance(port, bool) or not isinstance(port, int):
        return None
    if not (1 <= port <= 65535):
        return None
    return port


def _tactic_ports(
    resources: tuple[Any, ...], service_ports: dict[str, int]
) -> dict[str, int]:
    ports: dict[str, int] = {}
    for resource in resources:
        if resource.kind != "service":
            continue
        tactic = resource.metadata.get("tactic")
        if isinstance(tactic, str) and tactic:
            ports.setdefault(tactic, service_ports[resource.name])
    return ports


def _card_metadata_lines(record: PackageRecord) -> list[str]:
    card = record.card
    if card is None:
        return []
    lines: list[str] = []
    if card.tags:
        lines.append(f"- Tags: {', '.join(f'`{tag}`' for tag in card.tags)}")
    if card.safety:
        lines.append(f"- Safety: {card.safety}")
    if card.latency:
        lines.append(f"- Latency: {card.latency}")
    if card.suggested_commands:
        lines.extend(["", "## Suggested Commands", ""])
        for command in card.suggested_commands:
            lines.append(f"- `{command}`")
    if lines and lines[-1] != "":
        lines.append("")
    return lines


def _settings_lines(record: PackageRecord) -> list[str]:
    settings: list[str] = []
    for resource in record.resources:
        if resource.kind != "config":
            continue
        defaults = resource.metadata.get("defaults")
        if not isinstance(defaults, dict):
            continue
        rendered = [
            f"{_toml_key(key)} = {value}"
            for key, value in (
                (key, _toml_value(value)) for key, value in sorted(defaults.items())
            )
            if value is not None
        ]
        if rendered:
            if not settings:
                settings.append("[settings]")
            settings.extend(rendered)
    return settings


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


def _metadata_summary(metadata: dict[str, Any]) -> str:
    parts: list[str] = []
    for key, value in sorted(metadata.items()):
        if key in {"defaults", "endpoints", "examples", "schema"}:
            continue
        rendered = _toml_value(value)
        if rendered is not None:
            parts.append(f"`{key}={rendered}`")
    return ", ".join(parts)


def _endpoint_lines(metadata: dict[str, Any]) -> list[str]:
    endpoints = metadata.get("endpoints")
    if not isinstance(endpoints, list):
        return []
    lines: list[str] = []
    for endpoint in endpoints:
        if not isinstance(endpoint, dict):
            continue
        rendered = _endpoint_line(endpoint)
        if rendered is None:
            continue
        lines.append(rendered)
    return lines


def _endpoint_line(endpoint: dict[str, Any]) -> str | None:
    method_value = endpoint.get("method")
    method = method_value.upper() if isinstance(method_value, str) else ""
    path = endpoint.get("path")
    if (
        method not in HTTP_METHODS
        or not isinstance(path, str)
        or not path
        or "%" in path
        or any(ch.isspace() for ch in path)
    ):
        return None
    suffix_parts: list[str] = []
    for value in (endpoint.get("name"), endpoint.get("mode") or endpoint.get("scope")):
        if value in (None, ""):
            continue
        if not isinstance(value, str) or any(ch.isspace() for ch in value):
            return None
        suffix_parts.append(value)
    suffix = f" ({', '.join(suffix_parts)})" if suffix_parts else ""
    return f"  - Endpoint: `{method} {path}`{suffix}"


def _example_lines(metadata: dict[str, Any]) -> list[str]:
    examples = metadata.get("examples")
    if not isinstance(examples, list):
        return []
    lines: list[str] = []
    for example in examples:
        if not isinstance(example, dict):
            continue
        description = _example_description(example)
        if description is None:
            continue
        parts: list[str] = []
        if "input" in example:
            rendered = _json_inline(example["input"])
            if rendered is not None:
                parts.append(f"`input={rendered}`")
        if "output" in example:
            rendered = _json_inline(example["output"])
            if rendered is not None:
                parts.append(f"`output={rendered}`")
        if "command" in example:
            rendered = _json_inline(example["command"])
            if rendered is not None:
                parts.append(f"`command={rendered}`")
        if not parts:
            continue
        if description and description.endswith((".", "!", "?", ":")):
            prefix = f"{description} "
        else:
            prefix = f"{description}: " if description else ""
        lines.append(f"  - Example: {prefix}{' -> '.join(parts)}")
    return lines


def _example_description(example: dict[str, Any]) -> str | None:
    value = example.get("description")
    if value in (None, ""):
        value = example.get("name")
    if value in (None, ""):
        return ""
    if not isinstance(value, str):
        return None
    return value.strip()


def _json_inline(value: Any) -> str | None:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    except TypeError:
        return None


def _mapping_summary(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    parts: list[str] = []
    for key, item in sorted(value.items()):
        rendered = _toml_value(item)
        if rendered is not None:
            parts.append(f"`{key}={rendered}`")
    return ", ".join(parts)
