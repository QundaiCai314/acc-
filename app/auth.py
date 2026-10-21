"""Password sign-in issues opaque eight-hour sessions stored as digests."""
import hashlib
import secrets
import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field, SecretStr
from starlette.concurrency import run_in_threadpool

from .access import team_mode
from .models import StrictModel
from .passwords import verify_password


router = APIRouter(prefix='/auth', tags=['authentication'])
SESSION_SECONDS = 8 * 60 * 60


class Login(StrictModel):
    user_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,64}$')
    workspace: str = Field(default='default', pattern=r'^[a-zA-Z0-9_-]{1,64}$')
    password: SecretStr = Field(min_length=1, max_length=256)


@router.post('/login')
async def login(request: Request):
    if not team_mode.get():
        raise HTTPException(409, 'Password login requires team mode; use the local connection option')
    try:
        credentials = Login.model_validate(await request.json())
    except ValueError:
        # Validation errors must never echo password-bearing input.
        raise HTTPException(422, 'Provide a valid user_id, workspace and password') from None
    store = request.app.state.store
    key = f'login-account:{credentials.workspace}:{credentials.user_id}'
    if not await run_in_threadpool(store.consume_rate, key, 10):
        raise HTTPException(429, 'Login attempt limit reached', headers={'Retry-After': '60'})
    account = next((u for u in request.state.access_config.users
                    if (u.user_id, u.workspace) == (credentials.user_id, credentials.workspace)), None)
    valid = await run_in_threadpool(verify_password, credentials.password.get_secret_value(),
                                   account.password_hash if account else None)
    if not valid or not account or not account.enabled:
        raise HTTPException(401, 'Invalid account or password', headers={'WWW-Authenticate': 'Bearer'})
    token = secrets.token_urlsafe(32)
    expires = time.time() + SESSION_SECONDS
    await run_in_threadpool(store.create_auth_session, hashlib.sha256(token.encode()).hexdigest(),
                            account.user_id, account.workspace, account.credential_digest(), expires)
    return {'access_token': token, 'token_type': 'bearer',
            'expires_at': datetime.fromtimestamp(expires, timezone.utc).isoformat(),
            'identity': account.identity()}


@router.post('/logout')
def logout(request: Request):
    digest = request.state.auth_session
    if digest:
        request.app.state.store.revoke_auth_session(digest)
    # Personal tokens are administrator-managed; disconnecting does not revoke them.
    return {'session_revoked': bool(digest)}
