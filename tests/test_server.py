import asyncio
import io
import zipfile

import httpx
import pytest
from pydantic import ValidationError

from psihub import LocalHub
from psihub.server import PublishRequest, ValidateRequest, create_app
from test_lifecycle import make_lifecycle_package


@pytest.mark.parametrize(
    "factory",
    [
        lambda: ValidateRequest(path=b"."),
        lambda: PublishRequest(path=b"."),
        lambda: ValidateRequest(path=""),
        lambda: PublishRequest(path="   "),
    ],
)
def test_local_hub_server_request_models_reject_malformed_paths(factory):
    with pytest.raises(ValidationError):
        factory()


@pytest.mark.parametrize("value", ["false", "true", 0, 1])
def test_local_hub_server_publish_request_rejects_non_bool_validate(value):
    with pytest.raises(ValidationError):
        PublishRequest(path=".", validate=value)


def test_local_hub_server_rejects_blank_request_paths(tmp_path):
    app = create_app(hub=LocalHub(tmp_path / "hub"))

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            validation = await client.post("/validate", json={"path": "   "})
            publish = await client.post(
                "/publish",
                json={"path": "", "validate": True},
            )
        return validation, publish

    validation, publish = asyncio.run(run())

    assert validation.status_code == 422
    assert publish.status_code == 422
    assert "package path" in validation.text
    assert "package path" in publish.text


def test_local_hub_server_rejects_non_bool_publish_validate(tmp_path):
    app = create_app(hub=LocalHub(tmp_path / "hub"))

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post(
                "/publish",
                json={"path": ".", "validate": "false"},
            )

    response = asyncio.run(run())

    assert response.status_code == 422
    assert "validate" in response.text


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


def test_local_hub_server_respects_version_query_and_numeric_latest(tmp_path):
    package = make_lifecycle_package(tmp_path)
    manifest = package / "psi.toml"
    hub = LocalHub(tmp_path / "hub")

    text = manifest.read_text(encoding="utf-8")
    manifest.write_text(
        text.replace('version = "0.1.0"', 'version = "0.2.0"'),
        encoding="utf-8",
    )
    hub.publish(package)

    text = manifest.read_text(encoding="utf-8")
    manifest.write_text(
        text.replace('version = "0.2.0"', 'version = "0.10.0"').replace(
            'summary = "Echo tactic package."',
            'summary = "Newer numeric echo package."',
        ),
        encoding="utf-8",
    )
    hub.publish(package)
    app = create_app(hub=hub)

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            latest = await client.get("/packages/demo/echo")
            older = await client.get(
                "/packages/demo/echo",
                params={"version": "0.2.0"},
            )
            older_card = await client.get(
                "/packages/demo/echo/card",
                params={"version": "0.2.0"},
            )
            older_download = await client.get(
                "/packages/demo/echo/download",
                params={"version": "0.2.0"},
            )
            bad_version = await client.get(
                "/packages/demo/echo",
                params={"version": "bad version"},
            )
        return latest, older, older_card, older_download, bad_version

    latest, older, older_card, older_download, bad_version = asyncio.run(run())

    assert latest.json()["version"] == "0.10.0"
    assert older.json()["version"] == "0.2.0"
    assert "Echo tactic package." in older_card.text
    assert "Newer numeric echo package." not in older_card.text
    assert bad_version.status_code == 400
    assert "package version" in bad_version.text
    with zipfile.ZipFile(io.BytesIO(older_download.content)) as archive:
        manifest_text = archive.read("psi.toml").decode()
    assert 'version = "0.2.0"' in manifest_text


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
                    "/packages/bad%20org/echo",
                    "/packages/demo/bad%20name",
                    "/packages/bad%25org/echo",
                    "/packages/demo/bad%25name",
                    "/packages/bad:org/echo/card",
                    "/packages/bad:org/echo/agent-card",
                    "/packages/bad:org/echo/config-template",
                    "/packages/bad:org/echo/download",
                )
            ]

    responses = asyncio.run(run())

    assert {response.status_code for response in responses} == {400}
    assert all("path segment" in response.json()["detail"] for response in responses)
