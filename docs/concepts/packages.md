# Packages

A PsiHub package is a normal folder with a `psi.toml` manifest. The manifest
declares package metadata and typed resources:

- schemas,
- tactics,
- services,
- channels,
- snapshots,
- configs,
- docs,
- examples,
- assets,
- runs.

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

[requirements.api_keys]
OPENAI_API_KEY = "OpenAI-compatible model access."

[runs.local]
services = ["api"]

[card]
summary = "Echo tactic package."
tags = ["demo", "tactic"]
suggested_commands = ["uvicorn demo.app:create_app --reload"]

[docs.readme]
path = "README.md"
title = "README"
```

## Primary Resource

Focused packages should declare a matching primary resource:

```toml
[package]
org = "demo"
name = "echo"
kind = "tactic"
primary = "tactics.echo"
```

Tactic packages point at `tactics.*`; channel packages point at `channels.*`;
service packages point at `services.*`; app packages typically point at
`services.*` or `runs.*`.

The primary resource helps cards, agent cards, and future runners present the
package without scanning every manifest table.

## Resource Refs

Every declared resource can be addressed with a stable ref:

```text
psi://demo/echo/tactics/echo
psi://demo/echo/services/api
psi://demo/echo/docs/readme
```

Refs are package contracts. Concrete local URLs, store paths, and service
ports belong in `.psi/config.toml`, not in the package manifest unless they are
passive metadata or defaults.

## Validation Boundary

PsiHub validates the shape. It does not import or run the whole system.

Validation catches malformed refs, missing same-package resources, invalid
entrypoints, unbound services, duplicate package records, unsafe package-file
paths, and run metadata that names missing resources. It also warns when cards
or README metadata are missing so draft packages remain flexible while still
nudging authors toward discoverable packages.

## What Makes A Package Useful

Good packages include:

- a small README,
- `card` metadata with summary and tags,
- examples with concrete commands or inputs,
- clear schema/tactic/channel/service descriptions,
- endpoint metadata for custom service routes,
- config defaults that are safe to share,
- suggested commands that humans can run locally.

Do not store raw secrets in metadata. Use local credential refs such as
`api_key_ref`, `apiKeyRef`, or `apikeyref`.

Declare launch-time provider keys as public requirements instead:

```toml
[requirements.api_keys]
OPENAI_API_KEY = "OpenAI-compatible model access."
ANTHROPIC_API_KEY = "Claude model access."
```

`psi init` and `psi launch` use these names to guide local setup while keeping
secret values in the user's process environment, OS keyring, or local env file.
