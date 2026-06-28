import asyncio

import httpx

from lllm import RemoteTactic, Tactic, TacticResolver
from lllm.services import create_tactic_app
from pydantic import BaseModel
from sssn import AsyncSSSNClient, LocalStore
from sssn.server import create_app as create_sssn_app

from psihub import LocalConfigResolver


TACTIC_REF = "psi://demo/http-combo/tactics/analyze"
RAW_CHANNEL_REF = "psi://demo/http-combo/channels/raw"
ANALYSIS_CHANNEL_REF = "psi://demo/http-combo/channels/analysis"


class AnalyzeInput(BaseModel):
    text: str


class AnalyzeOutput(BaseModel):
    summary: str


class AnalyzeTactic(Tactic[AnalyzeInput, AnalyzeOutput]):
    name = "analyze"
    input_type = AnalyzeInput
    output_type = AnalyzeOutput

    def _run(self, input_value, *, context=None):
        return AnalyzeOutput(summary=input_value.text.upper())


def test_http_refs_call_lllm_service_and_sssn_channel_service(tmp_path):
    config = LocalConfigResolver.from_text(
        f"""
[refs."{TACTIC_REF}"]
url = "http://lllm/run"

[refs."{RAW_CHANNEL_REF}"]
url = "http://sssn"

[refs."{ANALYSIS_CHANNEL_REF}"]
url = "http://sssn"
""".lstrip(),
        root=tmp_path / "workspace",
    )
    lllm_app = create_tactic_app(AnalyzeTactic())
    sssn_app = create_sssn_app(LocalStore(tmp_path / "store"))

    async def run():
        tactic_resolver = TacticResolver()
        tactic_resolver.register(
            TACTIC_REF,
            RemoteTactic(
                config.resolve(TACTIC_REF).url,
                name="analyze",
                input_type=AnalyzeInput,
                output_type=AnalyzeOutput,
                async_transport=httpx.ASGITransport(app=lllm_app),
            ),
        )
        raw_client = AsyncSSSNClient(
            config.resolve(RAW_CHANNEL_REF).url,
            transport=httpx.ASGITransport(app=sssn_app),
        )
        analysis_client = AsyncSSSNClient(
            config.resolve(ANALYSIS_CHANNEL_REF).url,
            transport=httpx.ASGITransport(app=sssn_app),
        )
        await raw_client.create_channel({"name": "raw"})
        await analysis_client.create_channel({"name": "analysis"})
        raw = await raw_client.append_event(
            {
                "channel": "raw",
                "payload": {"text": "hello"},
                "correlation_id": "run-1",
            }
        )
        output = await tactic_resolver.arun(TACTIC_REF, raw.payload)
        analysis = await analysis_client.append_event(
            {
                "channel": "analysis",
                "kind": "analysis",
                "payload": output.model_dump(mode="json"),
                "correlation_id": raw.correlation_id,
                "parent_ids": [raw.id],
            }
        )
        loaded = await analysis_client.query_events("analysis")
        return output, raw, analysis, loaded

    output, raw, analysis, loaded = asyncio.run(run())

    assert output == AnalyzeOutput(summary="HELLO")
    assert analysis.parent_ids == (raw.id,)
    assert loaded[0].id == analysis.id
    assert loaded[0].payload == {"summary": "HELLO"}
