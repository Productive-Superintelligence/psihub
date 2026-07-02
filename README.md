# PsiHub

<p align="center">
  <img src="assets/psihub-logo-text-dark.png" alt="PsiHub" width="420">
</p>

PsiHub is the local-first Python package hub for PSI packages.

It owns the package protocol: `psi.toml`, validation, local publish/download,
package cards, local config templates, and optional local hub APIs. It does not
launch services.
`psi.toml` must be a regular package file rather than a symlink.

## Install

```bash
python -m pip install psihub
```

For a reproducible install:

```bash
python -m pip install psihub==0.0.2
```

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
tactics = ["echo"]
transport = "fastapi"

[requirements.api_keys]
OPENAI_API_KEY = "OpenAI-compatible model access."

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

## Python Lifecycle

```python
from psihub import LocalHub, init_package, validate_package

init_package(".", org="demo", name="echo", kind="tactic")

report = validate_package(".")
if not report.ok:
    for issue in report.issues:
        print(issue.level, issue.code, issue.message)

hub = LocalHub(".psihub")
record = hub.publish(".")
downloaded = hub.download("demo/echo", "./downloaded")
package_card = hub.card("demo/echo")
agent_card = hub.agent_card("demo/echo")
config = hub.config_template("demo/echo")
```

For a step-by-step local package walkthrough, see
`docs/tutorials/local-package-lifecycle.md`.

The `psihub` console command is a developer convenience over the Python API.
The unified user CLI for local launch and credential setup is `psi`.

Local publish validates by default and rejects packages with validation errors.
Use `hub.publish(path, validate=False)` only when intentionally indexing an
incomplete local package.

Package and agent cards render declared endpoint and tactic example metadata so
custom service routes and concrete calls are visible without opening source
files. Generated cards, config templates, local hub index records, and local
hub JSON metadata responses filter raw secret-shaped metadata keys such as
`api_key`/`apiKey`/`apikey`, tokens, `accessToken`/`accesstoken`, passwords,
cookies, `authorization`, and credentials while preserving local refs such as
`api_key_ref`, `apiKeyRef`, and `apikeyref`.

Validation accepts well-formed external `psi://.../schemas/name` refs, rejects
malformed schema refs, and catches same-package schema refs that point at
missing declared schemas. Ref, package, and resource-name segments must be
plain path segments without whitespace, percent escapes, path separators, or
semicolon params.
Doc, example, and asset package-file paths must stay portable and must not use
symlinks, because local publish and download copies skip symlinks.
Tactic examples should include an `input`, `output`, or `command`; empty
examples produce a validation warning so cards stay useful.
Packages that need provider credentials should declare public requirements in
`[requirements.api_keys]`, mapping conventional environment names such as
`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `TOGETHER_API_KEY` to short
descriptions. Package manifests describe required names only; raw secret
values stay in the user's environment, OS keyring, or local env file managed by
`psi init`.
Packages should declare `[card]` metadata and `[docs.readme]` when a
`README.md` exists; missing card/readme metadata produces validation warnings
so generated human and agent cards stay discoverable.
Endpoint metadata must declare one of `GET`, `POST`, `PUT`, `PATCH`, or
`DELETE`, use a `/`-prefixed path without empty or dot segments, backslashes,
colons, semicolon path params, queries, fragments, URLs, network-path prefixes, or
percent escapes, and use known SSSN scopes when a `scope` is provided.
Service resources must declare either an importable `entry` or a declared
`tactic`, so package cards and config templates do not advertise unbound
services.
Local `.psi/config.toml` binding keys are also validated as strict
`psi://org/package/resources/name` refs with known PSI resource sections.
Each binding must declare exactly one serializable concrete target: `url`,
`store`, or `path`; other keys are kept as metadata.
URL targets must be absolute HTTP(S) URLs without URL params, query strings,
fragments, or embedded credentials.
In-process `object` bindings are registered with
`LocalConfigResolver.bind(..., object=...)` and are not serialized into
`.psi/config.toml`.
Use `[refs."psi://...".metadata]` for structured binding metadata. Legacy
top-level extra keys still work, but the explicit metadata table wins on
duplicate keys. Ref, service, and store metadata must not include raw
secret-shaped keys such as `api_key`/`apiKey`/`apikey`, tokens,
`accessToken`/`accesstoken`, passwords, cookies, `authorization`, or
credentials; use local credential refs such as `api_key_ref`, `apiKeyRef`, or
`apikeyref` instead.
Metadata maps must use string keys; direct Python metadata with non-string keys
is rejected before Pydantic can coerce keys into text.

Local hub storage defaults to:

```text
.psihub/
  packages/
  index/
```

When a local hub is reopened, index records must still point at the deterministic
`.psihub/packages/org/name/version/psi.toml` package location.

Local publish copies package source into the hub while excluding local-only
secret/config/cache material such as `.env`, `.env.local`, `.envrc`,
`.envrc.local`, `.netrc`, `.pypirc`, `.npmrc`, `.ssh/`, `.aws/`, `.azure/`,
`.gcloud/`, root-level private key files such as `id_ed25519` and `id_rsa`,
`.direnv/`, `.psi/`, `.psihub/`, virtualenvs, build output, and Python caches.
Template files such as `.env.example`, `.env.sample`, `.env.template`,
`.envrc.example`, `.envrc.sample`, and `.envrc.template` are preserved.
Symlinks are skipped rather than followed during publish and download copies.

Generated config templates assign multiple service refs distinct default local
ports in manifest order. A service can declare `port` in its metadata to prefer
a local config-template port; PsiHub still only writes passive config and does
not launch that service. Tactic refs point at the local port for the service
that declares the tactic, falling back to port 8000 when no service declares it.
Templates also include passive `[services.*]` port tables and `[stores.*]` path
tables for humans or future runners to inspect without asking PsiHub to launch
anything; store table paths must be non-empty strings without whitespace and
must stay portable relative local paths, without absolute paths, traversal,
home expansion, percent escapes, URL syntax, or Windows/UNC path syntax.
Snapshot resources render as `psi://.../snapshots/name` refs and bind to the
same local store path convention as channels.
Config defaults render under `[settings]`; `LocalConfigResolver.settings()`
and `setting(name, default)` expose those local values alongside ref bindings,
`services()/service(name)`, and `stores()/store(name)`.

Use `--hub` to point commands at another local hub directory.
