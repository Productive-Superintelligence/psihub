"""FastAPI app for the local disk-backed PsiHub."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .local import LocalHub
from .validator import validate_package


class ValidateRequest(BaseModel):
    path: str


class PublishRequest(BaseModel):
    path: str
    run_validation: bool = Field(default=True, alias="validate")


def create_app(*, hub: LocalHub | None = None, hub_root: str | Path = ".psihub"):
    """Create a local package-hub API over a disk-backed hub."""

    try:
        from fastapi import FastAPI, HTTPException
        from fastapi.encoders import jsonable_encoder
        from fastapi.responses import PlainTextResponse, StreamingResponse
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Install psihub[server] to use the FastAPI server.") from exc

    local_hub = hub or LocalHub(hub_root)
    app = FastAPI(title="PsiHub Local Hub", version="0.1.0")
    app.state.psihub = local_hub

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"ok": True}

    @app.post("/validate")
    async def validate(request: ValidateRequest) -> dict[str, Any]:
        report = validate_package(request.path)
        return report.model_dump(mode="json")

    @app.post("/publish")
    async def publish(request: PublishRequest) -> dict[str, Any]:
        record = local_hub.publish(request.path, validate=request.run_validation)
        return jsonable_encoder(record)

    @app.get("/packages")
    async def list_packages() -> list[dict[str, Any]]:
        return [jsonable_encoder(record) for record in local_hub.list()]

    @app.get("/packages/{org}/{name}")
    async def metadata(org: str, name: str, version: str | None = None) -> dict[str, Any]:
        try:
            return jsonable_encoder(local_hub.get(f"{org}/{name}", version=version))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/packages/{org}/{name}/card")
    async def card(org: str, name: str, version: str | None = None) -> str:
        try:
            return PlainTextResponse(local_hub.card(f"{org}/{name}", version=version))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/packages/{org}/{name}/config-template")
    async def config_template(org: str, name: str, version: str | None = None) -> str:
        try:
            return PlainTextResponse(
                local_hub.config_template(f"{org}/{name}", version=version)
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/packages/{org}/{name}/download")
    async def download(org: str, name: str, version: str | None = None):
        try:
            record = local_hub.get(f"{org}/{name}", version=version)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        payload = _zip_folder(record.root)
        headers = {
            "content-disposition": f'attachment; filename="{record.name}-{record.version}.zip"'
        }
        return StreamingResponse(
            io.BytesIO(payload),
            media_type="application/zip",
            headers=headers,
        )

    return app


def _zip_folder(root: Path) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(root))
    return buffer.getvalue()
