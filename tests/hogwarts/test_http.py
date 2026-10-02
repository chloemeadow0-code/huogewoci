import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from starlette.testclient import TestClient

from hogwarts.auth import Accounts
from hogwarts.demo import run_demo
from hogwarts.engine import Game, TOOLS
from hogwarts.http_app import create_http_app
from lorekit.support import checkpoint


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('REGISTRATION_OPEN', 'true')
    monkeypatch.setenv('MCP_ALLOWED_HOSTS', 'testserver')
    monkeypatch.setenv('MCP_ALLOWED_ORIGINS', 'http://testserver')
    with TestClient(create_http_app(tmp_path / 'data')) as c:
        yield c


def enroll(client, name):
    response = client.post('/api/register', json={'name':name})
    assert response.status_code == 201, response.text
    return response.json()['api_key']


def headers(key):
    return {'Authorization':'Bearer '+key}


def act(client, key, tool, arguments=None, expected=200):
    response = client.post('/api/action', headers=headers(key), json={'tool':tool,'arguments':arguments or {}})
    assert response.status_code == expected, response.text
    return response.json()


def test_registration_health_and_boundary(client, monkeypatch):
    assert client.get('/health').json()['status'] == 'ok'
    for path in ('/','/register','/play','/manual','/static/app.js','/static/style.css'):
        assert client.get(path).status_code == 200
    for path in ('/api/state','/mcp','/mcp/'):
        assert client.get(path).status_code == 401
    assert client.post('/api/register', json={'name':'x'}).status_code == 400
    key = enroll(client, '雾窗新生')
    act(client,key,'time_set',expected=400)
    act(client,key,'check_status',{'player_key':'someone-else'},expected=400)
    assert client.get('/api/state',headers=headers('hw_sk_fake')).status_code == 401
    assert client.get('/',headers={'Host':'evil.example'}).status_code == 421
    assert client.get('/health',headers={'Host':'platform-probe.internal'}).status_code == 200
    assert client.post('/api/register',json={'name':'雾窗新生'},headers={'Origin':'https://evil.example'}).status_code == 403
    assert client.post('/api/register',content='name=abc',headers={'Content-Type':'text/plain'}).status_code == 415
    assert client.post('/api/register',content='x'*65537,headers={'Content-Type':'application/json'}).status_code == 413
    monkeypatch.setenv('REGISTRATION_OPEN','false')
    assert client.post('/api/register',json={'name':'新同学'}).status_code == 403
    assert client.get('/api/state',headers=headers(key)).status_code == 200


def test_two_players_share_world_keep_private_state(client, tmp_path):
    a,b = enroll(client,'雾窗甲'),enroll(client,'雾窗乙')
    for key in (a,b):
        act(client,key,'sleep',{'hours':0})
        act(client,key,'move',{'destination':'hall'})
        act(client,key,'move',{'destination':'library'})
    act(client,a,'talk',{'npc':'professor','message':'初次见面'})
    reply = act(client,b,'talk',{'npc':'professor','message':'初次见面'})
    assert '你好，新生' in reply['result']['reply']  # A's memories aren't B's.
    act(client,a,'study',{'spell':'alohomora'})
    act(client,a,'cast_spell',{'spell':'alohomora','target':'chest'})
    assert not act(client,b,'inspect',{'target':'chest'})['result']['state']['locked']
    act(client,a,'search',{'target':'chest'})
    state_a = client.get('/api/state',headers=headers(a)).json()
    state_b = client.get('/api/state',headers=headers(b)).json()
    assert state_a['status']['result']['name'] == '雾窗甲'
    assert state_b['status']['result']['name'] == '雾窗乙'
    assert not state_b['status']['result']['learned_spells']
    secret = '图书馆练习箱里藏着温室丢失的银色标签。'
    assert secret in state_a['status']['result']['known_facts']
    assert secret not in json.dumps(state_b,ensure_ascii=False)
    assert 'players' not in state_b
    for key in (a,b):
        assert key.encode() not in (tmp_path/'data'/'accounts.db').read_bytes()
    act(client,b,'search',{'target':'chest'})
    assert secret in client.get('/api/state',headers=headers(b)).json()['status']['result']['known_facts']


def test_identity_concurrent_requests(client):
    a,b = enroll(client,'并发甲'),enroll(client,'并发乙')
    def request(key,name):
        for _ in range(8):
            data=client.get('/api/state',headers=headers(key)).json()
            assert data['status']['result']['name'] == name
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending=[pool.submit(request,a,'并发甲'),pool.submit(request,b,'并发乙')]
        for future in pending:
            future.result()


def test_restart_preserves_identity_and_world(client, tmp_path):
    key = enroll(client,'持续新生')
    act(client,key,'sleep',{'hours':0})
    act(client,key,'move',{'destination':'hall'})
    act(client,key,'move',{'destination':'library'})
    act(client,key,'study',{'spell':'lumos'})
    with TestClient(create_http_app(tmp_path/'data')) as restarted:
        result=restarted.get('/api/state',headers=headers(key)).json()
        assert result['status']['result']['name'] == '持续新生'
        assert 'lumos' in result['status']['result']['learned_spells']
        assert result['scene']['result']['location'] == 'library'


def test_shared_clock_catches_inactive_player(client):
    a,b = enroll(client,'夜游甲'),enroll(client,'休息乙')
    act(client,a,'sleep',{'hours':0})
    act(client,a,'move',{'destination':'hall'})
    act(client,b,'sleep',{'hours':0})
    act(client,b,'wait',{'minutes':720})
    act(client,b,'wait',{'minutes':360})
    result=client.get('/api/state',headers=headers(a)).json()['status']['result']
    assert result['location']=='hospital'
    assert len(result['violations'])==1 and result['house_points']==-5


def test_rejected_action_keeps_checkpoint_cursor(tmp_path):
    game=Game(tmp_path/'game.db')
    try:
        checkpoint.manual_save(game.db,game.sid,'before')
        cursor=checkpoint._get_cursor(game.db,game.sid)
        assert not game.call('cast_spell',spell='lumos',target='wand')['ok']
        assert checkpoint._get_cursor(game.db,game.sid)==cursor
    finally:
        game.close()


@pytest.mark.asyncio
async def test_real_http_mcp_full_demo(tmp_path):
    root=Path(__file__).resolve().parents[2]
    expected=run_demo(tmp_path/'expected.db')
    with socket.socket() as s:
        s.bind(('127.0.0.1',0))
        port=s.getsockname()[1]
    env=dict(os.environ,PYTHONPATH=str(root/'src'),HOST='127.0.0.1',PORT=str(port),
             DATA_DIR=str(tmp_path/'http-data'),REGISTRATION_OPEN='true',
             MCP_ALLOWED_HOSTS=f'127.0.0.1:{port}',MCP_ALLOWED_ORIGINS=f'http://127.0.0.1:{port}')
    proc=subprocess.Popen([sys.executable,'-m','hogwarts.http_app'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    base=f'http://127.0.0.1:{port}'
    try:
        async with httpx.AsyncClient(trust_env=False) as http:
            for _ in range(100):
                if proc.poll() is not None:
                    raise AssertionError(proc.stderr.read().decode(errors='replace'))
                try:
                    r=await http.get(base+'/health')
                    if r.status_code==200:
                        break
                except httpx.TransportError:
                    pass
                await asyncio.sleep(.05)
            else:
                raise AssertionError('HTTP server did not become healthy')
            key=(await http.post(base+'/api/register',json={'name':'HTTP新生'})).json()['api_key']
            # Both slash forms avoid TLS-breaking redirects and query auth is supported.
            for path in ('/mcp','/mcp/'):
                async with httpx.AsyncClient(trust_env=False) as transport:
                    async with streamable_http_client(base+path+'?api_key='+key,http_client=transport) as (reader,writer,_):
                        async with ClientSession(reader,writer) as session:
                            await session.initialize()
                            assert {t.name for t in (await session.list_tools()).tools}==set(TOOLS)
                            assert (await session.call_tool('time_set',{})).isError
            async with httpx.AsyncClient(headers=headers(key),trust_env=False) as transport:
                async with streamable_http_client(base+'/mcp/',http_client=transport) as (reader,writer,_):
                    async with ClientSession(reader,writer) as session:
                        await session.initialize()
                        for step in expected:
                            result=await session.call_tool(step['tool'],step['arguments'])
                            actual=json.loads(result.content[0].text)
                            assert actual['ok'] and actual['time']==step['response']['time'],actual
                        status=json.loads((await session.call_tool('check_status')).content[0].text)['result']
                        assert status['name']=='HTTP新生'
                        assert status['house_points']==-3 and status['violations']
            browser=await http.get(base+'/api/state',headers=headers(key))
            assert browser.json()['status']['result']['house_points']==-3
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        proc.stderr.close()
