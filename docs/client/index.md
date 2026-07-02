# Client

PsiHub is a local-first package client. It validates `psi.toml`, publishes
packages into a local hub, downloads them, and renders cards for humans and
agents. It does not launch services.

## Install

```bash
python -m pip install psihub
```

## Initialize And Validate

```bash
psihub init demo-package --org demo --name echo --kind tactic
psihub validate demo-package
```

## Publish And List

```bash
psihub --hub .psihub publish demo-package --local
psihub --hub .psihub list
```

Local publish copies the package into deterministic `.psihub/packages` and
`.psihub/index` storage. Package source remains ordinary files.

## Download

```bash
psihub --hub .psihub get demo/echo --dest ./downloaded
```

The downloaded folder keeps `psi.toml`, docs, examples, and assets intact.

## Explain

```bash
psihub --hub .psihub card demo/echo
psihub --hub .psihub agent-card demo/echo
psihub --hub .psihub config-template demo/echo
```

Cards expose resources, endpoint hints, package docs, and required API key
names without printing secret values.

## Serve A Local API

```bash
psihub --hub .psihub serve --host 127.0.0.1 --port 8787
```

Use the API when an app or development tool needs to browse the same local hub.
