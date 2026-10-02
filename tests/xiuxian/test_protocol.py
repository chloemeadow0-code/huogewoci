import os, sys, json
from pathlib import Path
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from xiuxian.engine import TOOLS


@pytest.mark.asyncio
async def test_real_stdio(tmp_path):
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "xiuxian.server", "--db", str(tmp_path / "stdio.db")],
        env=dict(
            os.environ,
            PYTHONPATH=str(Path(__file__).resolve().parents[2] / "src"),
            PYTHONIOENCODING="utf-8",
        ),
    )
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            assert {t.name for t in (await session.list_tools()).tools} == set(TOOLS)

            def payload(result):
                return json.loads(result.content[0].text)

            assert (
                payload(await session.call_tool("get_self"))["result"]["realm"]
                == "炼气"
            )
            assert payload(
                await session.call_tool("choose_route", {"route": "qingxiao"})
            )["ok"]
            assert (
                payload(await session.call_tool("cultivate", {"duration": 4}))[
                    "result"
                ]["gained"]
                == 32
            )
            assert not payload(
                await session.call_tool("fight", {"target": "guardian"})
            )["ok"]
            assert (
                await session.call_tool("time_set", {"datetime": "2040-01-01"})
            ).isError
            assert len((await session.list_resources()).resources) == 1
            assert len((await session.list_prompts()).prompts) == 1
            assert (await session.read_resource("xiuxian://rules")).contents


def test_real_http_mcp(tmp_path, monkeypatch):
    from starlette.testclient import TestClient
    from xiuxian.http_app import create_http_app

    monkeypatch.setenv("REGISTRATION_OPEN", "true")
    with TestClient(create_http_app(tmp_path), base_url="http://localhost") as c:
        token = c.post("/api/register", json={"name": "独立AI", "kind": "ai"}).json()[
            "api_key"
        ]
        headers = {
            "Authorization": "Bearer " + token,
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }

        def rpc(method, params=None):
            r = c.post(
                "/mcp/",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": method,
                    "params": params or {},
                },
            )
            assert r.status_code == 200, r.text
            return r.json()["result"]

        assert rpc(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        )["serverInfo"]
        assert {t["name"] for t in rpc("tools/list")["tools"]} == set(TOOLS)
        rpc("tools/call", {"name": "choose_route", "arguments": {"route": "qingxiao"}})
        r = rpc("tools/call", {"name": "cultivate", "arguments": {"duration": 3}})
        assert json.loads(r["content"][0]["text"])["result"]["gained"] == 24
        view = c.get("/api/state", headers=headers)
        assert view.status_code == 200
        assert view.json()["readOnly"] is True
        assert view.json()["kind"] == "ai"
        assert view.json()["self"]["result"]["cultivation"] == 24
        assert view.json()["history"]["result"][-1]["action"] == "cultivate"
        clock_before = view.json()["world"]["result"]["time"]
        assert (
            c.get("/api/state", headers=headers).json()["world"]["result"]["time"]
            == clock_before
        )
        assert (
            c.post(
                "/api/action",
                headers=headers,
                json={"tool": "cultivate", "arguments": {}},
            ).status_code
            == 403
        )
        assert rpc("resources/list")["resources"][0]["uri"] == "xiuxian://rules"
        assert rpc("prompts/list")["prompts"][0]["name"] == "begin_journey"
        token2 = c.post("/api/register", json={"name": "第二AI", "kind": "ai"}).json()[
            "api_key"
        ]
        headers["Authorization"] = "Bearer " + token2
        r = rpc("tools/call", {"name": "get_self", "arguments": {}})
        assert json.loads(r["content"][0]["text"])["result"]["cultivation"] == 0
        second_view = c.get("/api/state", headers=headers).json()
        assert second_view["self"]["result"]["name"] == "第二AI"
        assert second_view["history"]["result"] == []


@pytest.mark.asyncio
async def test_full_campaign_over_stdio(tmp_path):
    from xiuxian.demo import campaign
    import copy

    tape = []
    campaign(tmp_path / "expected.db", record=tape)
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "xiuxian.server", "--db", str(tmp_path / "live.db")],
        env=dict(
            os.environ,
            PYTHONPATH=str(Path(__file__).resolve().parents[2] / "src"),
            PYTHONIOENCODING="utf-8",
        ),
    )
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            for step in tape:
                actual = json.loads(
                    (await session.call_tool(step["tool"], step["arguments"]))
                    .content[0]
                    .text
                )
                expected = copy.deepcopy(step["response"])
                if step["tool"] == "get_self":
                    for response in (actual, expected):
                        for key in ("id", "name", "createdAt"):
                            response["result"].pop(key, None)
                assert actual == expected, (step["tool"], actual, expected)
