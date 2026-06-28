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

- package identity and summary
- declared resources and refs
- services and custom endpoints
- examples
- suggested commands
- safety and latency notes when present
- local config templates

Packages should declare `[card]` metadata and `[docs.readme]` when a README is
present. Missing card/readme metadata is a validation warning, not an error, so
local drafts can remain valid while still nudging authors toward discoverable
packages.
