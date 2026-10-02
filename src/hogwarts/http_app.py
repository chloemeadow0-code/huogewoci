"""Credential-based browser and HTTP MCP entry point, local-only by default."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from .auth import Accounts, current_identity, identity
from .engine import Game, LOCK, TOOLS
from .rules import RuleError, require
from .server import create_server

STATIC = Path(__file__).parent / 'web'


def create_http_app(data_dir=None):
    data_dir = Path(data_dir or os.environ.get('DATA_DIR', 'data')).resolve()
    accounts = Accounts(data_dir)
    db_path = data_dir / 'hogwarts.db'
    game = Game(db_path)
    game.close()

    def action(name, args, who):
        with LOCK:
            game = Game(db_path, **who)
            try:
                return game.call(name, **args)
            finally:
                game.close()

    async def health(request):
        try:
            def check():
                with accounts.connect() as db:
                    db.execute('SELECT 1 FROM accounts LIMIT 1').fetchone()
                with LOCK:
                    game = Game(db_path)
                    try:
                        game.db.execute('SELECT 1').fetchone()
                    finally:
                        game.close()
            await run_in_threadpool(check)
            return JSONResponse({'status': 'ok', 'service': 'hogwarts', 'tools': len(TOOLS)})
        except Exception:
            return JSONResponse({'status': 'unavailable'}, status_code=503)

    async def document(request):
        return FileResponse(STATIC / 'index.html')

    async def manual(request):
        return FileResponse(STATIC / 'manual.html')

    async def body(request):
        payload = await request.json()
        require(isinstance(payload, dict), '请求必须是 JSON 对象。')
        return payload

    async def register(request):
        if os.environ.get('REGISTRATION_OPEN', 'false').lower() not in ('true','1','yes'):
            return JSONResponse({'error': '注册已关闭，请使用已有凭证。'}, status_code=403)
        try:
            payload = await body(request)
            require(set(payload) == {'name'}, '注册只接受 name。')
            token, who = await run_in_threadpool(accounts.register, payload['name'])
            await run_in_threadpool(action, 'check_status', {}, who)
            return JSONResponse({'api_key': token, 'name': who['player_name'], 'mcp_path': '/mcp/'}, status_code=201)
        except (RuleError, ValueError, TypeError):
            return JSONResponse({'error': '请使用 2～24 字的名字。'}, status_code=400)

    async def state(request):
        who = identity()
        def view():
            with LOCK:
                status = action('check_status', {}, who)
                scene = action('look', {}, who)
                schedule = action('check_schedule', {}, who)
                inventory = action('check_inventory', {}, who)
                game = Game(db_path, **who)
                try:
                    peers = [{'name': r['player']['name'], 'house': r['player']['house'],
                              'location': r['player']['location']}
                             for r in game.state.get('players', {}).values()]
                finally:
                    game.close()
                return {'status': status, 'scene': scene, 'schedule': schedule, 'inventory': inventory, 'students': peers}
        return JSONResponse(await run_in_threadpool(view))

    async def perform(request):
        try:
            payload = await body(request)
            require(set(payload) <= {'tool', 'arguments'}, '动作只接受 tool 和 arguments。')
            tool, args = payload.get('tool'), payload.get('arguments', {})
            require(tool in TOOLS and isinstance(args, dict), '不支持的玩家动作。')
            result = await run_in_threadpool(action, tool, args, identity())
            return JSONResponse(result, status_code=200 if result['ok'] else 400)
        except (RuleError, ValueError, TypeError):
            return JSONResponse({'ok': False, 'error': '无效的玩家动作。'}, status_code=400)

    hosts = ['127.0.0.1', '127.0.0.1:*', 'localhost', 'localhost:*', '[::1]', '[::1]:*']
    hosts += [h.strip() for h in os.environ.get('MCP_ALLOWED_HOSTS', '').split(',') if h.strip()]
    origins = ['http://127.0.0.1:*', 'http://localhost:*', 'http://[::1]:*']
    origins += [h.strip() for h in os.environ.get('MCP_ALLOWED_ORIGINS', '').split(',') if h.strip()]
    mcp = create_server(db_path, identity_provider=identity, stateless_http=True, json_response=True,
                        streamable_http_path='/', host='127.0.0.1',
                        transport_security=TransportSecuritySettings(
                            enable_dns_rebinding_protection=True, allowed_hosts=hosts, allowed_origins=origins))
    mcp_app = mcp.streamable_http_app()

    @asynccontextmanager
    async def lifespan(app):
        async with mcp.session_manager.run():
            yield

    app = Starlette(routes=[Route('/health', health), Route('/healthz', health),
                           Route('/', document), Route('/register', document), Route('/play', document),
                           Route('/manual', manual), Route('/api/register', register, methods=['POST']),
                           Route('/api/state', state), Route('/api/action', perform, methods=['POST']),
                           Mount('/static', StaticFiles(directory=STATIC)), Mount('/mcp', mcp_app)], lifespan=lifespan)

    class PlayerBoundary:
        def __init__(self, inner):
            self.inner = inner

        async def __call__(self, scope, receive, send):
            if scope['type'] != 'http':
                return await self.inner(scope, receive, send)
            if scope['path'] == '/mcp':
                scope = dict(scope, path='/mcp/', raw_path=b'/mcp/')
            request = Request(scope)
            path = scope['path']
            host = request.headers.get('host', '')
            valid_host = any(host == value or (value.endswith(':*') and host.startswith(value[:-1]))
                             for value in hosts)
            if not valid_host and path not in ('/health','/healthz'):
                return await JSONResponse({'error': '未配置此域名。'}, status_code=421)(scope, receive, send)
            who = None
            if path.startswith('/mcp/') or path in ('/api/state','/api/action'):
                auth = request.headers.get('authorization', '')
                key = auth[7:].strip() if auth.lower().startswith('bearer ') else request.query_params.get('api_key')
                who = await run_in_threadpool(accounts.lookup, key)
                if not who:
                    return await JSONResponse({'error': '缺少或无效的 Hogwarts 凭证。'}, status_code=401)(scope, receive, send)
            origin = request.headers.get('origin')
            host = request.headers.get('host', '')
            if origin and origin not in (f'http://{host}', f'https://{host}', *origins):
                return await JSONResponse({'error': '不允许此来源。'}, status_code=403)(scope, receive, send)
            if request.method == 'POST' and path.startswith('/api/'):
                if not request.headers.get('content-type','').lower().startswith('application/json'):
                    return await JSONResponse({'error': '需要 application/json。'}, status_code=415)(scope, receive, send)
            if request.method == 'POST':
                chunks, size = [], 0
                while True:
                    message = await receive()
                    if message['type'] == 'http.disconnect':
                        return
                    size += len(message.get('body', b''))
                    if size > 65536:
                        return await JSONResponse({'error': '请求过大。'}, status_code=413)(scope, receive, send)
                    chunks.append(message)
                    if not message.get('more_body', False):
                        break
                async def buffered_receive():
                    return chunks.pop(0) if chunks else await receive()
                receiver = buffered_receive
            else:
                receiver = receive
            token = current_identity.set(who)
            async def safe_send(message):
                if message['type'] == 'http.response.start':
                    message = dict(message)
                    message['headers'] = list(message.get('headers', [])) + [
                        (b'cache-control', b'no-store'), (b'referrer-policy', b'no-referrer'),
                        (b'x-content-type-options', b'nosniff'),
                        (b'content-security-policy', b"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'")]
                await send(message)
            try:
                await self.inner(scope, receiver, safe_send)
            finally:
                current_identity.reset(token)

    return PlayerBoundary(app)


def main():
    import uvicorn
    host = os.environ.get('HOST','127.0.0.1')
    if host not in ('127.0.0.1','localhost','::1') and not os.environ.get('MCP_ALLOWED_HOSTS','').strip():
        raise RuntimeError('公开监听前请配置 MCP_ALLOWED_HOSTS。')
    uvicorn.run(create_http_app(), host=host,
                port=int(os.environ.get('PORT','8080')), workers=1, access_log=False)


if __name__ == '__main__':
    main()
