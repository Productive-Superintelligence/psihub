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

Choose a download destination outside `.psihub` so downloaded copies never
overwrite hub storage.

Publishing validates by default and rejects packages with validation errors.
Use `--no-validate` only for intentionally incomplete local experiments.

Publish copies package source into the hub, but skips local-only secret/config
and cache material such as `.env`, `.env.local`, `.psi/`, `.psihub/`,
virtualenvs, build output, and Python caches. Template files like
`.env.example`, `.env.sample`, and `.env.template` remain publishable.
