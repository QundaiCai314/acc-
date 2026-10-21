"""Password sign-in issues opaque eight-hour sessions stored as digests."""
import hashlib
import secrets
import sqlite3
import hmac
import time
from datetime import datetime, timezone
from contextlib import closing

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field, SecretStr
from starlette.concurrency import run_in_threadpool

from .access import team_mode, principal, Account
from .account_config import edit_accounts
from .models import StrictModel
from .passwords import hash_password, verify_password


router = APIRouter(prefix='/auth', tags=['authentication'])
SESSION_SECONDS = 8 * 60 * 60


class Login(StrictModel):
    user_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,64}$')
    workspace: str = Field(default='default', pattern=r'^[a-zA-Z0-9_-]{1,64}$')
    password: SecretStr = Field(min_length=1, max_length=256)


class Registration(StrictModel):
    user_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,64}$')
    workspace: str = Field(default='default', pattern=r'^[a-zA-Z0-9_-]{1,64}$')
    password: SecretStr = Field(min_length=12, max_length=256)


class PasswordChange(StrictModel):
    current_password: SecretStr = Field(min_length=1, max_length=256)
    password: SecretStr = Field(min_length=12, max_length=256)


class PasswordReset(Registration):
    reset_code: SecretStr = Field(min_length=1, max_length=256)


class MemberChange(StrictModel):
    user_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,64}$')
    action: str = Field(pattern=r'^(approve|reject|reset|disable|enable)$')
    role: str = Field(default='viewer', pattern=r'^(viewer|contributor|reviewer)$')


async def parse(request, model):
    if not team_mode.get():
        raise HTTPException(409, 'Account management requires team mode')
    try:
        return model.model_validate(await request.json())
    except ValueError:
        raise HTTPException(422, 'Invalid account fields; new passwords require 12 to 256 characters') from None


@router.get('/members')
def members(request: Request):
    if not team_mode.get():
        raise HTTPException(409, 'Account management requires team mode')
    workspace = principal.get().workspace
    with closing(request.app.state.store.connect()) as db:
        pending = db.execute('SELECT user_id, created_at FROM registration_requests WHERE workspace = ? ORDER BY created_at',
                             (workspace,)).fetchall()
    return {'members': [{**u.identity().model_dump(), 'enabled': u.enabled}
                        for u in request.state.access_config.users if u.workspace == workspace],
            'pending': [{'user_id': user, 'created_at': created} for user, created in pending]}


@router.post('/members')
async def manage_member(request: Request):
    change = await parse(request, MemberChange)
    actor = principal.get()
    def apply():
        with edit_accounts(request.state.access_path) as config:
            # Recheck authorization while holding the same lock used for mutations.
            if not any(u['user_id'] == actor.user_id and u['workspace'] == actor.workspace
                       and u['enabled'] and u['role'] == 'admin' for u in config['users']):
                raise HTTPException(403, 'Administrator role required')
            account = next((u for u in config['users'] if (u['user_id'], u['workspace']) ==
                            (change.user_id, actor.workspace)), None)
            store = request.app.state.store
            if change.action in ('approve', 'reject'):
                pending = store.registration(actor.workspace, change.user_id)
                if not pending or account:
                    raise HTTPException(409, 'Registration is no longer pending')
                if change.action == 'approve':
                    config['users'].append(Account(user_id=change.user_id, workspace=actor.workspace,
                        role=change.role, password_hash=pending[0],
                        token_sha256=hashlib.sha256(secrets.token_bytes(32)).hexdigest()).model_dump())
            else:
                if not account:
                    raise HTTPException(404, 'Member not found')
                if account['role'] == 'admin':
                    raise HTTPException(409, 'Manage administrator credentials using the server command')
                if change.action == 'reset':
                    if not account['enabled']:
                        raise HTTPException(409, 'Enable the member before issuing a reset code')
                    code = secrets.token_urlsafe(32)
                    account['reset_digest'] = hashlib.sha256(code.encode()).hexdigest()
                    account['reset_expires'] = time.time() + 1800
                else:
                    account['enabled'] = change.action == 'enable'
                    # Disable invalidates sessions and outstanding reset codes permanently.
                    if not account['enabled']:
                        account['token_sha256'] = hashlib.sha256(secrets.token_bytes(32)).hexdigest()
                        account['reset_digest'], account['reset_expires'] = None, 0
        if change.action in ('approve', 'reject'):
            store.remove_registration(actor.workspace, change.user_id)
        return {'status': change.action, **({'reset_code': code, 'expires_in': 1800}
                                           if change.action == 'reset' else {})}
    return await run_in_threadpool(apply)


@router.post('/password')
async def change_password(request: Request):
    details = await parse(request, PasswordChange)
    actor = principal.get()
    def apply():
        with edit_accounts(request.state.access_path) as config:
            account = next((u for u in config['users'] if (u['user_id'], u['workspace']) ==
                            (actor.user_id, actor.workspace)), None)
            if not account or not account['enabled'] or not verify_password(
                    details.current_password.get_secret_value(), account['password_hash']):
                raise HTTPException(400, 'Current password is incorrect')
            account['password_hash'] = hash_password(details.password.get_secret_value())
            account['reset_digest'], account['reset_expires'] = None, 0
        return {'status': 'password_changed', 'sign_in_required': True}
    return await run_in_threadpool(apply)


@router.post('/reset-password')
async def reset_password(request: Request):
    details = await parse(request, PasswordReset)
    key = f'reset:{details.workspace}:{details.user_id}'
    if not await run_in_threadpool(request.app.state.store.consume_rate, key, 5):
        raise HTTPException(429, 'Reset attempt limit reached', headers={'Retry-After': '60'})
    def apply():
        with edit_accounts(request.state.access_path) as config:
            account = next((u for u in config['users'] if (u['user_id'], u['workspace']) ==
                            (details.user_id, details.workspace)), None)
            digest = hashlib.sha256(details.reset_code.get_secret_value().encode()).hexdigest()
            if (not account or not account['enabled'] or account['reset_expires'] <= time.time()
                    or not hmac.compare_digest(account['reset_digest'] or '', digest)):
                raise HTTPException(400, 'Invalid or expired reset code')
            account['password_hash'] = hash_password(details.password.get_secret_value())
            account['reset_digest'], account['reset_expires'] = None, 0
        return {'status': 'password_reset', 'sign_in_required': True}
    return await run_in_threadpool(apply)


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


@router.post('/register', status_code=202)
async def register(request: Request):
    if not team_mode.get():
        raise HTTPException(409, 'Registration requires team mode')
    try:
        details = Registration.model_validate(await request.json())
    except ValueError:
        raise HTTPException(422, 'Provide a valid account, workspace and password of at least 12 characters') from None
    key = f'register:{details.workspace}:{details.user_id}'
    if not await run_in_threadpool(request.app.state.store.consume_rate, key, 3):
        raise HTTPException(429, 'Registration attempt limit reached', headers={'Retry-After': '60'})
    if any(u.user_id == details.user_id and u.workspace == details.workspace
           for u in request.state.access_config.users):
        raise HTTPException(409, 'Account already exists; contact the workspace administrator')
    if not any(u.workspace == details.workspace and u.role == 'admin' and u.enabled
               for u in request.state.access_config.users):
        raise HTTPException(409, 'Workspace is not accepting registration; contact its administrator')
    password_hash = await run_in_threadpool(hash_password, details.password.get_secret_value())
    try:
        await run_in_threadpool(request.app.state.store.create_registration, details.workspace,
                                details.user_id, password_hash, datetime.now(timezone.utc).isoformat())
    except sqlite3.IntegrityError:
        raise HTTPException(409, 'Registration is already awaiting approval') from None
    return {'status': 'pending_approval', 'user_id': details.user_id, 'workspace': details.workspace}


@router.post('/logout')
def logout(request: Request):
    digest = request.state.auth_session
    if digest:
        request.app.state.store.revoke_auth_session(digest)
    # Personal tokens are administrator-managed; disconnecting does not revoke them.
    return {'session_revoked': bool(digest)}
