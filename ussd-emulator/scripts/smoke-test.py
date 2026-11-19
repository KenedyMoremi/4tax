#!/usr/bin/env python3
"""Test the running emulator against a real USSD callback using synthetic subscribers."""
from datetime import datetime, timezone
import getpass
import json
import os
import urllib.error
import urllib.request
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

transport = Call()
assert transport.last['errorCode'] is None
assert f"<imsi>{transport.subscriber['imsi']}</imsi>" in transport.last['requestXml']
assert '<mcc>651</mcc>' in transport.last['requestXml'] and '<mnc>01</mnc>' in transport.last['requestXml']
replay = api('exchanges', transport.last_request)
assert replay['requestXml'] == transport.last['requestXml'] and replay['prompt'] == transport.last['prompt']
transport.steps('1', '1', '1', 'DEMO0000000000001', 'DEMO123', '000000000001', 'Synthetic Owner', 'Maseru', '2', '1', '087431', '087431')
transport.confirmed()

returning = Call(transport.subscriber)
returning.steps('1', '2', '087431', '1', '3', '2', 'Maseru market', '1', '000000000001', 'Synthetic Owner', '1')
returning.confirmed()

wellness = Call(identity('10'))
assert '<mnc>10</mnc>' in wellness.last['requestXml']
wellness.steps('2', '1', '2', '2', '62123456', '4', '1,3,5', '08:00', '17:00', 'Synthetic Salon', 'Ha Thetsane', '000000000002', 'Synthetic Owner', '1', '087431', '087431')
wellness.confirmed()

vendor = Call()
vendor.steps('1', '1', '3', '1', 'Synthetic Vendor', 'Maseru market', '1', '000000000003', 'Synthetic Owner', '1', '087431', '087431')
vendor.confirmed()

partial = Call()
partial.steps('1', '1', '1', 'DEMO0000000000002')
assert partial.send('ABORT')['state'] == 'End'
resume = Call(partial.subscriber)
resume.steps('1', '1')
assert 'Unfinished' in resume.last['prompt']
resume.steps('1')
assert 'number plate' in resume.last['prompt']
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

localhost = Call(target='http://localhost:8080/ussd/callback/grapevine')
assert localhost.last['errorCode'] is None, ('Docker localhost mapping', localhost.last['errorCode'])
localhost.send('ABORT')
print('PASS: three registration sectors, Add business, generated numbers/IMSIs, exact replay, resume, abort, timeout, key correction, missing request IDs and Docker localhost mapping.')
