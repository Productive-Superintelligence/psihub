# Local Package Lifecycle

Create, validate, publish, inspect, and download a local Psi package without a
hosted hub.

Goal: create a minimal local package, put it in the fake local hub, inspect the
generated cards and config template, and download it into a clean folder.

The same flow is available as an executable example at
`examples/local_package_lifecycle/workflow.py`.

## Prerequisites

```bash
python -m pip install -e ".[dev]"
```

## Files Used

This walkthrough creates:

- `demo-package/psi.toml`: package manifest created by `psihub init`.
- `demo-package/README.md`: source-facing package README.
- `.psihub/`: deterministic local hub storage.
- `downloaded/echo/`: downloaded copy of the published package.

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

Expected output:

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

## Verify

```bash
test -f ../downloaded/echo/psi.toml
```

Expected output:

```text
exit code 0 with no output
```

Next, add schemas, tactics, channels, services, examples, and run metadata to
the package manifest.
