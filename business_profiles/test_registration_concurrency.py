import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from unittest import skipUnless
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from django.db import connection, connections
from django.test import Client, TransactionTestCase, override_settings
from .models import USSDRegistration


@skipUnless(connection.vendor == 'postgresql', 'Requires an explicitly configured disposable PostgreSQL database')
@override_settings(REGISTRATION_AUTH_ISSUER='https://auth.example.test',
                   REGISTRATION_AUTH_JWKS_URL='https://auth.example.test/oauth2/jwks')
class RegistrationConcurrencyTests(TransactionTestCase):
    def test_concurrent_retries_create_one_registration_and_conflicting_payload_is_rejected(self):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        token = jwt.encode({'sub': str(uuid.uuid4()), 'iss': 'https://auth.example.test',
                            'aud': 'registration-api', 'kind': 'owner', 'scope': 'businesses:create',
                            'iat': int(time.time()), 'exp': int(time.time()) + 900}, key,
                           algorithm='RS256', headers={'kid': 'test'})
        payload = {'sector': 'retail', 'owner': {'fullNames': 'Test Owner', 'idNumber': '000001'},
                   'details': {'goods_type': 'food', 'location': 'Test market', 'turnover_range': '1000_9999',
                               'purchase_price_range': '100_499', 'selling_price_range': '500_999'},
                   'employees': [], 'source': {'channel': 'USSD', 'language': 'en'}}
        barrier = Barrier(2)
        def send(body, operation):
            try:
                barrier.wait(timeout=10)
                response = Client().post('/api/v1/businesses', data=json.dumps(body), content_type='application/json',
                                         HTTP_AUTHORIZATION='Bearer ' + token, HTTP_IDEMPOTENCY_KEY=operation)
                return response.status_code, response.json()
            finally:
                connections.close_all()
        with patch('business_profiles.registration_auth.jwks_client') as lookup:
            lookup.return_value.get_signing_key_from_jwt.return_value = SimpleNamespace(key=key.public_key())
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: send(payload, 'same'), range(2)))
            self.assertEqual(sorted(status for status, _ in results), [200, 201])
            self.assertEqual(results[0][1], results[1][1])
            self.assertEqual(USSDRegistration.objects.count(), 1)
            changed = payload | {'owner': {'fullNames': 'Changed Owner', 'idNumber': '000001'}}
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(send, payload, 'conflict')
                second = pool.submit(send, changed, 'conflict')
                statuses = sorted([first.result()[0], second.result()[0]])
            self.assertEqual(statuses, [201, 409])
            self.assertEqual(USSDRegistration.objects.count(), 2)
