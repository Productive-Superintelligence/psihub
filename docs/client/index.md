# Python Package

PsiHub is a Python package for PSI package metadata, validation, local hub
storage, cards, config templates, and optional local hub APIs.

It is not the user-facing command line. `psi` owns local launch and credential
setup. PsiHub keeps package metadata inspectable and portable for Python code,
apps, scripts, AAAX, and agents.

## Install

```bash
python -m pip install psihub
```

## Create Package Metadata

```python
from psihub import init_package

init_package("demo-package", org="demo", name="echo", kind="tactic")
```

## Validate

```python
from psihub import validate_package

report = validate_package("demo-package")
if not report.ok:
    for issue in report.issues:
        print(issue.level, issue.code, issue.message)
```

Validation checks refs, resources, package-file paths, card metadata, endpoint
metadata, and API key requirement declarations.

## Publish And Resolve

```python
from psihub import LocalHub

hub = LocalHub(".psihub")
record = hub.publish("demo-package")
latest = hub.get("demo/echo")
downloaded = hub.download("demo/echo", "./downloaded")
```

`LocalHub` stores packages under deterministic `.psihub/packages` and
`.psihub/index` paths. Download returns another ordinary package folder with
`psi.toml`, docs, examples, and assets intact.

## Render Cards

```python
package_card = hub.card("demo/echo")
agent_card = hub.agent_card("demo/echo")
config = hub.config_template("demo/echo")
```

Cards expose resources, endpoint hints, package docs, and required API key
names without printing secret values.

## Embed The API

```python
from psihub import LocalHub, create_app

app = create_app(hub=LocalHub(".psihub"))
```

Use the API when an app or development tool needs to browse the same local hub.

The `psihub` console command remains a developer convenience over these Python
APIs. The unified user CLI is `psi`.
