"""Local administrator command: create, rotate or revoke a team account."""
import argparse
import hashlib
import os
import secrets
from pathlib import Path

from .access import AccessConfig, Account


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path('data/access.json'))
    parser.add_argument('--user', required=True)
    parser.add_argument('--workspace', default='default')
    parser.add_argument('--role', choices=['viewer', 'contributor', 'reviewer', 'admin'], default='viewer')
    parser.add_argument('--rotate', action='store_true')
    parser.add_argument('--disable', action='store_true')
    args = parser.parse_args()
    config = AccessConfig.model_validate_json(args.config.read_text(encoding='utf-8')) if args.config.exists() else None
    users = config.users if config else []
    current = next((u for u in users if (u.user_id, u.workspace) == (args.user, args.workspace)), None)
    if current and not (args.rotate or args.disable):
        parser.error('Account exists; use --rotate or --disable explicitly')
    if not current and args.disable:
        parser.error('Account does not exist')
    if args.rotate and args.disable:
        parser.error('Choose either --rotate or --disable')
    token = secrets.token_urlsafe(32)
    account = (current.model_copy(update={'enabled': False}) if args.disable else
               Account(user_id=args.user, workspace=args.workspace, role=args.role,
                       token_sha256=hashlib.sha256(token.encode()).hexdigest()))
    users = [u for u in users if (u.user_id, u.workspace) != (args.user, args.workspace)] + [account]
    config = AccessConfig.model_validate({**(config.model_dump() if config else {}), 'users': users})
    args.config.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.config.with_name(args.config.name + '.' + secrets.token_hex(6) + '.tmp')
    try:
        with temporary.open('x', encoding='utf-8') as file:
            file.write(config.model_dump_json(indent=2))
        os.replace(temporary, args.config)
    finally:
        temporary.unlink(missing_ok=True)
    print('Account disabled' if args.disable else f'Bearer token (shown once): {token}')
    print(f'Config: {args.config.resolve()}')


if __name__ == '__main__':
    main()
