# CLI

Initialize package metadata:

```bash
psihub init PATH --org ORG --name NAME --kind KIND
```

Validate a package folder:

```bash
psihub validate PATH
```

Publish into a local hub:

```bash
psihub --hub .psihub publish PATH --local
```

Inspect local hub contents:

```bash
psihub --hub .psihub list
psihub --hub .psihub card ORG/NAME
psihub --hub .psihub agent-card ORG/NAME
psihub --hub .psihub config-template ORG/NAME
```

Download a package folder:

```bash
psihub --hub .psihub get ORG/NAME --dest downloaded
```

The download destination should be outside the selected local hub root.

Serve the local hub API:

```bash
psihub --hub .psihub serve --host 127.0.0.1 --port 8787
```

`--hub` selects the local hub root. Without it, PsiHub uses `.psihub` in the
current workspace.
