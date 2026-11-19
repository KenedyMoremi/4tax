"""Configuration and readiness for the independently run synthetic registration mock."""
import http.client
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

CONFIG = Path(__file__).resolve().parents[1] / '.env'
values = {}
if CONFIG.exists():
    values = dict(line.split('=', 1) for line in CONFIG.read_text().splitlines()
                  if line and not line.startswith('#') and '=' in line)
if sys.argv[1] == 'init':
    for key, value in {'MOCK_PORT': '8081', 'AUTH_ISSUER': 'http://localhost:9000',
                       'AUTH_JWKS_URL': 'http://auth:9000/oauth2/jwks'}.items():
        values.setdefault(key, value)
    descriptor = os.open(CONFIG, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, 'w') as output:
        output.write(''.join(f'{key}={value}\n' for key, value in values.items()))
    CONFIG.chmod(0o600)
elif sys.argv[1] == 'ready':
    for _ in range(90):
        try:
            with urllib.request.urlopen(f"http://localhost:{values.get('MOCK_PORT', '8081')}/actuator/health", timeout=2) as response:
                if response.status == 200:
                    break
        except (urllib.error.URLError, OSError, http.client.HTTPException):
            pass
        time.sleep(1)
    else:
        raise SystemExit('Registration mock did not become healthy; inspect its service-local Compose logs.')
else:
    raise SystemExit('Expected init or ready')
