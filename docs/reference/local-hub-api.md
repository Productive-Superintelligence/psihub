# Local Hub API

PsiHub can expose the local disk-backed hub through a small FastAPI app. This
API is for package validation, local publishing, metadata lookup, cards, config
templates, and package downloads. It does not launch package services.

```python
from psihub import LocalHub
from psihub.server import create_app

app = create_app(hub=LocalHub(".psihub"))
```

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Check the local hub API process. |
| `POST` | `/validate` | Validate a package folder without publishing it. |
| `POST` | `/publish` | Publish a package folder into the local hub. |
| `GET` | `/packages` | List indexed package records. |
| `GET` | `/packages/{org}/{name}` | Read package metadata. |
| `GET` | `/packages/{org}/{name}/card` | Render the human package card. |
| `GET` | `/packages/{org}/{name}/agent-card` | Render the coding-agent card. |
| `GET` | `/packages/{org}/{name}/config-template` | Render local `.psi/config.toml` bindings. |
| `GET` | `/packages/{org}/{name}/download` | Download the package folder as a zip archive. |

## Validate

```bash
curl -X POST http://127.0.0.1:8710/validate \
  -H 'content-type: application/json' \
  -d '{"path":"demo-package"}'
```

Expected output:

```json
{"ok": true, "issues": []}
```

## Publish

```bash
curl -X POST http://127.0.0.1:8710/publish \
  -H 'content-type: application/json' \
  -d '{"path":"demo-package","validate":true}'
```

Publishing with `validate: true` rejects packages that have validation errors.
The local hub stores accepted packages under `.psihub/packages` and writes
metadata under `.psihub/index`.

## Download

```bash
curl -L http://127.0.0.1:8710/packages/demo/echo/download -o echo.zip
```

The response body is an `application/zip` archive of the package folder.

## Verify

```bash
python -m pytest tests/test_server.py -q
```

Expected output:

```text
... passed
```

Next, use the CLI reference for the same lifecycle from shell commands.
