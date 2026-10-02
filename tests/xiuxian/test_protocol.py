import os, sys, json, copy
from pathlib import Path
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from xiuxian.mcp_dispatch import MCP_TOOLS
from xiuxian.island import IslandGame


def params(db):
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "xiuxian.server", "--db", str(db)],
        env=dict(
            os.environ,
            PYTHONPATH=str(Path(__file__).resolve().parents[2] / "src"),
            PYTHONIOENCODING="utf-8",
        ),
    )


@pytest.mark.asyncio
async def test_real_stdio(tmp_path):
    async with stdio_client(params(tmp_path / "stdio.db")) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            assert {t.name for t in (await session.list_tools()).tools} == set(
                MCP_TOOLS
            )

            async def call(group, command=""):
                r = await session.call_tool(
                    group, {"command": command} if group != "relay_manual" else {}
                )
                return json.loads(r.content[0].text)

            assert (await call("relay_manual"))["result"]["world"] == "灵汐岛"
            assert (await call("cultivator_ops", "rename 新道号"))["ok"]
            assert (await call("sect_ops", "join qingxiao"))["ok"]
            assert (await call("cultivate_ops", "meditate 4"))["result"][
                "gained"
            ] in range(20, 45, 4)
            assert not (await call("battle_ops", "skill strike 99999"))["ok"]
            assert len((await session.list_resources()).resources) == 1
            assert len((await session.list_prompts()).prompts) == 1


def test_real_http_mcp(tmp_path, monkeypatch):
    from starlette.testclient import TestClient
    from xiuxian.http_app import create_http_app

    monkeypatch.setenv("REGISTRATION_OPEN", "true")
    with TestClient(create_http_app(tmp_path), base_url="http://localhost") as c:
        # A human-issued credential can be used by AI; both operate this exact player.
        key = c.post(
            "/api/register", json={"name": "共号修士", "kind": "human"}
        ).json()["api_key"]
        headers = {
            "Authorization": "Bearer " + key,
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }

        def rpc(method, params=None):
            response = c.post(
                "/mcp/",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": method,
                    "params": params or {},
                },
            )
            assert response.status_code == 200, response.text
            return response.json()["result"]

        rpc(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        )
        assert {t["name"] for t in rpc("tools/list")["tools"]} == set(MCP_TOOLS)
        rpc(
            "tools/call",
            {"name": "sect_ops", "arguments": {"command": "join qingxiao"}},
        )
        args = {"command": "meditate 3", "request_id": "mcp-once"}
        r = rpc("tools/call", {"name": "cultivate_ops", "arguments": args})
        gained = json.loads(r["content"][0]["text"])["result"]["gained"]
        assert rpc("tools/call", {"name": "cultivate_ops", "arguments": args}) == r
        view = c.get("/api/v1/state", headers=headers).json()
        assert view["self"]["result"]["cultivation"] == gained
        assert view["history"]["result"][-1]["action"] == "cultivate"
        assert view["readOnly"] is False
        r = c.post(
            "/api/v1/command",
            headers=headers,
            json={"tool": "cultivator_ops", "command": "rename 新道号"},
        )
        assert r.status_code == 200
        r = rpc(
            "tools/call", {"name": "cultivator_ops", "arguments": {"command": "sheet"}}
        )
        assert json.loads(r["content"][0]["text"])["result"]["name"] == "新道号"
        key2 = c.post("/api/register", json={"name": "另一修士", "kind": "ai"}).json()[
            "api_key"
        ]
        assert (
            c.get("/api/v1/state", headers={"Authorization": "Bearer " + key2}).json()[
                "self"
            ]["result"]["cultivation"]
            == 0
        )


@pytest.mark.asyncio
async def test_full_campaign_over_stdio(tmp_path):
    from xiuxian.island_demo import campaign

    tape = []
    campaign(tmp_path / "expected.db", record=tape)
    birth = next(
        s["response"]["result"]
        for s in tape
        if s["tool"] == "cultivator_ops" and s["command"] == "sheet"
    )
    live = IslandGame(tmp_path / "live.db")
    for key in ("root", "rootElements", "aptitude"):
        live.player[key] = birth[key]
    live._store()
    live.close()
    async with stdio_client(params(tmp_path / "live.db")) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            for step in tape:
                actual = json.loads(
                    (
                        await session.call_tool(
                            step["tool"], {"command": step["command"]}
                        )
                    )
                    .content[0]
                    .text
                )
                expected = copy.deepcopy(step["response"])
                if step["tool"] == "cultivator_ops" and step["command"] == "sheet":
                    for response in (actual, expected):
                        for key in ("id", "name", "createdAt"):
                            response["result"].pop(key, None)
                assert actual == expected, (
                    step["tool"],
                    step["command"],
                    actual,
                    expected,
                )
