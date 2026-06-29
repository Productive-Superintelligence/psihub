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
            agent_card = await client.get("/packages/demo/echo/agent-card")
            config = await client.get("/packages/demo/echo/config-template")
            download = await client.get("/packages/demo/echo/download")
        return health, validation, publish, listed, metadata, card, agent_card, config, download

    health, validation, publish, listed, metadata, card, agent_card, config, download = asyncio.run(run())

    assert health.json() == {"ok": True}
    assert validation.json()["ok"] is True
    assert publish.json()["key"] == "demo/echo@0.1.0"
    assert listed.json()[0]["identifier"] == "demo/echo"
    assert metadata.json()["key"] == "demo/echo@0.1.0"
    assert "psi://demo/echo/tactics/echo" in card.text
    assert "Agent Card: demo/echo" in agent_card.text
    assert '[refs."psi://demo/echo/tactics/echo"]' in config.text
    assert download.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        assert "psi.toml" in archive.namelist()


def test_local_hub_server_rejects_invalid_publish(tmp_path):
    package = make_lifecycle_package(tmp_path)
    text = (package / "psi.toml").read_text(encoding="utf-8")
    (package / "psi.toml").write_text(
        text.replace('tactic = "echo"', 'tactic = "missing"'),
        encoding="utf-8",
    )
    app = create_app(hub=LocalHub(tmp_path / "hub"))

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            publish = await client.post(
                "/publish",
                json={"path": str(package), "validate": True},
            )
            listed = await client.get("/packages")
        return publish, listed

    publish, listed = asyncio.run(run())

    assert publish.status_code == 400
    assert publish.json()["detail"]["ok"] is False
    assert publish.json()["detail"]["issues"][0]["code"] == "service_tactic_missing"
    assert listed.json() == []


def test_local_hub_server_rejects_invalid_package_identifiers(tmp_path):
    app = create_app(hub=LocalHub(tmp_path / "hub"))

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return [
                await client.get(path)
                for path in (
                    "/packages/bad:org/echo",
                    "/packages/demo/bad:name",
                    "/packages/bad:org/echo/card",
                    "/packages/bad:org/echo/agent-card",
                    "/packages/bad:org/echo/config-template",
                    "/packages/bad:org/echo/download",
                )
            ]

    responses = asyncio.run(run())

    assert {response.status_code for response in responses} == {400}
    assert all("path segment" in response.json()["detail"] for response in responses)
