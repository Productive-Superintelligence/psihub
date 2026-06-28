"""Shared parsing for PsiHub resource refs."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


PSI_REF_SECTIONS = {
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


@dataclass(frozen=True)
class PsiRef:
    org: str
    package: str
    resource_kind: str
    name: str


def parse_psi_ref(ref: str) -> PsiRef:
    parsed = urlparse(ref)
    if parsed.scheme != "psi":
        raise ValueError(f"Ref must use psi:// scheme: {ref}")
    if parsed.params or parsed.query or parsed.fragment:
        raise ValueError(f"Ref must not include params, query, or fragment: {ref}")
    org = parsed.netloc.strip()
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 3:
        raise ValueError(f"Ref must have shape psi://org/package/resources/name: {ref}")
    package, resource_kind, name = parts
    if not org or not package or not name:
        raise ValueError(f"Ref contains an empty segment: {ref}")
    if resource_kind not in PSI_REF_SECTIONS:
        raise ValueError(f"Ref uses unknown resource section {resource_kind!r}: {ref}")
    for segment in (org, package, name):
        if segment in {".", ".."} or any(ch in segment for ch in ":\\"):
            raise ValueError(f"Ref contains an invalid segment: {ref}")
    return PsiRef(org=org, package=package, resource_kind=resource_kind, name=name)


def validate_psi_ref(ref: str) -> None:
    parse_psi_ref(ref)
