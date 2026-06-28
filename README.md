# PsiHub

PsiHub is the local-first package hub for PSI packages.

It owns the package protocol: `psi.toml`, validation, local publish/download,
package cards, and local config templates. It does not launch services.

## Package Shape

```toml
[package]
psi_version = "0.1"
org = "demo"
name = "echo"
version = "0.1.0"
kind = "tactic"
primary = "tactics.echo"

[schemas.echo_input]
entry = "demo.schemas:EchoInput"

[schemas.echo_output]
entry = "demo.schemas:EchoOutput"

[tactics.echo]
entry = "demo.tactics:EchoTactic"
input = "echo_input"
output = "echo_output"

[services.api]
tactic = "echo"
transport = "fastapi"

[snapshots.latest]
schema = "echo_output"
description = "Latest echo result."

[runs.local]
services = ["api"]
snapshots = ["latest"]

[card]
summary = "Echo tactic package."
tags = ["demo"]
suggested_commands = ["uvicorn demo.app:create_app --reload"]

[docs.readme]
path = "README.md"
title = "README"

[config.defaults]
policy_url = "http://127.0.0.1:8000"
```

Focused package kinds should declare a matching `package.primary`: tactic
packages point at `tactics.*`, channel packages at `channels.*`, service
packages at `services.*`, and app packages at `services.*` or `runs.*`.

## Local Lifecycle

```bash
psihub init . --org demo --name echo --kind tactic
psihub validate .
psihub publish . --local
psihub list
psihub get demo/echo --dest ./downloaded
psihub card demo/echo
psihub agent-card demo/echo
psihub config-template demo/echo
```

Local publish validates by default and rejects packages with validation errors.
Use `psihub publish --local --no-validate` only when intentionally indexing an
incomplete local package.

Package and agent cards render declared endpoint metadata so custom service
routes are visible without opening source files.

Validation accepts well-formed external `psi://.../schemas/name` refs, rejects
malformed schema refs, and catches same-package schema refs that point at
missing declared schemas.
Local `.psi/config.toml` binding keys are also validated as strict
`psi://org/package/resources/name` refs.

Local hub storage defaults to:

```text
.psihub/
  packages/
  index/
```

Generated config templates assign multiple service refs distinct default local
ports in manifest order. Tactic refs point at the local port for the service
that declares the tactic, falling back to port 8000 when no service declares it.
Templates also include passive `[services.*]` port tables and `[stores.*]` path
tables for humans or future runners to inspect without asking PsiHub to launch
anything.
Snapshot resources render as `psi://.../snapshots/name` refs and bind to the
same local store path convention as channels.
Config defaults render under `[settings]`; `LocalConfigResolver.settings()`
and `setting(name, default)` expose those local values alongside ref bindings,
`services()/service(name)`, and `stores()/store(name)`.

Use `--hub` to point commands at another local hub directory.
