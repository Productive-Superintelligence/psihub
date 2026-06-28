# Local Package Lifecycle

Create, validate, publish, inspect, and download a local Psi package without a
hosted hub.

## Prerequisites

```bash
python -m pip install -e ".[dev]"
```

## Initialize A Package

```bash
mkdir demo-package
cd demo-package
psihub init . --org demo --name echo --kind tactic
```

This creates `psi.toml` and a starter `README.md`.

## Validate

```bash
psihub validate .
```

Expected output includes:

```text
ok
```

## Publish Locally

```bash
psihub --hub ../.psihub publish . --local
```

Local hub storage is deterministic:

```text
.psihub/
  packages/
  index/
```

## Inspect

```bash
psihub --hub ../.psihub list
psihub --hub ../.psihub card demo/echo
psihub --hub ../.psihub agent-card demo/echo
psihub --hub ../.psihub config-template demo/echo
```

Cards describe refs and config. PsiHub does not launch services.

## Download

```bash
psihub --hub ../.psihub get demo/echo --dest ../downloaded
```

Verify:

```bash
test -f ../downloaded/echo/psi.toml
```

Next, add schemas, tactics, channels, services, examples, and run metadata to
the package manifest.
