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

`--hub` selects the local hub root. Without it, PsiHub uses `.psihub` in the
current workspace.
