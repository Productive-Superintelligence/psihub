# Contributing To PsiHub

PsiHub is the package registry layer for Psi packages.

## Development Setup

```bash
python -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e ".[dev]"
```

Run:

```bash
.venv/bin/python -m pytest
```

## Design Rules

- Keep the package record transport-neutral.
- Keep local filesystem behavior compatible with a future hosted backend.
- Validate package entrypoints without forcing one runtime.
- Render package cards and config templates without launching services.
- Keep service launch behavior in humans, scripts, AAAX, or another runner.
