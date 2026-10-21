"""Small-team authentication with personal tokens and revocable login sessions."""
import hashlib
import ipaddress
from contextvars import ContextVar
from pathlib import Path
from typing import Literal

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer
from pydantic import Field, model_validator
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from .models import StrictModel
from .passwords import HASH_PATTERN


class Principal(StrictModel):
    user_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,64}$')
    workspace: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,64}$')
    role: Literal['viewer', 'contributor', 'reviewer', 'admin']


class Account(Principal):
    token_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    password_hash: str | None = Field(default=None, pattern=HASH_PATTERN)
    enabled: bool = True
    reset_digest: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    reset_expires: float = 0

    def credential_digest(self) -> str:
        return hashlib.sha256((self.token_sha256 + ':' + (self.password_hash or '')).encode()).hexdigest()

    def identity(self) -> Principal:
        return Principal(user_id=self.user_id, workspace=self.workspace, role=self.role)


class AccessConfig(StrictModel):
    users: list[Account] = Field(min_length=1, max_length=1000)
    requests_per_minute: int = Field(default=120, ge=1, le=10000)
    model_requests_per_minute: int = Field(default=10, ge=1, le=100)

    @model_validator(mode='after')
    def unique_users(self):
        if len({u.token_sha256 for u in self.users}) != len(self.users):
            raise ValueError('Duplicate token digest')
        if len({(u.workspace, u.user_id) for u in self.users}) != len(self.users):
            raise ValueError('Duplicate user in workspace')
        return self


LOCAL = Principal(user_id='local', workspace='default', role='admin')
principal: ContextVar[Principal] = ContextVar('principal', default=LOCAL)
team_mode: ContextVar[bool] = ContextVar('team_mode', default=False)


def attributed(body: dict) -> dict:
    actor = principal.get()
    result = {**body, 'workspace_id': actor.workspace, 'created_by': actor.user_id}
    if team_mode.get():
        for field in ('reviewer', 'curator'):
            if field in result:
                result[field] = actor.user_id
    return result


def authorize(request: Request, credentials=Depends(HTTPBearer(auto_error=False))):
    if not team_mode.get():
        return
    route = request.scope['route'].path
    if route in ('/auth/me', '/auth/login', '/auth/logout', '/auth/register', '/auth/reset-password', '/auth/password'):
        return
    role = principal.get().role
    if route.startswith('/auth/') and role != 'admin':
        raise HTTPException(403, 'Administrator role required')
    if route.startswith('/integrations') and role != 'admin':
        raise HTTPException(403, 'Administrator role required')
    if route == '/spatial/runs/{run_id}' and role == 'viewer':
        raise HTTPException(403, 'Run logs require contributor access')
    if request.method in ('GET', 'HEAD', 'OPTIONS'):
        return
    if route.endswith(('/review', '/withdraw', '/decision', '/claim', '/release')):
        if role not in ('reviewer', 'admin'):
            raise HTTPException(403, 'Reviewer role required')
    elif route.endswith(('/query', '/ask', '/route', '/reason', '/transform')):
        return
    elif role not in ('contributor', 'reviewer', 'admin'):
        raise HTTPException(403, 'Contributor role required')


class AccessMiddleware:
    def __init__(self, app, mode: str, config_path: Path | None, max_body_bytes=8_000_000):
        self.app, self.mode, self.config_path = app, mode, config_path
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        if scope['path'] == '/health' and scope['method'] == 'GET':
            return await self.app(scope, receive, send)
        headers = {k.lower(): v for k, v in scope['headers']}
        actor = LOCAL
        login = scope['path'] == '/auth/login' and scope['method'] == 'POST'
        registration = scope['path'] in ('/auth/register', '/auth/reset-password') and scope['method'] == 'POST'
        scope.setdefault('state', {})['auth_session'] = None
        if self.mode == 'team':
            # Reload per request so revocations apply across all workers without restarting.
            try:
                config = await run_in_threadpool(
                    lambda: AccessConfig.model_validate_json(self.config_path.read_text(encoding='utf-8')))
            except (OSError, ValueError):
                return await JSONResponse({'detail': 'Access configuration unavailable'}, 503)(scope, receive, send)
            store = scope['app'].state.store
            scope['state']['access_config'] = config
            scope['state']['access_path'] = self.config_path
            if login or registration:
                scope['state']['access_config'] = config
                # Use the ASGI peer, never an untrusted forwarded header.
                peer = (scope.get('client') or ('unknown', 0))[0]
                bucket, limit = f'login-ip:{peer}', 30
            else:
                token = headers.get(b'authorization', b'').decode('latin-1')
                digest = hashlib.sha256(token[7:].encode()).hexdigest() if token.startswith('Bearer ') else ''
                account = next((u for u in config.users if u.enabled and u.token_sha256 == digest), None)
                if account is None and digest:
                    session = await run_in_threadpool(store.auth_session, digest)
                    if session:
                        account = next((u for u in config.users if u.enabled and
                                        (u.user_id, u.workspace, u.credential_digest()) == session), None)
                        if account:
                            scope['state']['auth_session'] = digest
                if account is None:
                    return await JSONResponse({'detail': 'Valid bearer token required'}, 401,
                                              headers={'WWW-Authenticate': 'Bearer', 'Cache-Control': 'no-store'})(scope, receive, send)
                actor = account.identity()
                expensive = scope['path'].endswith(('/analyze', '/ask', '/probe', '/references/search'))
                limit = config.model_requests_per_minute if expensive else config.requests_per_minute
                bucket = f'{actor.workspace}:{actor.user_id}:{"model" if expensive else "api"}'
            if not await run_in_threadpool(store.consume_rate, bucket, limit):
                return await JSONResponse({'detail': 'Request limit reached'}, 429,
                                          headers={'Retry-After': '60'})(scope, receive, send)
        else:
            peer = (scope.get('client') or ('', 0))[0]
            try:
                loopback = ipaddress.ip_address(peer).is_loopback
            except ValueError:
                loopback = peer == 'testclient'
            if not loopback:
                return await JSONResponse({'detail': 'Use team mode for remote access'}, 403)(scope, receive, send)
        # Bound received bytes even when Content-Length is absent or inaccurate.
        body = bytearray()
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            body.extend(message.get('body', b''))
            if len(body) > (4096 if scope['path'].startswith('/auth/') else self.max_body_bytes):
                return await JSONResponse({'detail': 'Request body exceeds size limit'}, 413)(scope, receive, send)
            if not message.get('more_body', False):
                break
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
            return await receive()

        async def private_send(message):
            if message['type'] == 'http.response.start':
                message['headers'] = [*message.get('headers', []), (b'cache-control', b'no-store'),
                                      (b'x-content-type-options', b'nosniff')]
            await send(message)

        token = principal.set(actor)
        mode_token = team_mode.set(self.mode == 'team')
        try:
            await self.app(scope, bounded_receive, private_send)
        finally:
            principal.reset(token)
            team_mode.reset(mode_token)
