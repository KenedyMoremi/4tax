"""USSD-local configuration and application enrolment with the authoritative auth service."""
import http.client
import base64
import json
import os
from pathlib import Path
import secrets
import sys
import time
import urllib.error
import urllib.request
import urllib.parse

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

def wait_for(url):
    for _ in range(90):
        try:
            with urllib.request.urlopen(url + '/actuator/health', timeout=2) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, OSError, http.client.HTTPException):
            pass
        time.sleep(1)
    raise SystemExit('Dependency not healthy. Start auth first, then inspect service-local Compose logs.')

def client_is_registered(auth, config):
    client_id = config.get('USSD_CLIENT_ID')
    client_secret = config.get('USSD_CLIENT_SECRET')
    if not client_id or not client_secret:
        return False
    credentials = base64.b64encode(f'{client_id}:{client_secret}'.encode()).decode()
    body = urllib.parse.urlencode({'grant_type': 'client_credentials', 'scope': 'owners:create owners:login'}).encode()
    request = urllib.request.Request(auth + '/oauth2/token', data=body,
        headers={'Content-Type': 'application/x-www-form-urlencoded', 'Authorization': 'Basic ' + credentials})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status == 200
    except urllib.error.HTTPError as error:
        if error.code in (400, 401, 403):
            return False
        raise SystemExit('Auth could not validate the application credentials. Inspect auth service health.')
    except (urllib.error.URLError, OSError, http.client.HTTPException):
        raise SystemExit('Auth could not validate the application credentials. Inspect auth service health.')

values = read()
if sys.argv[1] == 'init':
    for key in ('REDIS_PASSWORD', 'GATEWAY_KEY', 'STATE_SECRET'):
        values.setdefault(key, secrets.token_urlsafe(32))
    for key, value in {'USSD_PORT': '8080', 'SPRING_PROFILES_ACTIVE': 'dev',
                       'AUTH_PUBLIC_URL': 'http://localhost:9000', 'AUTH_URL': 'http://auth:9000',
                       'AUTH_ISSUER': 'http://localhost:9000', 'AUTH_JWKS_URL': 'http://auth:9000/oauth2/jwks',
                       'REGISTRATION_URL': 'http://registration-api:8081'}.items():
        values.setdefault(key, value)
    write(values)
elif sys.argv[1] == 'provision':
    auth = values.get('AUTH_PUBLIC_URL', 'http://localhost:9000')
    wait_for(auth)
    if not client_is_registered(auth, values):
        body = json.dumps({'applicationName': '4Tax USSD', 'scopes': ['owners:create', 'owners:login']}).encode()
        request = urllib.request.Request(auth + '/api/v1/clients', data=body, headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=10) as response:
            client = json.load(response)
        values['USSD_CLIENT_ID'] = client['clientId']
        values['USSD_CLIENT_SECRET'] = client['clientSecret']
        write(values)
elif sys.argv[1] == 'ready':
    wait_for(f"http://localhost:{values.get('USSD_PORT', '8080')}")
else:
    raise SystemExit('Expected init, provision or ready')
