import os
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from hogwarts.engine import TOOLS
from hogwarts.demo import run_demo
from hogwarts.server import create_server


@pytest.mark.asyncio
async def test_registry_allowlist(tmp_path):
    app = create_server(tmp_path / 'registry.db')
    assert {tool.name for tool in await app.list_tools()} == set(TOOLS)
    assert await app.list_resources() == []
    assert await app.list_prompts() == []


@pytest.mark.asyncio
async def test_real_stdio_session(tmp_path):
    expected = run_demo(tmp_path / 'expected.db')
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2] / 'src'),
               PYTHONIOENCODING='utf-8')
    params = StdioServerParameters(command=sys.executable,
                                  args=['-m', 'hogwarts.server', '--db', str(tmp_path / 'stdio.db')], env=env)
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            listed = await session.list_tools()
            assert {t.name for t in listed.tools} == set(TOOLS)
            def payload(result):
                import json
                return json.loads(result.content[0].text)
            assert payload(await session.call_tool('sleep', {'hours': 0}))['ok']
            assert payload(await session.call_tool('check_status'))['result']['year'] == 1
            denied = payload(await session.call_tool('cast_spell', {'spell':'lumos','target':'wand'}))
            assert not denied['ok']
            unavailable = await session.call_tool('time_set', {'datetime':'2040-01-01'})
            assert unavailable.isError
            # Same end-to-end demo over actual MCP subprocess transport.
            for step in expected:
                actual = payload(await session.call_tool(step['tool'], step['arguments']))
                assert actual == step['response']
