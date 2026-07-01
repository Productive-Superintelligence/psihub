# Cards And Agent Cards

Package cards are human-readable summaries rendered from `psi.toml`, docs,
examples, resource metadata, and validation results.

```bash
psihub --hub .psihub card demo/echo
```

Agent cards are concise instructions for coding agents:

```bash
psihub --hub .psihub agent-card demo/echo
```

Cards include:

- package identity and summary,
- declared resources and refs,
- services and custom endpoints,
- examples,
- suggested commands,
- safety and latency notes when present,
- local config templates.

## Package Metadata

Packages should declare `[card]` metadata and `[docs.readme]` when a README is
present:

```toml
[card]
summary = "Echo tactic package."
tags = ["demo", "tactic"]
suggested_commands = ["uvicorn demo.app:create_app --reload"]

[docs.readme]
path = "README.md"
title = "README"
```

Missing card/readme metadata is a validation warning, not an error, so local
drafts can remain valid while still nudging authors toward discoverable
packages.

## Endpoint Metadata

Service and SSSN helper metadata can expose custom endpoints:

```toml
[services.api]
entry = "demo.app:create_app"
transport = "fastapi"

[[services.api.endpoints]]
name = "health"
method = "GET"
path = "/health"
description = "Service health check."
```

Generated cards show custom routes beside portable package resources so a
human or coding agent can decide which API to call without reading the service
source first.

## Secret Filtering

Generated cards, agent cards, config templates, local hub index records, and
local hub metadata responses filter raw secret-shaped metadata keys such as
`api_key`/`apiKey`/`apikey`, tokens, `accessToken`/`accesstoken`, passwords,
cookies, `authorization`, and credentials.

Use refs such as `api_key_ref`, `apiKeyRef`, and `apikeyref` when a card needs
to say which local credential a runner should provide.

## Config Templates

`psihub config-template` turns package resources into passive local config:

```bash
psihub --hub .psihub config-template demo/echo
```

Templates can include service ports, store paths, settings, tactic URL refs,
channel store refs, and snapshot store refs. PsiHub writes instructions; it
does not launch the services or create the stores.
