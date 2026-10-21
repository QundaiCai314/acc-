"""Password hashes for administrator-provisioned accounts; no plaintext storage."""
import hashlib
import hmac
import secrets


ITERATIONS = 600_000
HASH_PATTERN = r'^pbkdf2_sha256\$600000\$[a-f0-9]{32}\$[a-f0-9]{64}$'


def hash_password(password: str) -> str:
    if not 12 <= len(password) <= 256:
        raise ValueError('Password must contain 12 to 256 characters')
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), ITERATIONS).hex()
    return f'pbkdf2_sha256${ITERATIONS}${salt}${digest}'


def verify_password(password: str, encoded: str | None) -> bool:
    # A missing account/hash still performs the same expensive operation.
    salt, expected = (encoded.split('$')[2:] if encoded else ('0' * 32, '0' * 64))
    actual = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), ITERATIONS).hex()
    return hmac.compare_digest(actual, expected) and encoded is not None
