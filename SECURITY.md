# Security Policy

PsiHub loads package metadata and imports package entrypoints during validation.
Treat package archives, entrypoints, generated package cards, and config
templates as security-sensitive surfaces.

## Supported Versions

The current `main` branch and active release branch receive security fixes.

## Reporting A Vulnerability

Please report suspected vulnerabilities privately to the project maintainers.
Do not open a public issue with exploit details.

Include:

- affected version or commit
- package manifest involved
- reproduction steps
- expected and actual behavior
- whether the issue involves package loading, validation, local hub storage, or hosted registry behavior

## Scope

Security-sensitive areas include:

- `psi.toml` parsing and validation
- package-local import resolution
- package card rendering
- local publish/download storage
- future hosted package upload, storage, and build workers
