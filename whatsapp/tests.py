from datetime import timedelta
from unittest.mock import patch, MagicMock
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from django.db.models import Sum
from twilio.request_validator import RequestValidator
from agents.bookkeeping import AgentUnavailable, interpret, RecordIntent
from bookkeeping import services, agent_actions
from bookkeeping.models import RecordProposal, Expense, Document, Payment, JournalLine, Contact
from .linking import change_link
from .models import WhatsAppLink, InboundMessage, OutboundMessage
from .worker import process_one, send_one

SETTINGS = dict(BOOKKEEPING_AI_PROVIDER='openai', WHATSAPP_SEND_INTERVAL_SECONDS=0, WHATSAPP_ENABLED=True, TWILIO_ACCOUNT_SID='AC'+'1'*32, TWILIO_AUTH_TOKEN='test-token', TWILIO_WHATSAPP_FROM='whatsapp:+14155550000', TWILIO_WEBHOOK_URL='http://testserver/webhooks/twilio/whatsapp/', OPENAI_API_KEY='test-only')


@override_settings(**SETTINGS)
class WhatsAppTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='owner', password='test')
        self.other = get_user_model().objects.create_user(username='other', password='test')
        self.business = services.setup_business(owner=self.user, name='Shop')
        self.other_business = services.setup_business(owner=self.other, name='Other')
        self.code = change_link(self.business, self.user, '+26658123456')
        self.link = WhatsAppLink.objects.get(business=self.business)
        self.counter = 0
        self.client.force_login(self.user)

    def intent(self, **changes):
        return dict(action='expense', description='Transport', amount='250.00', currency='LSL', date=timezone.localdate().isoformat(), due_date=None, contact_name=None, payment_account='1020', expense_account='5300', tax_rate='0.00', amount_basis='exclusive', document_number=None, question=None) | changes

    def verified(self):
        self.link.verified_at = timezone.now()
        self.link.save()

    def enqueue(self, body='Paid M250 for transport from M-Pesa', **changes):
        self.counter += 1
        return InboundMessage.objects.create(sid='SM'+f'{self.counter:032x}', link=self.link, generation=self.link.generation, body=body, **changes)

    def signed(self, **changes):
        data = dict(MessageSid='SM'+'a'*32, From='whatsapp:'+self.link.phone, To=SETTINGS['TWILIO_WHATSAPP_FROM'], AccountSid=SETTINGS['TWILIO_ACCOUNT_SID'], Body='HELP', NumMedia='0') | changes
        signature = RequestValidator(SETTINGS['TWILIO_AUTH_TOKEN']).compute_signature(SETTINGS['TWILIO_WEBHOOK_URL'], data)
        return self.client.post(reverse('twilio_whatsapp'), data, HTTP_X_TWILIO_SIGNATURE=signature)

    @patch('whatsapp.worker.interpret')
    def test_signed_webhook_is_fast_and_idempotent(self, ai):
        self.assertEqual(self.signed().status_code, 200)
        self.assertEqual(self.signed().status_code, 200)
        self.assertEqual(InboundMessage.objects.count(), 1)
        ai.assert_not_called()

    def test_rejects_forgery_wrong_account_destination_and_invalid_input(self):
        self.assertEqual(self.client.post(reverse('twilio_whatsapp'), {}).status_code, 403)
        self.assertEqual(self.signed(AccountSid='wrong').status_code, 403)
        self.assertEqual(self.signed(To='whatsapp:+14155550001').status_code, 403)
        self.assertEqual(self.signed(MessageSid='bad').status_code, 400)
        self.assertEqual(self.signed(Body='a'*4001).status_code, 400)
        self.assertFalse(InboundMessage.objects.exists())

    def test_unknown_sender_and_disabled_integration(self):
        self.assertEqual(self.signed(From='whatsapp:+26658999999').status_code, 200)
        self.assertFalse(InboundMessage.objects.exists())
        with override_settings(WHATSAPP_ENABLED=False):
            self.assertEqual(self.signed().status_code, 503)

    @override_settings(WHATSAPP_HOURLY_LIMIT=1)
    def test_rate_limit_and_retry(self):
        self.signed()
        self.assertContains(self.signed(MessageSid='SM'+'b'*32), 'hourly message limit')
        self.assertEqual(InboundMessage.objects.count(), 1)
        self.assertNotContains(self.signed(), 'hourly message limit')

    @patch('whatsapp.worker.interpret')
    def test_link_verification_and_attempt_limit(self, ai):
        self.enqueue('LINK '+self.code)
        process_one()
        self.link.refresh_from_db()
        self.assertIsNotNone(self.link.verified_at)
        self.assertEqual(self.link.code_digest, '')
        ai.assert_not_called()
        change_link(self.business, self.user, self.link.phone)
        self.link.refresh_from_db()
        for _ in range(6):
            self.enqueue('LINK WRONG')
            process_one()
        self.link.refresh_from_db()
        self.assertEqual(self.link.failed_attempts, 5)
        self.assertIsNone(self.link.verified_at)

    def test_phone_cannot_link_to_two_businesses(self):
        with self.assertRaises(ValidationError):
            change_link(self.other_business, self.other, self.link.phone)

    @patch('whatsapp.worker.interpret')
    def test_preview_confirm_retry_and_balance(self, ai):
        self.verified()
        ai.return_value = self.intent()
        self.enqueue()
        process_one()
        proposal = RecordProposal.objects.get()
        self.assertFalse(Expense.objects.exists())
        self.assertFalse(JournalLine.objects.exists())
        self.enqueue('CONFIRM '+proposal.reference)
        process_one()
        self.enqueue('CONFIRM '+proposal.reference)
        process_one()
        self.assertEqual(Expense.objects.count(), 1)
        totals = JournalLine.objects.aggregate(d=Sum('debit'), c=Sum('credit'))
        self.assertEqual(totals['d'], totals['c'])
        self.assertEqual(OutboundMessage.objects.count(), 3)
        self.assertEqual(ai.call_count, 1)

    def proposal(self, **changes):
        return agent_actions.propose(business=self.business, owner=self.user, source_key='whatsapp:test'+str(RecordProposal.objects.count()), data=self.intent(**changes))

    def confirm(self, proposal):
        return agent_actions.resolve_proposal(business=self.business, owner=self.user, reference=proposal.reference, confirm=True)

    def test_cancel_expiry_cross_tenant_and_csrf(self):
        proposal = self.proposal()
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(reverse('agent_records')), proposal.reference)
        self.client.post(reverse('agent_records'), {'reference':proposal.reference, 'action':'confirm'})
        self.assertFalse(Expense.objects.exists())
        self.client.force_login(self.user)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        self.assertEqual(csrf_client.post(reverse('agent_records'), {'reference':proposal.reference, 'action':'confirm'}).status_code, 403)
        self.assertEqual(csrf_client.post(reverse('whatsapp_setup'), {'action':'disconnect'}).status_code, 403)
        self.client.post(reverse('agent_records'), {'reference':proposal.reference, 'action':'cancel'})
        with self.assertRaises(ValidationError):
            self.confirm(proposal)
        expired = self.proposal()
        RecordProposal.objects.filter(pk=expired.pk).update(expires_at=timezone.now()-timedelta(seconds=1))
        with self.assertRaises(ValidationError):
            self.confirm(expired)
        self.assertFalse(Expense.objects.exists())

    @patch('whatsapp.worker.interpret')
    def test_disconnect_invalidates_work_and_drafts(self, ai):
        self.verified()
        proposal = self.proposal()
        self.enqueue('CONFIRM '+proposal.reference)
        change_link(self.business, self.user)
        process_one()
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, 'cancelled')
        self.assertFalse(Expense.objects.exists())
        self.assertFalse(OutboundMessage.objects.exists())
        ai.assert_not_called()

    def test_paid_sale_unpaid_documents_and_payment(self):
        sale = self.proposal(action='sale', contact_name='Buyer')
        self.assertFalse(Contact.objects.exists())
        self.confirm(sale)
        doc = Document.objects.get()
        self.assertEqual(doc.paid, doc.total)
        self.assertEqual(Payment.objects.count(), 1)
        invoice = self.proposal(action='invoice', contact_name='Customer', due_date=timezone.localdate().isoformat())
        self.confirm(invoice)
        unpaid = Document.objects.get(contact__name='Customer')
        self.assertEqual(unpaid.paid, 0)
        self.confirm(self.proposal(action='payment', document_number=unpaid.number))
        unpaid.refresh_from_db()
        self.assertEqual(unpaid.balance, 0)
        self.confirm(self.proposal(action='bill', contact_name='Supplier', due_date=timezone.localdate().isoformat()))
        self.assertEqual(Document.objects.filter(kind='bill', status='posted').count(), 1)

    def test_validation_rejects_foreign_currency_future_date_tax_and_account(self):
        for changes in [dict(currency='OTHER'), dict(date=(timezone.localdate()+timedelta(days=1)).isoformat()), dict(tax_rate='14'), dict(payment_account='9999'), dict(amount='-1'), dict(action='delete')]:
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.proposal(**changes)
        self.assertFalse(RecordProposal.objects.exists())

    @patch('whatsapp.worker.interpret', side_effect=AgentUnavailable('test'))
    def test_provider_failure_retries_without_posting(self, ai):
        self.verified()
        message = self.enqueue()
        for _ in range(3):
            InboundMessage.objects.filter(pk=message.pk).update(available_at=timezone.now())
            process_one()
        message.refresh_from_db()
        self.assertEqual(message.status, 'done')
        self.assertEqual(message.attempts, 3)
        self.assertIn('unavailable', OutboundMessage.objects.get().body)
        self.assertFalse(RecordProposal.objects.exists())

    @patch('whatsapp.worker.interpret')
    def test_media_and_summary_skip_ai(self, ai):
        self.verified()
        self.enqueue(media_count=1)
        process_one()
        self.enqueue('SUMMARY')
        process_one()
        ai.assert_not_called()
        self.assertIn('Revenue', OutboundMessage.objects.last().body)

    @patch('whatsapp.worker.Client')
    def test_outbox_acceptance_and_ambiguous_failure_no_retry(self, client):
        self.verified()
        message = self.enqueue('HELP')
        process_one()
        client.return_value.messages.create.side_effect = TimeoutError('sensitive text')
        send_one()
        self.assertFalse(send_one())
        reply = OutboundMessage.objects.get(inbound=message)
        self.assertEqual(reply.status, 'uncertain')
        self.assertEqual(reply.error_code, 'send_unconfirmed')
        client.return_value.messages.create.assert_called_once()
        self.enqueue('HELP')
        process_one()
        client.return_value.messages.create.side_effect = None
        client.return_value.messages.create.return_value.sid = 'SM'+'f'*32
        send_one()
        self.assertEqual(OutboundMessage.objects.last().status, 'sent')

    @patch('whatsapp.worker.Client')
    def test_expired_and_revoked_replies_do_not_send(self, client):
        message = self.enqueue('HELP')
        OutboundMessage.objects.create(inbound=message, body='private')
        InboundMessage.objects.filter(pk=message.pk).update(created_at=timezone.now()-timedelta(hours=24))
        send_one()
        self.assertEqual(OutboundMessage.objects.get().status, 'expired')
        message = self.enqueue('HELP')
        OutboundMessage.objects.create(inbound=message, body='private')
        change_link(self.business, self.user)
        send_one()
        self.assertEqual(OutboundMessage.objects.last().status, 'cancelled')
        client.assert_not_called()

    def test_owner_screens_render(self):
        self.proposal()
        self.assertContains(self.client.get(reverse('whatsapp_setup')), 'Connect your number')
        self.assertContains(self.client.get(reverse('agent_records')), 'Transport')
        response = self.client.post(reverse('whatsapp_setup'), {'phone':self.link.phone, 'consent':'on'})
        self.assertContains(response, 'LINK ')
        self.assertIn('no-store', response.headers['Cache-Control'])

    @patch('agents.bookkeeping.OpenAI')
    def test_openai_structured_output_and_no_storage(self, sdk):
        response = MagicMock(status='completed', output_parsed=RecordIntent(**self.intent()))
        sdk.return_value.__enter__.return_value.responses.parse.return_value = response
        self.assertEqual(interpret('example', context='{}')['amount'], '250.00')
        kwargs = sdk.return_value.__enter__.return_value.responses.parse.call_args.kwargs
        self.assertFalse(kwargs['store'])
        self.assertIs(kwargs['text_format'], RecordIntent)
        self.assertEqual(sdk.call_args.kwargs['max_retries'], 0)

    @patch('whatsapp.worker.Client')
    @override_settings(WHATSAPP_SEND_INTERVAL_SECONDS=3)
    def test_sandbox_send_spacing(self, client):
        self.verified()
        client.return_value.messages.create.return_value.sid = 'SM'+'e'*32
        for _ in range(2):
            self.enqueue('HELP')
            process_one()
        self.assertTrue(send_one())
        self.assertFalse(send_one())
        self.assertEqual(OutboundMessage.objects.filter(status='pending').count(), 1)

    @patch('whatsapp.worker.interpret', side_effect=RuntimeError('private provider data'))
    def test_unexpected_failure_is_bounded_and_redacted(self, ai):
        self.verified()
        message = self.enqueue()
        for _ in range(3):
            InboundMessage.objects.filter(pk=message.pk).update(available_at=timezone.now())
            process_one()
        message.refresh_from_db()
        self.assertEqual(message.status, 'failed')
        self.assertEqual(message.error_code, 'processing_failed')
        self.assertFalse(Expense.objects.exists())
        self.assertFalse(process_one())

    def test_owner_can_confirm_in_browser(self):
        proposal = self.proposal()
        response = self.client.post(reverse('agent_records'), {'reference':proposal.reference, 'action':'confirm'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Expense.objects.count(), 1)

    @patch('whatsapp.worker.interpret')
    def test_expired_link_and_inactive_owner_cannot_reach_ai(self, ai):
        self.link.code_expires_at = timezone.now()-timedelta(seconds=1)
        self.link.save()
        self.enqueue('LINK '+self.code)
        process_one()
        self.link.refresh_from_db()
        self.assertIsNone(self.link.verified_at)
        self.verified()
        self.user.is_active = False
        self.user.save()
        self.enqueue()
        process_one()
        ai.assert_not_called()
        self.assertFalse(RecordProposal.objects.exists())

    @override_settings(BOOKKEEPING_AI_PROVIDER='groq', GROQ_API_KEY='test-groq')
    @patch('agents.bookkeeping.OpenAI')
    def test_groq_uses_strict_schema_and_validates_json(self, sdk):
        import json
        response = MagicMock()
        response.choices = [MagicMock(finish_reason='stop', message=MagicMock(content=json.dumps(self.intent())))]
        sdk.return_value.__enter__.return_value.chat.completions.create.return_value = response
        self.assertEqual(interpret('example', context='{}')['amount'], '250.00')
        self.assertEqual(sdk.call_args.kwargs['base_url'], 'https://api.groq.com/openai/v1')
        call = sdk.return_value.__enter__.return_value.chat.completions.create.call_args.kwargs
        self.assertTrue(call['response_format']['json_schema']['strict'])
        response.choices[0].message.content = '{"action":"delete"}'
        with self.assertRaises(AgentUnavailable):
            interpret('example', context='{}')

    @override_settings(BOOKKEEPING_AI_PROVIDER='groq')
    @patch('whatsapp.worker.interpret')
    def test_provider_change_requires_new_consent(self, ai):
        # Existing OpenAI consent does not authorize sending messages to Groq.
        self.verified()
        self.enqueue()
        process_one()
        ai.assert_not_called()
        self.assertContains(self.signed(), 'provider has changed')
        self.assertContains(self.client.get(reverse('whatsapp_setup')), 'Twilio and Groq')

    def test_groq_schema_limits_accounts_to_workspace_codes(self):
        import json
        from agents.bookkeeping import intent_schema
        schema = intent_schema(json.dumps({'payment_accounts':[{'code':'1020','name':'M-Pesa'}], 'expense_categories':[{'code':'5300','name':'Transport'}]}))
        self.assertEqual(schema['properties']['payment_account']['enum'], ['1020', None])
        self.assertEqual(schema['properties']['expense_account']['enum'], ['5300', None])
        self.assertEqual(set(schema['required']), set(schema['properties']))
        self.assertIn('quantity', schema['properties'])
        self.assertIn('unit_price', schema['properties'])
        self.assertNotIn('default', schema['properties']['quantity'])

    @override_settings(WHATSAPP_LINK_SECRET='dedicated-test-link-secret')
    def test_dedicated_link_secret_is_independent_of_django_signing_key(self):
        from .linking import digest
        before = digest('test-code')
        with override_settings(SECRET_KEY='different-worker-secret'):
            self.assertEqual(digest('test-code'), before)
        with override_settings(WHATSAPP_LINK_SECRET='rotated-link-secret'):
            self.assertNotEqual(digest('test-code'), before)
