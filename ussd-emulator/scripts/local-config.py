"""Emulator-local defaults. No other service's configuration is read."""
import http.client
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

config = Path(__file__).resolve().parents[1] / '.env'
values = {}
if config.exists():
    values = dict(line.split('=', 1) for line in config.read_text().splitlines()
                  if line and not line.startswith('#') and '=' in line)
if sys.argv[1] == 'init':
    for key, value in {'EMULATOR_PORT': '8090', 'DEFAULT_CALLBACK_URL': 'http://ussd:8080/ussd/callback/grapevine',
                       'DEFAULT_SERVICE_CODE': '*123#', 'LOCALHOST_ALIAS': 'host.docker.internal'}.items():
        values.setdefault(key, value)
    descriptor = os.open(config, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, 'w') as output:
        output.write(''.join(f'{key}={value}\n' for key, value in values.items()))
    config.chmod(0o600)
elif sys.argv[1] == 'ready':
    port = values.get('EMULATOR_PORT', '8090')
    for _ in range(90):
        try:
            with urllib.request.urlopen(f'http://localhost:{port}/actuator/health', timeout=2) as response:
                if response.status == 200:
                    print(f'USSD emulator is ready at http://localhost:{port}')
                    break
        except (urllib.error.URLError, OSError, http.client.HTTPException):
            pass
        time.sleep(1)
    else:
        raise SystemExit('Emulator did not become healthy. Inspect docker compose logs in ussd-emulator/.')
else:
    raise SystemExit('Expected init or ready')
