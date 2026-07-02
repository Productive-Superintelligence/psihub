# Manifest

`psi.toml` is the package protocol owned by PsiHub.
The manifest file itself must be a regular package file rather than a symlink.

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
tactics = ["echo"]
transport = "fastapi"

[requirements.api_keys]
OPENAI_API_KEY = "OpenAI-compatible model access."
ANTHROPIC_API_KEY = "Claude model access."

[runs.local]
services = ["api"]

[card]
summary = "Echo tactic package."
tags = ["demo", "tactic"]
suggested_commands = ["uvicorn demo.app:create_app --reload"]

[docs.readme]
path = "README.md"
title = "README"

[config.defaults]
policy_url = "http://127.0.0.1:8000"
```

Doc, example, and asset resources use portable paths relative to the package
root. Absolute paths are rejected during validation, and portable package-file
paths must not contain whitespace, percent escapes, URL schemes, network-path
prefixes, backslashes, colon separators, or symlinks.

Validation catches malformed refs, missing same-package resources, invalid
entrypoints, unbound services, duplicate package records, and run metadata that
names missing resources.
Same-package references such as `service.tactic`, `service.tactics`,
`service.subscribes`, `snapshot.channel`, and `runs.*` resource lists must use
local resource names that are non-empty path segments without whitespace,
percent escapes, path separators, or semicolon params.

Custom endpoint metadata uses plain route paths, names, and tags. Route paths
must be `/`-prefixed and avoid empty or dot segments, backslashes, colons, path
params, queries, fragments, URLs, network-path prefixes, whitespace, and
percent escapes.

Use `service.tactic` for the primary tactic exposed by a service. Use
`service.tactics` when one service exposes multiple same-package tactics; config
templates will bind each listed tactic ref to that service's local port.

## Required API Keys

Use `[requirements.api_keys]` for credentials a package needs at launch time.
Keys are conventional environment variable names and values are short public
descriptions:

```toml
[requirements.api_keys]
OPENAI_API_KEY = "OpenAI-compatible model access."
TOGETHER_API_KEY = "Together AI fallback model access."
```

Resource metadata can narrow the same idea to a specific resource:

```toml
[tactics.analyze.metadata.required_api_keys]
ANTHROPIC_API_KEY = "Claude model access for analysis."
```

Manifests never store raw secret values. The `psi` CLI checks these names before
launch, then reads values from the process environment, OS keyring, or a local
env file configured by `psi init`.
