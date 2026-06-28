# Getting Started

Install PsiHub in editable mode while developing:

```bash
python -m pip install -e ".[dev,docs]"
```

Create a starter package:

```bash
psihub init demo-package --org demo --name echo --kind tactic
```

Validate it:

```bash
psihub validate demo-package
```

Publish it into a local hub:

```bash
psihub --hub .psihub publish demo-package --local
```

Inspect what the hub knows:

```bash
psihub --hub .psihub list
psihub --hub .psihub card demo/echo
psihub --hub .psihub agent-card demo/echo
psihub --hub .psihub config-template demo/echo
```

Download a normal editable copy:

```bash
psihub --hub .psihub get demo/echo --dest downloaded
```

The downloaded package remains a folder with `psi.toml`, docs, examples, and
source files. Coding agents can inspect it directly.
