import json
import time
import uuid
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest import skipUnless
from types import SimpleNamespace
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from django.db import connection, close_old_connections
from django.test import TestCase, TransactionTestCase, Client, override_settings
from django.utils import timezone

from agents.bookkeeping import AgentUnavailable
from bookkeeping.models import Contact, Document, JournalEntry, Payment, RecordProposal
from .models import USSDRegistration, USSDTransaction, USSDLedger
from . import test_registration_api as registration_tests


@override_settings(REGISTRATION_AUTH_ISSUER='https://auth.example.test', REGISTRATION_AUTH_JWKS_URL='https://auth.example.test/oauth2/jwks', WHATSAPP_ENABLED=False)
class USSDTransactionTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def setUp(self):
        self.subject = str(uuid.uuid4())
        self.claims = {'sub': self.subject, 'iss': 'https://auth.example.test', 'aud': ['registration-api'],
                       'kind': 'owner', 'scope': 'businesses:create businesses:read transactions:create',
                       'iat': int(time.time()), 'exp': int(time.time()) + 900}
        lookup = patch('business_profiles.registration_auth.jwks_client').start()
        lookup.return_value.get_signing_key_from_jwt.return_value = SimpleNamespace(key=self.key.public_key())
        self.ai = patch('business_profiles.transactions.interpret').start()
        self.ai.return_value = self.intent()
        self.addCleanup(patch.stopall)
        self.client = Client(enforce_csrf_checks=True)
        self.registration = self.entity()

    def entity(self, sector='retail', **changes):
        return USSDRegistration.objects.create(issuer=self.claims['iss'], owner_subject=self.subject,
                idempotency_key=uuid.uuid4().hex, payload=registration_tests.RegistrationAPITests.payload(self, sector), **changes)

    def intent(self, **changes):
        return dict(action='sale', description='Test sale', amount='100.00', currency='LSL', date=timezone.localdate().isoformat(),
                    due_date=None, contact_name=None, payment_account='1000', expense_account=None, tax_rate='0.00',
                    amount_basis='exclusive', document_number=None, question=None) | changes

    def headers(self, claims=None, key='operation-1'):
        token = jwt.encode(claims or self.claims, self.key, algorithm='RS256', headers={'kid': 'test'})
        return {'HTTP_AUTHORIZATION': 'Bearer '+token, 'HTTP_IDEMPOTENCY_KEY': key}

    def payload(self, entity=None):
        entity = entity or self.registration
        sector = entity.payload['sector']
        fields = {'paymentDetails': 'paid in cash', 'buyer': 'N/A'}
        fields.update({'route': 'Maseru to Roma', 'passengers': '5 passengers', 'fareCost': 'M20 per passenger'} if sector == 'transport'
                      else {'service': 'Haircut', 'serviceCost': 'M100'} if sector == 'services'
                      else {'goods': 'Two bags of produce', 'totalValue': 'M100 total'})
        return {'channel': 'USSD', 'action': 'propose', 'entityId': str(entity.pk), 'sector': sector, 'fields': fields, 'language': 'en'}

    def post(self, payload=None, key='operation-1', claims=None):
        return self.client.post('/webhooks/twilio/whatsapp/', data=json.dumps(payload or self.payload()),
                                content_type='application/json', **self.headers(claims, key))

    def resolve(self, proposal, action='confirm', entity=None, key='operation-1', claims=None):
        return self.post({'channel': 'USSD', 'action': action, 'entityId': str((entity or self.registration).pk),
                          'transactionId': proposal['transactionId']}, key=key, claims=claims)

    def test_every_sector_uses_free_text_then_proposal_and_explicit_confirmation(self):
        for sector in ('transport', 'services', 'ecommerce', 'retail', 'agriculture'):
            entity = self.entity(sector)
            key = sector
            response = self.post(self.payload(entity), key=key)
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(response['Cache-Control'], 'no-store')
            self.assertEqual(response.json()['status'], 'pending')
            ledger = USSDLedger.objects.get(registration=entity)
            self.assertFalse(ledger.business.owner.has_usable_password())
            self.assertEqual(ledger.business.district, '')
            self.assertFalse(JournalEntry.objects.filter(business=ledger.business).exists())
            self.assertEqual(self.resolve(response.json(), entity=entity, key=key).json()['status'], 'posted')
            self.assertEqual(Payment.objects.filter(document__business=ledger.business).count(), 1)
            self.assertEqual(Contact.objects.get(business=ledger.business).name, 'N/A')
            self.assertTrue(Document.objects.get(business=ledger.business).notes.startswith('Confirmed via USSD'))
        self.assertEqual(USSDLedger.objects.count(), 5)
        self.assertEqual(len(set(USSDLedger.objects.values_list('business__owner_id', flat=True))), 5)

    def test_retries_reuse_proposal_and_post_only_once(self):
        first = self.post().json()
        self.assertEqual(first, self.post().json())
        self.assertEqual(self.ai.call_count, 1)
        changed = self.payload(); changed['fields']['totalValue'] = 'M200'
        self.assertEqual(self.post(changed).status_code, 409)
        first_confirm = self.resolve(first)
        self.assertEqual(first_confirm.json(), self.resolve(first).json())
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(Document.objects.count(), 1)

    def test_cancel_never_posts_and_cannot_be_confirmed(self):
        proposal = self.post().json()
        self.assertEqual(self.resolve(proposal, 'cancel').json()['status'], 'cancelled')
        self.assertEqual(self.resolve(proposal, 'cancel').status_code, 200)
        self.assertEqual(self.resolve(proposal).status_code, 409)
        self.assertFalse(JournalEntry.objects.exists())

    def test_owner_and_issuer_isolation_in_listing_and_webhook(self):
        other = self.claims | {'sub': str(uuid.uuid4())}
        foreign = self.entity(); foreign.owner_subject = other['sub']; foreign.save()
        self.assertEqual(self.post(self.payload(foreign)).status_code, 404)
        self.assertEqual(self.post(claims=self.claims | {'iss': 'https://wrong.example.test'}).status_code, 401)
        response = self.client.get('/api/v1/businesses', **self.headers())
        self.assertEqual([x['entityId'] for x in response.json()['businesses']], [str(self.registration.pk)])
        proposal = self.post().json()
        self.assertEqual(self.resolve(proposal, claims=other).status_code, 404)

    def test_pagination_returns_only_this_owners_entities(self):
        for _ in range(6): self.entity()
        first = self.client.get('/api/v1/businesses?page=1', **self.headers()).json()
        second = self.client.get('/api/v1/businesses?page=2', **self.headers()).json()
        self.assertEqual(len(first['businesses']), 5); self.assertEqual(first['nextPage'], 2)
        self.assertEqual(len(second['businesses']), 2); self.assertIsNone(second['nextPage'])
        self.assertEqual(self.client.get('/api/v1/businesses?page=0', **self.headers()).status_code, 400)
        self.assertFalse(USSDLedger.objects.exists())

    def test_signature_scope_kind_audience_and_expiry_are_enforced(self):
        for changes, status in [({'scope': 'businesses:create'}, 403), ({'kind': 'application'}, 403),
                                ({'aud': ['auth-api']}, 401), ({'exp': int(time.time())-1}, 401)]:
            self.assertEqual(self.post(claims=self.claims | changes).status_code, status)
        self.assertEqual(self.client.post('/webhooks/twilio/whatsapp/', data=json.dumps(self.payload()), content_type='application/json').status_code, 401)
        self.assertEqual(self.client.get('/api/v1/businesses', **self.headers(self.claims | {'scope': 'transactions:create'})).status_code, 403)
        self.assertFalse(USSDTransaction.objects.exists())

    def test_ai_outage_is_retryable_without_duplicate_proposals(self):
        self.ai.side_effect = AgentUnavailable('private provider detail')
        first = self.post(); self.assertEqual(first.status_code, 503)
        self.assertNotIn(b'private provider detail', first.content)
        self.ai.side_effect = None
        self.assertEqual(self.post().json()['status'], 'pending')
        self.assertEqual(USSDTransaction.objects.count(), 1)
        self.assertEqual(RecordProposal.objects.count(), 1)

    def test_ambiguity_wrong_intents_or_missing_payment_accounts_never_post(self):
        for index, intent in enumerate([self.intent(action='clarify', question='private customer detail'),
                                        self.intent(action='expense'), self.intent(payment_account=None)]):
            self.ai.return_value = intent
            response = self.post(key='ambiguous-'+str(index))
            self.assertEqual(response.status_code, 422, response.content)
            self.assertEqual(response.json()['code'], 'CLARIFICATION_REQUIRED')
            self.assertNotIn(b'private customer detail', response.content)
        self.assertFalse(JournalEntry.objects.exists())

    def test_unpaid_invoice_requires_buyer_and_due_date(self):
        self.ai.return_value = self.intent(action='invoice', due_date=(timezone.localdate()+timedelta(days=10)).isoformat(), payment_account=None)
        self.assertEqual(self.post().status_code, 422)
        payload = self.payload(); payload['fields'].update(buyer='Test Buyer', paymentDetails='unpaid; due in 10 days')
        self.ai.return_value['contact_name'] = 'Test Buyer'
        preview = self.post(payload, key='unpaid').json()
        self.assertEqual(self.resolve(preview, key='unpaid').json()['status'], 'posted')
        self.assertFalse(Payment.objects.exists())
        self.assertEqual(Document.objects.get().contact.name, 'Test Buyer')

    def test_invalid_payloads_and_sector_tampering_do_not_reach_ai(self):
        for mutate in [lambda p: p.update(sector='transport'), lambda p: p['fields'].update(totalValue=100),
                       lambda p: p['fields'].update(unknown='bad'), lambda p: p['fields'].update(goods=''),
                       lambda p: p.update(unknown='bad')]:
            payload = self.payload(); mutate(payload)
            self.assertEqual(self.post(payload).status_code, 422)
        self.ai.assert_not_called(); self.assertFalse(USSDLedger.objects.exists())

    def test_expired_preview_does_not_post_and_processing_lease_is_respected(self):
        preview = self.post().json()
        proposal = RecordProposal.objects.get(); proposal.expires_at = timezone.now()-timedelta(seconds=1); proposal.save()
        self.assertEqual(self.resolve(preview).json()['code'], 'PROPOSAL_EXPIRED_OR_CHANGED')
        item = USSDTransaction.objects.get(); item.status='processing'; item.save()
        self.assertEqual(self.post().json()['code'], 'TRANSACTION_BUSY')
        self.assertFalse(JournalEntry.objects.exists())

    @override_settings(BOOKKEEPING_AI_PROVIDER='openai', OPENAI_API_KEY='private-test-key')
    def test_read_only_release_health_reports_schema_and_provider_without_secrets(self):
        response=self.client.get('/api/v1/transactions/health')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json(),{'ready':True,'schemaReady':True,'aiConfigured':True})
        self.assertNotIn(b'private-test-key',response.content)
        self.assertFalse(USSDLedger.objects.exists()); self.ai.assert_not_called()
        with self.settings(OPENAI_API_KEY=''):
            self.assertEqual(self.client.get('/api/v1/transactions/health').status_code,503)


@skipUnless(connection.vendor == 'postgresql', 'Row-lock tests require PostgreSQL')
@override_settings(REGISTRATION_AUTH_ISSUER='https://auth.example.test', REGISTRATION_AUTH_JWKS_URL='https://auth.example.test/oauth2/jwks')
class USSDTransactionConcurrencyTests(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    setUp = USSDTransactionTests.setUp
    entity = USSDTransactionTests.entity
    intent = USSDTransactionTests.intent
    headers = USSDTransactionTests.headers
    payload = USSDTransactionTests.payload
    post = USSDTransactionTests.post
    resolve = USSDTransactionTests.resolve

    def threaded_post(self, payload):
        close_old_connections()
        try:
            return Client(enforce_csrf_checks=True).post('/webhooks/twilio/whatsapp/', data=json.dumps(payload),
                         content_type='application/json', **self.headers())
        finally:
            close_old_connections()

    def test_overlapping_proposals_call_ai_once_and_preserve_operation(self):
        entered, release = Event(), Event()
        def slow(*args, **kwargs):
            entered.set()
            if not release.wait(5): raise RuntimeError('Test did not release AI call')
            return self.intent()
        self.ai.side_effect = slow
        with ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(self.threaded_post, self.payload())
            try:
                self.assertTrue(entered.wait(5))
                self.assertEqual(self.post().json()['code'], 'TRANSACTION_BUSY')
            finally:
                release.set()
            self.assertEqual(first.result().status_code, 200)
        self.assertEqual(self.post().status_code, 200)
        self.assertEqual(self.ai.call_count, 1)
        self.assertEqual(RecordProposal.objects.count(), 1)

    def test_overlapping_confirmations_post_exactly_one_sale_and_payment(self):
        preview = self.post().json()
        payload = {'channel': 'USSD', 'action': 'confirm', 'entityId': str(self.registration.pk), 'transactionId': preview['transactionId']}
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(self.threaded_post, [payload, payload]))
        self.assertEqual([r.status_code for r in responses], [200, 200])
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(Document.objects.count(), 1)
        self.assertEqual(JournalEntry.objects.count(), 2)
