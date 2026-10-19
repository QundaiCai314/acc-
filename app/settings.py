"""Read local provider credentials without copying them into responses or process logs."""
import json
import os
from pathlib import Path


class ConfigurationError(RuntimeError):
    pass


def setting(name: str, default: str = '') -> str:
    if name in os.environ:
        return os.environ[name]
    path = Path(os.getenv('DISASTER_PROVIDER_CONFIG', 'data/provider-settings.json'))
    if not path.exists():
        return default
    try:
        value = json.loads(path.read_text(encoding='utf-8')).get(name, default)
        if not isinstance(value, str):
            raise ValueError('Configuration values must be strings')
        return value
    except (OSError, ValueError, AttributeError) as exc:
        raise ConfigurationError('Provider configuration is unreadable or invalid') from exc
