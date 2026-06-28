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

[runs.local]
services = ["api"]

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

## Local Lifecycle

```bash
psihub init . --org demo --name echo --kind tactic
psihub validate .
psihub publish . --local
psihub list
psihub get demo/echo --dest ./downloaded
psihub card demo/echo
psihub config-template demo/echo
```

Local hub storage defaults to:

```text
.psihub/
  packages/
  index/
```

Use `--hub` to point commands at another local hub directory.
