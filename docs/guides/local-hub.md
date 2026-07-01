# Local Hub

The local hub is deterministic disk storage for package development and tests:

```text
.psihub/
  packages/
  index/
```

On reopen, index records must still point at the matching
`.psihub/packages/org/name/version/psi.toml` package file.

## Publish

Publish a package:

```bash
psihub --hub .psihub publish demo-package --local
```

Publishing validates by default and rejects packages with validation errors.
Use `--no-validate` only for intentionally incomplete local experiments.

Publish copies package source into the hub, but skips local-only secret/config
and cache material such as `.env`, `.env.local`, `.envrc`, `.envrc.local`,
`.netrc`, `.pypirc`, `.npmrc`, `.ssh/`, `.aws/`, `.azure/`, `.gcloud/`,
root-level private key files such as `id_ed25519` and `id_rsa`, `.direnv/`,
`.psi/`, `.psihub/`, virtualenvs, build output, and Python caches. Template
files like `.env.example`, `.env.sample`, `.env.template`, `.envrc.example`,
`.envrc.sample`, and `.envrc.template` remain publishable.
Symlinks are skipped rather than followed during publish and download copies.

## Inspect

List packages:

```bash
psihub --hub .psihub list
```

Render package explanations:

```bash
psihub --hub .psihub card demo/echo
psihub --hub .psihub agent-card demo/echo
psihub --hub .psihub config-template demo/echo
```

Cards and config templates are generated from stored package metadata. They are
safe to hand to humans or coding agents because secret-shaped metadata keys are
filtered before rendering.

## Download

Download a package:

```bash
psihub --hub .psihub get demo/echo --dest downloaded
```

Choose a download destination outside `.psihub` so downloaded copies never
overwrite hub storage. Downloads are normal folders, not symlinks into the
hub.

## Whole-System Fixtures

PsiHub lifecycle tests include a deterministic societal analysts fixture suite.
It publishes source-channel, analyst-tactic, combined analyst, aggregate-report,
and downstream decision-review packages into a local hub, downloads them into a
clean workspace, generates cards and config templates, then runs a local harness
with dummy SSSN channels and LLLM tactics.

The fixture is intentionally offline and synthetic. It proves package metadata,
refs, cards, config templates, downloaded-package reuse, and local composition;
it does not make financial, political, cultural, or trading recommendations.

## Serve

The local hub API exposes package metadata and downloads to local tools:

```bash
psihub --hub .psihub serve --host 127.0.0.1 --port 8787
```

The API does not launch package services. It serves package cards, metadata,
agent cards, config templates, and package archives from the selected local
hub root.
