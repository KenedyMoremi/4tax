#!/usr/bin/env python3
"""Check the real interfaces without creating owners or business records."""
import json
import os
from pathlib import Path
import secrets
import urllib.error
import urllib.request
import uuid
import xml.etree.ElementTree as ET

config = dict(line.split('=', 1) for line in (Path(__file__).resolve().parents[1] / '.env').read_text().splitlines()
              if line and not line.startswith('#') and '=' in line)
base = os.environ.get('USSD_URL', 'http://localhost:' + config.get('USSD_PORT', '8080')).rstrip('/')
key = os.environ.get('GATEWAY_KEY', config['GATEWAY_KEY'])
for service in (config.get('AUTH_PUBLIC_URL', 'https://4tax-auth.vercel.app'), base):
    with urllib.request.urlopen(service.rstrip('/') + '/actuator/health', timeout=30) as response:
        assert json.load(response)['status'] == 'UP'
with urllib.request.urlopen(config.get('REGISTRATION_URL', 'https://4tax.vercel.app').rstrip('/') + '/api/v1/registration/options', timeout=30) as response:
    schema = json.load(response)
assert schema['schemaVersion'] == 2
assert [s['value'] for s in schema['sectors']] == ['transport', 'services', 'ecommerce', 'retail', 'agriculture']
assert schema['salaryPeriod'] == schema['turnoverPeriod'] == 'monthly'

for language in ('1', '2'):
    for sector in ('1', '2', '3', '4', '5'):
        session, mobile = str(uuid.uuid4()), '26658' + ''.join(str(secrets.randbelow(10)) for _ in range(6))
        for event, value in [('initial', ''), ('action', language), ('action', '1'), ('action', sector), ('abort', '')]:
            root = ET.Element('ussdAppRequest')
            for name, text in {'type': event, 'sessionId': session, 'msisdn': mobile, 'network': 'VOD',
                               'requestId': str(uuid.uuid4())}.items():
                ET.SubElement(root, name).text = text
            if event == 'action':
                ET.SubElement(root, 'name').text = 'nextStateAction'
                field = ET.SubElement(root, 'field')
                ET.SubElement(field, 'name').text = 'userResponse'
                ET.SubElement(field, 'value').text = value
            request = urllib.request.Request(base + '/ussd/callback/grapevine', data=ET.tostring(root),
                headers={'Content-Type': 'application/xml', 'X-Gateway-Key': key})
            with urllib.request.urlopen(request, timeout=30) as response:
                reply = ET.fromstring(response.read())
            assert len(reply.findtext('prompt')) <= 160
            assert reply.findtext('state') == ('End' if event == 'abort' else 'NextState')

request = urllib.request.Request(base + '/ussd/callback/grapevine', data=b'<invalid/>', headers={'Content-Type': 'application/xml'})
try:
    urllib.request.urlopen(request, timeout=30)
    raise AssertionError('Gateway accepted a request without a credential')
except urllib.error.HTTPError as error:
    assert error.code == 401
print('PASS: real auth/registration metadata, five sector menus in both languages, gateway authentication and XML callbacks. No owners or business records created.')
