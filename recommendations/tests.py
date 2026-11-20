import json
from types import SimpleNamespace
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from agents.bookkeeping import AgentUnavailable
from agents.recommendations import recommend
from bookkeeping.models import Account, JournalEntry
from bookkeeping.services import setup_business, post_journal
from business_profiles.models import SectorProfile
from .context import snapshot


PLAN = {'summary': 'Review your recorded expenses.',
        'recommendations': [{'title': 'Review spending', 'priority': 'medium', 'evidence_keys': ['expenses'],
            'explanation': 'Check the recorded costs.', 'next_step': 'Review the largest costs this week.',
            'measure': 'Compare recorded expenses next month.'}]}


@override_settings(GROQ_RECOMMENDATIONS_API_KEY='test-key-not-real')
class RecommendationTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(username='recommend-owner')
        self.business = setup_business(owner=self.owner, name='Private business name')
        SectorProfile.objects.create(business=self.business, sector='retail', owner_id_number='private-national-id')
        self.other = get_user_model().objects.create_user(username='other-recommend-owner')
        self.foreign = setup_business(owner=self.other, name='Other private business')
        self.record(self.business, 100)
        self.record(self.foreign, 9000)
        self.client.force_login(self.owner)

    def record(self, business, amount):
        accounts = {a.code: a for a in Account.objects.filter(business=business)}
        post_journal(business=business, user=business.owner, date=timezone.localdate(),
                     description='Private transaction description', source_key='test-recommendations',
                     lines=[(accounts['1000'], amount, 0), (accounts['4000'], 0, amount)])

    def test_snapshot_scoped_and_contains_no_personal_data(self):
        data = snapshot(self.business)
        self.assertEqual(data['metrics']['income']['value'], '100.00')
        self.assertEqual(data['metrics']['previous_income']['value'], '0.00')
        self.assertEqual(data['metrics']['entries']['value'], '1')
        self.assertNotIn('9000', json.dumps(data))
        for text in ['Private', 'private-national-id', self.owner.username]:
            self.assertNotIn(text, json.dumps(data))

    @patch('recommendations.views.recommend', return_value=PLAN)
    def test_post_uses_owner_context_and_displays_evidence_without_writes(self, agent):
        count = JournalEntry.objects.count()
        response = self.client.post(reverse('recommendations'), {'consent': 'on', 'business_id': self.foreign.pk})
        self.assertContains(response, 'Review spending')
        self.assertContains(response, 'Recorded expenses')
        self.assertEqual(agent.call_args.args[0]['metrics']['income']['value'], '100.00')
        self.assertEqual(JournalEntry.objects.count(), count)
        self.assertIn('no-store', response['Cache-Control'])

    @patch('recommendations.views.recommend')
    def test_get_missing_consent_and_empty_books_do_not_call_provider(self, agent):
        self.assertEqual(self.client.get(reverse('recommendations')).status_code, 200)
        self.assertEqual(self.client.post(reverse('recommendations'), {}).status_code, 200)
        owner = get_user_model().objects.create_user(username='empty-recommend-owner')
        setup_business(owner=owner, name='Empty books')
        self.client.force_login(owner)
        response = self.client.post(reverse('recommendations'), {'consent': 'on'})
        self.assertContains(response, 'Record your recent sales and expenses first')
        agent.assert_not_called()

    def test_login_and_csrf_required(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse('recommendations')).status_code, 302)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(client.post(reverse('recommendations'), {'consent': 'on'}).status_code, 403)

    @patch('recommendations.views.recommend', side_effect=AgentUnavailable('secret-provider-error'))
    def test_provider_failure_is_safe(self, agent):
        response = self.client.post(reverse('recommendations'), {'consent': 'on'})
        self.assertContains(response, 'unavailable right now')
        self.assertNotContains(response, 'secret-provider-error')

    @patch('agents.recommendations.OpenAI')
    def test_provider_uses_separate_key_and_validates_response(self, provider):
        client = provider.return_value.__enter__.return_value
        choice = SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content=json.dumps(PLAN)))
        client.chat.completions.create.return_value = SimpleNamespace(choices=[choice])
        self.assertEqual(recommend(snapshot(self.business)), PLAN)
        self.assertEqual(provider.call_args.kwargs['api_key'], 'test-key-not-real')
        self.assertEqual(provider.call_args.kwargs['max_retries'], 0)
        choice.message.content = json.dumps(PLAN).replace('"expenses"', '"unknown_metric"')
        with self.assertRaises(AgentUnavailable):
            recommend(snapshot(self.business))
        choice.finish_reason = 'length'
        with self.assertRaises(AgentUnavailable):
            recommend(snapshot(self.business))

    @override_settings(GROQ_RECOMMENDATIONS_API_KEY='')
    @patch('agents.recommendations.OpenAI')
    def test_missing_separate_key_never_falls_back_to_bookkeeping_key(self, provider):
        with self.assertRaises(AgentUnavailable):
            recommend(snapshot(self.business))
        provider.assert_not_called()
