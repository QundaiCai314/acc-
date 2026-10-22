"""Local administrator command: create, rotate or revoke a team account."""
import argparse
import getpass
import hashlib
import secrets
from pathlib import Path

from .access import AccessConfig, Account
from .account_config import edit_accounts
from .passwords import hash_password


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path('data/access.json'))
    parser.add_argument('--user', required=True)
    parser.add_argument('--workspace', default='default')
    parser.add_argument('--role', choices=['viewer', 'contributor', 'reviewer', 'admin'])
    parser.add_argument('--rotate', action='store_true')
    parser.add_argument('--disable', action='store_true')
    parser.add_argument('--set-password', action='store_true', help='Set/reset a password using a hidden prompt')
    args = parser.parse_args()
    with edit_accounts(args.config) as body:
        config = AccessConfig.model_validate(body) if body['users'] else None
        users = config.users if config else []
        current = next((u for u in users if (u.user_id, u.workspace) == (args.user, args.workspace)), None)
        if current and not (args.rotate or args.disable or args.set_password):
            parser.error('Account exists; use --rotate, --disable or --set-password explicitly')
        if not current and args.disable:
            parser.error('Account does not exist')
        if args.disable and (args.rotate or args.set_password):
            parser.error('--disable cannot be combined with --rotate or --set-password')
        password_hash = current.password_hash if current else None
        if args.set_password:
            password = getpass.getpass('New password (12-256 characters): ')
            if password != getpass.getpass('Confirm password: '):
                parser.error('Passwords do not match; configuration unchanged')
            try:
                password_hash = hash_password(password)
            except ValueError as exc:
                parser.error(str(exc))
            del password
        token = secrets.token_urlsafe(32) if not current or args.rotate else None
        account = (current.model_copy(update={
                       'enabled': False, 'token_sha256': hashlib.sha256(secrets.token_bytes(32)).hexdigest(),
                       'reset_digest': None, 'reset_expires': 0}) if args.disable else
                   Account(user_id=args.user, workspace=args.workspace,
                           role=args.role or (current.role if current else 'viewer'),
                           token_sha256=hashlib.sha256(token.encode()).hexdigest() if token else current.token_sha256,
                           password_hash=password_hash, enabled=True if token else current.enabled))
        users = [u for u in users if (u.user_id, u.workspace) != (args.user, args.workspace)] + [account]
        body['users'] = [u.model_dump() for u in users]
    if args.disable:
        print('Account disabled')
    elif token:
        print(f'Bearer token (shown once): {token}')
    if args.set_password:
        print('Password set; existing login sessions are invalidated')
    print(f'Config: {args.config.resolve()}')


if __name__ == '__main__':
    main()
