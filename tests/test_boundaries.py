import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_SOURCES = sorted(
    path for path in ROOT.glob("*.py") if path.name != "__init__.py"
)
FORBIDDEN_IMPORT_ROOTS = (
    "subprocess",
)
FORBIDDEN_CALLS = {
    "asyncio.create_subprocess_exec",
    "asyncio.create_subprocess_shell",
    "os.execl",
    "os.execle",
    "os.execlp",
    "os.execlpe",
    "os.execv",
    "os.execve",
    "os.execvp",
    "os.execvpe",
    "os.posix_spawn",
    "os.posix_spawnp",
    "os.spawnl",
    "os.spawnle",
    "os.spawnlp",
    "os.spawnlpe",
    "os.spawnv",
    "os.spawnve",
    "os.spawnvp",
    "os.spawnvpe",
    "os.system",
    "subprocess.Popen",
    "subprocess.call",
    "subprocess.check_call",
    "subprocess.check_output",
    "subprocess.run",
}


def test_psihub_package_does_not_launch_dependency_services():
    violations: list[str] = []
    for path in PACKAGE_SOURCES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        aliases = _import_aliases(tree)
        for imported in aliases.values():
            if _is_forbidden_import(imported):
                violations.append(f"{path.name} imports {imported}")
        for call in _call_names(tree, aliases):
            if call in FORBIDDEN_CALLS:
                violations.append(f"{path.name} calls {call}")
            if call == "uvicorn.run" and path.name != "cli.py":
                violations.append(f"{path.name} calls {call}")

    assert violations == []


def test_only_cli_serve_launches_the_local_hub_api():
    tree = ast.parse((ROOT / "cli.py").read_text(encoding="utf-8"))
    aliases = _import_aliases(tree)
    uvicorn_calls = [
        call
        for call in _call_names(tree, aliases)
        if call == "uvicorn.run"
    ]

    assert uvicorn_calls == ["uvicorn.run"]


def test_boundary_scanner_rejects_subprocess_from_imports():
    tree = ast.parse("from subprocess import run as run_process")
    aliases = _import_aliases(tree)

    assert _is_forbidden_import(aliases["run_process"])


def _import_aliases(tree: ast.AST) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name.split(".", 1)[0]] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return aliases


def _call_names(tree: ast.AST, aliases: dict[str, str]) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _qualified_name(node.func)
            if name:
                parts = name.split(".", 1)
                if parts[0] in aliases:
                    resolved = aliases[parts[0]]
                    name = f"{resolved}.{parts[1]}" if len(parts) > 1 else resolved
                names.append(name)
    return names


def _is_forbidden_import(imported: str) -> bool:
    return any(
        imported == root or imported.startswith(f"{root}.")
        for root in FORBIDDEN_IMPORT_ROOTS
    )


def _qualified_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _qualified_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""
