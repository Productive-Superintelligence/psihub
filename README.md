# PsiHub

PsiHub is the local-first package hub for PSI packages.

It owns the package protocol: `psi.toml`, validation, local publish/download,
package cards, and local config templates. It does not launch services.
`psi.toml` must be a regular package file rather than a symlink.

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

For a step-by-step local package walkthrough, see
`docs/tutorials/local-package-lifecycle.md`.

Local publish validates by default and rejects packages with validation errors.
Use `psihub publish --local --no-validate` only when intentionally indexing an
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
missing declared schemas.
Doc, example, and asset package-file paths must stay portable and must not use
symlinks, because local publish and download copies skip symlinks.
Tactic examples should include an `input`, `output`, or `command`; empty
examples produce a validation warning so cards stay useful.
Packages should declare `[card]` metadata and `[docs.readme]` when a
`README.md` exists; missing card/readme metadata produces validation warnings
so generated human and agent cards stay discoverable.
Endpoint metadata must declare one of `GET`, `POST`, `PUT`, `PATCH`, or
`DELETE`, use a `/`-prefixed path, and use known SSSN scopes when a `scope` is
provided.
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
anything; store table paths must be non-empty strings without whitespace.
Snapshot resources render as `psi://.../snapshots/name` refs and bind to the
same local store path convention as channels.
Config defaults render under `[settings]`; `LocalConfigResolver.settings()`
and `setting(name, default)` expose those local values alongside ref bindings,
`services()/service(name)`, and `stores()/store(name)`.

Use `--hub` to point commands at another local hub directory.
