#!/usr/bin/env python3
"""Exercise running Compose services using synthetic identities; never print credentials."""
import base64
import json
from pathlib import Path
import secrets
import urllib.error
import urllib.request
import uuid

config = dict(line.split('=', 1) for line in (Path(__file__).resolve().parents[1] / '.env').read_text().splitlines()
              if line and not line.startswith('#') and '=' in line)

def request(port, path, body, headers=None, content_type='application/json'):
    data = json.dumps(body).encode() if content_type == 'application/json' else body.encode()
    req = urllib.request.Request(f'http://localhost:{port}{path}', data=data,
                                 headers={'Content-Type': content_type, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()

class Journey:
    def __init__(self, mobile=None):
        self.mobile = mobile or '+2665' + ''.join(str(secrets.randbelow(10)) for _ in range(7))
        self.session = str(uuid.uuid4())
        self.last = None
        self.send('', 'START')

    def send(self, value, event='INPUT'):
        status, text = request(8080, '/ussd/callback/simulator', {
            'network': 'TEST', 'sessionId': self.session, 'mobileNumber': self.mobile,
            'event': event, 'input': value, 'requestId': str(uuid.uuid4())
        }, {'X-Gateway-Key': config['GATEWAY_KEY']})
        assert status == 200, f'Callback failed with status {status}'
        self.last = json.loads(text)
        assert len(self.last['message']) <= 160
        return self.last

    def steps(self, *answers):
        for answer in answers:
            self.send(answer)

    def confirmed(self):
        assert self.last['end'] is True, 'Journey did not finish'
        assert 'DEMO-' in self.last['message'], 'Registration was not confirmed'

transport = Journey()
transport.steps('1', '1', '1', 'DEMO0000000000001', 'DEMO123', '000000000001',
                'Synthetic Owner', 'Maseru', '2', '1', '087431', '087431')
transport.confirmed()

returning = Journey(transport.mobile)
returning.steps('1', '2', '087431', '1', '3', '2', 'Maseru market', '1',
                '000000000001', 'Synthetic Owner', '1')
returning.confirmed()

wellness = Journey()
wellness.steps('2', '1', '2', '2', '62123456', '4', '1,3,5', '08:00', '17:00',
               'Synthetic Salon', 'Ha Thetsane', '000000000002', 'Synthetic Owner',
               '1', '087431', '087431')
wellness.confirmed()

vendor = Journey()
vendor.steps('1', '1', '3', '1', 'Synthetic Vendor', 'Maseru market', '1',
             '000000000003', 'Synthetic Owner', '1', '087431', '087431')
vendor.confirmed()

status, text = request(9000, '/api/v1/clients', {'applicationName': 'Smoke test', 'scopes': ['owners:create', 'owners:login']})
assert status == 201, 'Public client generation failed'
client = json.loads(text)
basic = base64.b64encode(f"{client['clientId']}:{client['clientSecret']}".encode()).decode()
status, text = request(9000, '/oauth2/token', 'grant_type=client_credentials&scope=owners:create%20owners:login',
                       {'Authorization': f'Basic {basic}'}, 'application/x-www-form-urlencoded')
assert status == 200, 'Issued client could not authenticate'
application_token = json.loads(text)['access_token']
status, _ = request(8081, '/api/v1/businesses', {}, {'Authorization': f'Bearer {application_token}', 'Idempotency-Key': str(uuid.uuid4())})
assert status == 401, 'Business API accepted an application token with the wrong audience'
status, _ = request(8080, '/ussd/callback/simulator', {})
assert status == 401, 'Gateway allowed a missing credential'
status, text = request(8080, '/ussd/callback/grapevine',
    '<ussdAppRequest><msisdn>26658123456</msisdn><sessionId>xml-smoke</sessionId><network>VOD</network><type>initial</type></ussdAppRequest>',
    {'X-Gateway-Key': config['GATEWAY_KEY']}, 'application/xml')
assert status == 200 and '<state>NextState</state>' in text, 'XML callback failed'
status, _ = request(8080, '/ussd/callback/grapevine',
    "<!DOCTYPE x [<!ENTITY e SYSTEM 'file:///etc/passwd'>]><ussdAppRequest><type>&e;</type></ussdAppRequest>",
    {'X-Gateway-Key': config['GATEWAY_KEY']}, 'application/xml')
assert status == 400, 'XML callback accepted a DTD'
print('PASS: transport, wellness/Sesotho, vendors, authenticated Add business, public client issuance, token audience, gateway authentication and XML callbacks.')
