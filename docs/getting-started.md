# Getting Started

This guide creates a package, validates it, publishes it into a local hub,
renders cards, and downloads a clean copy.

## Install

Install the alpha from PyPI:

```bash
python -m pip install --pre psihub
```

Install PsiHub in editable mode while developing:

```bash
python -m pip install -e ".[dev,docs]"
```

## Create A Starter Package

```bash
psihub init demo-package --org demo --name echo --kind tactic
```

This creates a normal package folder with `psi.toml` and starter docs. The
manifest is the package contract; the folder remains ordinary source that
humans and coding agents can inspect.

## Validate

```bash
psihub validate demo-package
```

Validation checks package identity, refs, entrypoints, endpoint metadata,
package-file paths, run metadata, card metadata, config defaults, and resource
names. Draft packages can still produce warnings, but validation errors block
local publish by default.

## Publish Locally

```bash
psihub --hub .psihub publish demo-package --local
```

Local hub storage is deterministic:

```text
.psihub/
  packages/
  index/
```

Publish copies package source into the hub while skipping local-only
secret/config/cache material and symlinks.

## Inspect

```bash
psihub --hub .psihub list
psihub --hub .psihub card demo/echo
psihub --hub .psihub agent-card demo/echo
psihub --hub .psihub config-template demo/echo
```

Cards summarize package identity, resources, refs, examples, endpoint
metadata, and suggested commands. Agent cards compress the same information
for coding agents. Config templates describe passive local bindings for
services, stores, settings, channels, snapshots, and tactics.

## Download

```bash
psihub --hub .psihub get demo/echo --dest downloaded
```

The downloaded package remains a folder with `psi.toml`, docs, examples, and
source files. Coding agents can inspect it directly. Choose a destination
outside `.psihub` so downloads never overwrite hub storage.

Continue with [Packages](concepts/packages.md) for manifest shape and
[Local Hub](guides/local-hub.md) for storage boundaries.
