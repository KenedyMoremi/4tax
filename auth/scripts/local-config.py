"""Auth-local configuration; raw secrets are never printed."""
import http.client
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request

CONFIG = Path(__file__).resolve().parents[1] / '.env'

def read():
    if not CONFIG.exists():
        return {}
    return dict(line.split('=', 1) for line in CONFIG.read_text().splitlines()
                if line and not line.startswith('#') and '=' in line)

def write(values):
    descriptor = os.open(CONFIG, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, 'w') as output:
        output.write(''.join(f'{key}={value}\n' for key, value in values.items()))
    CONFIG.chmod(0o600)

values = read()
if sys.argv[1] == 'init':
    for key in ('POSTGRES_PASSWORD', 'KEYSTORE_PASSWORD'):
        values.setdefault(key, secrets.token_urlsafe(32))
    for key, value in {'AUTH_PORT': '9000', 'AUTH_ISSUER': 'http://localhost:9000',
                       'AUTH_DATA_VOLUME': 'fourtax-auth-data', 'AUTH_KEY_VOLUME': 'fourtax-auth-signing-keys'}.items():
        values.setdefault(key, value)
    write(values)
elif sys.argv[1] == 'volumes':
    for name in ('AUTH_DATA_VOLUME', 'AUTH_KEY_VOLUME'):
        subprocess.run(['docker', 'volume', 'create', values[name]], check=True, stdout=subprocess.DEVNULL)
elif sys.argv[1] == 'ready':
    for _ in range(90):
        try:
            with urllib.request.urlopen(f"http://localhost:{values.get('AUTH_PORT', '9000')}/actuator/health", timeout=2) as response:
                if response.status == 200:
                    break
        except (urllib.error.URLError, OSError, http.client.HTTPException):
            pass
        time.sleep(1)
    else:
        raise SystemExit('Auth did not become healthy; inspect docker compose logs in auth/.')
else:
    raise SystemExit('Expected init, volumes or ready')
