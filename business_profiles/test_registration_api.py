import json
import time
import uuid
from unittest.mock import patch
from types import SimpleNamespace

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from django.test import TestCase, override_settings, Client
from .models import USSDRegistration
from .registration_auth import jwks_client


@override_settings(REGISTRATION_AUTH_ISSUER='https://auth.example.test',
                   REGISTRATION_AUTH_JWKS_URL='https://auth.example.test/oauth2/jwks')
class RegistrationAPITests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def setUp(self):
        self.subject = str(uuid.uuid4())
        self.claims = {'sub': self.subject, 'iss': 'https://auth.example.test',
                       'aud': ['registration-api'], 'kind': 'owner', 'scope': 'businesses:create',
                       'iat': int(time.time()), 'exp': int(time.time()) + 900}
        self.lookup = patch('business_profiles.registration_auth.jwks_client').start()
        self.addCleanup(patch.stopall)
        self.lookup.return_value.get_signing_key_from_jwt.return_value = SimpleNamespace(key=self.key.public_key())
        self.client = Client(enforce_csrf_checks=True)

    def payload(self, sector='retail'):
        details = {'location': 'Test location', 'turnover_range': '50000_plus'}
        sector_details = {
            'transport': {'business_type': 'taxi', 'vin': 'TESTVIN', 'license_plate': 'TEST001'},
            'services': {'service_type': 'salon', 'service_price_range': '100_499'},
            'retail': {'goods_type': 'food', 'purchase_price_range': '100_499', 'selling_price_range': '500_999'},
            'ecommerce': {'service_type': 'takealot', 'purchase_price_range': '100_499', 'selling_price_range': '500_999', 'shipping_price_range': '100_499'},
            'agriculture': {'activity': 'livestock', 'farmland_count': 0, 'farmland_size': '0', 'farmland_unit': 'hectares', 'selling_price_range': '1000_9999'},
        }
        details.update(sector_details[sector])
        if sector in ('transport', 'services'):
            details.update(working_days=['Monday'], opens_at='08:00', closes_at='17:00', overnight=False)
        payload = {'sector': sector, 'owner': {'fullNames': 'Test Owner', 'idNumber': '000001'},
                   'details': details, 'employees': [{'name': 'Test Employee', 'salary_range': '20000_plus'}],
                   'source': {'channel': 'USSD', 'language': 'en'}}
        if sector == 'transport':
            payload['routes'] = [{'origin': 'Maseru', 'destination': 'Roma', 'price': '25.50'}]
        if sector == 'agriculture':
            payload['livestock'] = [{'animal_type': 'Sheep', 'number': 5}, {'animal_type': 'Cattle', 'number': 2}]
        return payload

    def post(self, payload=None, key='test-operation', claims=None):
        token = jwt.encode(claims or self.claims, self.key, algorithm='RS256', headers={'kid': 'test'})
        return self.client.post('/api/v1/businesses', data=json.dumps(payload or self.payload()),
                                content_type='application/json', HTTP_AUTHORIZATION='Bearer ' + token,
                                HTTP_IDEMPOTENCY_KEY=key)

    def test_all_five_sectors_and_repeatable_collections(self):
        for sector in ('transport', 'services', 'ecommerce', 'retail', 'agriculture'):
            response = self.post(self.payload(sector), key=sector)
            self.assertEqual(response.status_code, 201, response.content)
            saved = USSDRegistration.objects.get(pk=response.json()['entityId'])
            self.assertEqual(str(saved.owner_subject), self.subject)
            self.assertEqual(saved.payload['owner']['idNumber'], '000001')
            self.assertLessEqual(len(response.json()['reference']), 64)
        self.assertEqual(USSDRegistration.objects.count(), 5)

    def test_retry_and_owner_scope(self):
        original = self.post()
        self.assertEqual(self.post().status_code, 200)
        self.assertEqual(self.post().json(), original.json())
        changed = self.payload(); changed['owner']['fullNames'] = 'Changed'
        self.assertEqual(self.post(changed).status_code, 409)
        other = self.claims | {'sub': str(uuid.uuid4())}
        self.assertEqual(self.post(claims=other).status_code, 201)
        self.assertEqual(USSDRegistration.objects.count(), 2)

    def test_invalid_tokens_and_application_tokens(self):
        for claims in [self.claims | {'exp': 1}, self.claims | {'iss': 'https://evil.test'},
                       self.claims | {'aud': 'auth-api'}, self.claims | {'sub': 'not-uuid'}]:
            self.assertEqual(self.post(claims=claims).status_code, 401)
        for changes in [{'kind': 'application'}, {'scope': ''}, {'scope': ['businesses:create']}]:
            self.assertEqual(self.post(claims=self.claims | changes).status_code, 403)
        self.assertEqual(self.client.post('/api/v1/businesses').status_code, 401)
        bad = jwt.encode(self.claims, 'x' * 64, algorithm='HS256', headers={'kid': 'test'})
        self.assertEqual(self.client.post('/api/v1/businesses', HTTP_AUTHORIZATION='Bearer ' + bad).status_code, 401)
        self.assertFalse(USSDRegistration.objects.exists())

    def test_validation_does_not_consume_retry_key(self):
        for field, value in [('salary_range', 'invalid'), ('name', '')]:
            payload = self.payload(); payload['employees'][0][field] = value
            self.assertEqual(self.post(payload).status_code, 422)
        payload = self.payload(); payload['owner']['idNumber'] = 123
        self.assertEqual(self.post(payload).status_code, 422)
        payload = self.payload(); payload['employees'] *= 51
        self.assertEqual(self.post(payload).status_code, 422)
        payload = self.payload(); payload['ownerId'] = str(uuid.uuid4())
        self.assertEqual(self.post(payload).status_code, 422)
        self.assertFalse(USSDRegistration.objects.exists())
        self.assertEqual(self.post().status_code, 201)

    def test_errors_and_no_cache(self):
        self.assertEqual(self.post(key='invalid key').status_code, 400)
        self.assertEqual(self.client.get('/api/v1/businesses').status_code, 405)
        self.lookup.return_value.get_signing_key_from_jwt.side_effect = jwt.PyJWKClientConnectionError('private internal detail')
        response = self.post()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(b'private internal', response.content)
        self.assertIn('no-store', response.headers['Cache-Control'])

    def test_options_publish_matching_choices_and_collection_actions(self):
        response = self.client.get('/api/v1/registration/options')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['sectors']), 5)
        transport = response.json()['sectors'][0]
        routes = next(row for row in transport['collections'] if row['name'] == 'routes')
        self.assertEqual(routes['fields'][2]['type'], 'decimal')
        for sector in response.json()['sectors']:
            staff = next(row for row in sector['collections'] if row['name'] == 'employees')
            self.assertEqual(staff['actions'], ['add_another', 'continue'])
            self.assertEqual(staff['fields'][1]['choices'][-1]['value'], '20000_plus')

    def test_real_jwks_client_with_mocked_network(self):
        jwks_client.cache_clear()
        public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key())) | {'kid': 'test', 'alg': 'RS256', 'use': 'sig'}
        # Exercise key selection and signature validation without any real network calls.
        from business_profiles import registration_auth
        real_client = jwt.PyJWKClient('https://auth.example.test/oauth2/jwks', timeout=2)
        self.lookup.return_value = real_client
        with patch.object(real_client, 'fetch_data', return_value={'keys': [public]}):
            self.assertEqual(self.post().status_code, 201)

    def test_malformed_and_oversized_json_and_wrong_media_type(self):
        token = jwt.encode(self.claims, self.key, algorithm='RS256', headers={'kid': 'test'})
        headers = {'HTTP_AUTHORIZATION': 'Bearer ' + token, 'HTTP_IDEMPOTENCY_KEY': 'test'}
        for body in ['[]', '{bad json', '{"sector":"retail","sector":"transport"}', '{"number":NaN}']:
            response = self.client.post('/api/v1/businesses', data=body, content_type='application/json', **headers)
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.post('/api/v1/businesses', data=' ' * 16385, content_type='application/json', **headers).status_code, 413)
        self.assertEqual(self.client.post('/api/v1/businesses', data='{}', content_type='text/plain', **headers).status_code, 415)
        self.assertFalse(USSDRegistration.objects.exists())

    def test_missing_claim_and_invalid_signature(self):
        claims = dict(self.claims); del claims['exp']
        self.assertEqual(self.post(claims=claims).status_code, 401)
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        token = jwt.encode(self.claims, other, algorithm='RS256', headers={'kid': 'test'})
        response = self.client.post('/api/v1/businesses', HTTP_AUTHORIZATION='Bearer ' + token)
        self.assertEqual(response.status_code, 401)

    def test_conditional_other_and_land_validation(self):
        payload = self.payload(); payload['details']['goods_type'] = 'other'
        self.assertEqual(self.post(payload).status_code, 422)
        payload['details']['other_description'] = 'Other goods'
        self.assertEqual(self.post(payload).status_code, 201)
        payload = self.payload('agriculture'); payload['livestock'] = []
        self.assertEqual(self.post(payload, key='farm').status_code, 422)
        payload['details']['activity'] = 'farming'
        self.assertEqual(self.post(payload, key='farm').status_code, 422)
        payload['details'].update(farmland_count=1, farmland_size='1.25')
        self.assertEqual(self.post(payload, key='farm').status_code, 201)
