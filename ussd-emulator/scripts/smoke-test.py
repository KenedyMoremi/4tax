#!/usr/bin/env python3
"""Test the running emulator against a real USSD callback using synthetic subscribers."""
from datetime import datetime, timezone
import getpass
import json
import os
import urllib.error
import urllib.request
import urllib.parse
import uuid

base = os.environ.get('EMULATOR_URL', 'http://localhost:8090').rstrip('/')
key = os.environ.get('GATEWAY_KEY') or getpass.getpass('USSD gateway key (not saved): ')

def api(path, body=None):
    request = urllib.request.Request(base + '/api/emulator/' + path,
        data=None if body is None else json.dumps(body).encode(),
        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=40) as response:
        return json.load(response)

config = api('config')
callback = os.environ.get('USSD_CALLBACK_URL', config['callbackUrl'])

def identity(mnc='01'):
    return api('identities', {'count': 1, 'prefix': '58', 'mnc': mnc})[0]

class Call:
    def __init__(self, subscriber=None, target=callback, include_id=True, gateway_key=key):
        self.subscriber = subscriber or identity()
        self.session = str(uuid.uuid4())
        self.target = target
        self.include_id = include_id
        self.key = gateway_key
        self.last_request = None
        self.last = self.send('START')

    def send(self, event, value=''):
        self.last_request = {'callbackUrl': self.target, 'gatewayHeader': 'X-Gateway-Key', 'gatewayKey': self.key,
            'subscriber': self.subscriber, 'sessionId': self.session, 'requestId': str(uuid.uuid4()),
            'serviceCode': '*123#', 'event': event, 'input': value, 'numberFormat': 'INTERNATIONAL',
            'includeRequestId': self.include_id, 'timestamp': datetime.now(timezone.utc).isoformat(), 'timeoutSeconds': 8}
        self.last = api('exchanges', self.last_request)
        return self.last

    def steps(self, *answers):
        for answer in answers:
            result = self.send('INPUT', answer)
            assert result['errorCode'] is None, (result['errorCode'], result['errorMessage'])

    def confirmed(self):
        assert self.last['state'] == 'End' and 'DEMO-' in self.last['prompt'], 'Entity was not confirmed'

initial = Call()
assert initial.last['errorCode'] is None
assert f"<imsi>{initial.subscriber['imsi']}</imsi>" in initial.last['requestXml']
replay = api('exchanges', initial.last_request)
assert replay['requestXml'] == initial.last['requestXml'] and replay['prompt'] == initial.last['prompt']
initial.send('ABORT')
for language in ('1', '2'):
    for sector in ('1', '2', '3', '4', '5'):
        call = Call(identity('10'))
        assert '<mnc>10</mnc>' in call.last['requestXml']
        call.steps(language, '1', sector)
        assert call.send('ABORT')['state'] == 'End'

partial = Call()
partial.steps('1', '1', '1', '1')
assert partial.send('ABORT')['state'] == 'End'
resume = Call(partial.subscriber)
resume.steps('1', '1')
assert 'Unfinished' in resume.last['prompt']
resume.steps('1')
assert resume.send('TIMEOUT')['state'] == 'End'

denied = Call(gateway_key='deliberately-wrong-key')
assert denied.last['httpStatus'] == 401 and denied.last['errorCode'] == 'HTTP_ERROR'
original_xml = denied.last['requestXml']
denied.last_request['gatewayKey'] = key
allowed = api('exchanges', denied.last_request)
assert allowed['errorCode'] is None and allowed['requestXml'] == original_xml
denied.key = key
denied.send('ABORT')

without_ids = Call(include_id=False)
assert '<requestId>' not in without_ids.last['requestXml']
without_ids.steps('1')
without_ids.send('ABORT')

if urllib.parse.urlparse(base).hostname in ('localhost', '127.0.0.1'):
    localhost = Call(target='http://localhost:8080/ussd/callback/grapevine')
    assert localhost.last['errorCode'] is None, ('Docker localhost mapping', localhost.last['errorCode'])
    localhost.send('ABORT')

print('PASS: five sector menus in both languages, generated numbers/IMSIs, replay, resume, abort, timeout, gateway authentication and Docker localhost mapping. No owners or business records created.')
