"""Local PsiHub command line tools."""

from __future__ import annotations

import argparse
import sys

from .local import LocalHub
from .manifest import init_package
from .validator import validate_package


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="psihub", description="Local PSI package hub")
    parser.add_argument("--hub", default=".psihub", help="Local hub directory")
    subcommands = parser.add_subparsers(dest="command", required=True)

    init = subcommands.add_parser("init", help="Prepare package metadata")
    init.add_argument("path", nargs="?", default=".")
    init.add_argument("--name")
    init.add_argument("--org", default="local")
    init.add_argument("--kind", default="mixed")
    init.add_argument("--force", action="store_true")

    validate = subcommands.add_parser("validate", help="Validate a package")
    validate.add_argument("path")

    publish = subcommands.add_parser("publish", help="Publish a package")
    publish.add_argument("path")
    publish.add_argument("--local", action="store_true", help="Publish to the local hub")
    publish.add_argument("--no-validate", action="store_true")

    get = subcommands.add_parser("get", help="Download a package from the local hub")
    get.add_argument("identifier")
    get.add_argument("--dest", default=".")
    get.add_argument("--version")

    list_packages = subcommands.add_parser("list", help="List local packages")

    card = subcommands.add_parser("card", help="Render a package card")
    card.add_argument("identifier")
    card.add_argument("--version")

    agent_card = subcommands.add_parser("agent-card", help="Render a package agent card")
    agent_card.add_argument("identifier")
    agent_card.add_argument("--version")

    config = subcommands.add_parser("config-template", help="Render .psi/config.toml")
    config.add_argument("identifier")
    config.add_argument("--version")

    serve = subcommands.add_parser("serve", help="Serve the local package hub API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8787)
    serve.add_argument("--log-level", default="info")

    args = parser.parse_args(argv)

    if args.command == "init":
        path = init_package(
            args.path,
            name=args.name,
            org=args.org,
            kind=args.kind,
            force=args.force,
        )
        print(path)
        return 0

    if args.command == "validate":
        report = validate_package(args.path)
        for issue in report.issues:
            print(f"{issue.level}: {issue.code}: {issue.message}", file=sys.stderr)
        print("ok" if report.ok else "failed")
        return 0 if report.ok else 1

    hub = LocalHub(args.hub)
    if args.command == "publish":
        if not args.local:
            parser.error("Only local publish is supported in this phase. Use --local.")
        record = hub.publish(args.path, validate=not args.no_validate)
        print(record.key)
        return 0 if record.validation.ok or args.no_validate else 1

    if args.command == "get":
        print(hub.download(args.identifier, args.dest, version=args.version))
        return 0

    if args.command == "list":
        for record in hub.list():
            print(record.key)
        return 0

    if args.command == "card":
        print(hub.card(args.identifier, version=args.version), end="")
        return 0

    if args.command == "agent-card":
        print(hub.agent_card(args.identifier, version=args.version), end="")
        return 0

    if args.command == "config-template":
        print(hub.config_template(args.identifier, version=args.version), end="")
        return 0

    if args.command == "serve":
        import uvicorn

        from .server import create_app

        uvicorn.run(
            create_app(hub=hub),
            host=args.host,
            port=args.port,
            log_level=args.log_level,
        )
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
