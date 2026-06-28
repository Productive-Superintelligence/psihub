# Packages

A PsiHub package is a normal folder with a `psi.toml` manifest. The manifest
declares package metadata and typed resources:

- schemas
- tactics
- services
- channels
- snapshots
- config defaults
- docs
- examples
- assets
- runs

Focused packages should declare a matching primary resource:

```toml
[package]
org = "demo"
name = "echo"
kind = "tactic"
primary = "tactics.echo"
```

App packages can center on a service or run while composing tactics, channels,
snapshots, and config metadata internally.

PsiHub validates the shape. It does not import or run the whole system.
