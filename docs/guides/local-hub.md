# Local Hub

The local hub is deterministic disk storage for package development and tests:

```text
.psihub/
  packages/
  index/
```

Publish a package:

```bash
psihub --hub .psihub publish demo-package --local
```

List packages:

```bash
psihub --hub .psihub list
```

Download a package:

```bash
psihub --hub .psihub get demo/echo --dest downloaded
```

Publishing validates by default and rejects packages with validation errors.
Use `--no-validate` only for intentionally incomplete local experiments.
