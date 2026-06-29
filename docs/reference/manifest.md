# Manifest

`psi.toml` is the package protocol owned by PsiHub.

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
prefixes, backslashes, or colon separators.

Validation catches malformed refs, missing same-package resources, invalid
entrypoints, unbound services, duplicate package records, and run metadata that
names missing resources.

Custom endpoint metadata uses plain route paths, names, and tags; avoid
whitespace and percent escapes in those fields, and do not use `//`
network-path prefixes for route paths.
