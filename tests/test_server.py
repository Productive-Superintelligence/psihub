import asyncio
import io
import zipfile

import httpx

from psihub import LocalHub
from psihub.server import create_app
from test_lifecycle import make_lifecycle_package


def test_local_hub_server_lifecycle(tmp_path):
    package = make_lifecycle_package(tmp_path)
    app = create_app(hub=LocalHub(tmp_path / "hub"))

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            health = await client.get("/health")
            validation = await client.post("/validate", json={"path": str(package)})
            publish = await client.post(
                "/publish",
                json={"path": str(package), "validate": True},
            )
            listed = await client.get("/packages")
            metadata = await client.get("/packages/demo/echo")
            card = await client.get("/packages/demo/echo/card")
            config = await client.get("/packages/demo/echo/config-template")
            download = await client.get("/packages/demo/echo/download")
        return health, validation, publish, listed, metadata, card, config, download

    health, validation, publish, listed, metadata, card, config, download = asyncio.run(run())

    assert health.json() == {"ok": True}
    assert validation.json()["ok"] is True
    assert publish.json()["key"] == "demo/echo@0.1.0"
    assert listed.json()[0]["identifier"] == "demo/echo"
    assert metadata.json()["key"] == "demo/echo@0.1.0"
    assert "psi://demo/echo/tactics/echo" in card.text
    assert '[refs."psi://demo/echo/tactics/echo"]' in config.text
    assert download.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        assert "psi.toml" in archive.namelist()
