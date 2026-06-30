"""Shared parsing for PsiHub resource refs."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import unquote, urlparse


PSI_REF_SECTIONS = frozenset(
    {
        "schemas",
        "tactics",
        "services",
        "channels",
        "snapshots",
        "runs",
        "configs",
        "docs",
        "examples",
        "assets",
    }
)


@dataclass(frozen=True)
class PsiRef:
    org: str
    package: str
    resource_kind: str
    name: str


def parse_psi_ref(ref: str) -> PsiRef:
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError("Ref must be a non-empty string.")
    parsed = urlparse(ref)
    if parsed.scheme != "psi":
        raise ValueError(f"Ref must use psi:// scheme: {ref}")
    if parsed.params or parsed.query or parsed.fragment:
        raise ValueError(f"Ref must not include params, query, or fragment: {ref}")
    org = parsed.netloc
    raw_parts = parsed.path.split("/")
    if (
        len(raw_parts) != 4
        or raw_parts[0] != ""
        or any(not part for part in raw_parts[1:])
    ):
        raise ValueError(f"Ref must have shape psi://org/package/resources/name: {ref}")
    package, resource_kind, name = raw_parts[1:]
    if not org or not package.strip() or not name.strip():
        raise ValueError(f"Ref contains an empty segment: {ref}")
    for segment in (org, package, resource_kind, name):
        decoded_segment = unquote(segment)
        if any(ch.isspace() for ch in decoded_segment):
            raise ValueError(f"Ref contains a whitespace-bearing segment: {ref}")
    if resource_kind not in PSI_REF_SECTIONS:
        raise ValueError(f"Ref uses unknown resource section {resource_kind!r}: {ref}")
    for segment in (org, package, name):
        decoded_segment = unquote(segment)
        if (
            decoded_segment in {".", ".."}
            or any(ch in decoded_segment for ch in "/:\\")
            or "%" in segment
        ):
            raise ValueError(f"Ref contains an invalid segment: {ref}")
    return PsiRef(org=org, package=package, resource_kind=resource_kind, name=name)


def validate_psi_ref(ref: str) -> None:
    parse_psi_ref(ref)
