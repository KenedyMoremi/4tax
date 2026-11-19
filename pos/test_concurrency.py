import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import connection, connections
from django.test import Client, TransactionTestCase
from django.urls import reverse

from bookkeeping.models import Account, JournalEntry
from bookkeeping.services import setup_business
from business_profiles.models import SectorProfile
from .models import Product, Sale, Refund


@skipUnless(connection.vendor == 'postgresql', 'Requires a disposable PostgreSQL database')
class PosConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(username='pos-race')
        business = setup_business(owner=self.owner, name='Test store')
        SectorProfile.objects.create(business=business, sector='retail', owner_id_number='000001')
        self.product = Product.objects.create(business=business, name='Last item', price=20, stock=1, track_stock=True)
        account = Account.objects.get(business=business, code='1000')
        self.data = {'token': str(uuid.uuid4()), 'account': str(account.pk), 'tendered': '20.00', 'received': 'on',
                     'items-TOTAL_FORMS': '1', 'items-INITIAL_FORMS': '0', 'items-0-product': str(self.product.pk),
                     'items-0-quantity': '1', 'items-0-version': '1'}

    def race(self, url, payloads):
        barrier = Barrier(2)
        def submit(payload):
            try:
                client = Client()
                client.force_login(self.owner)
                barrier.wait(timeout=10)
                response = client.post(url, payload)
                return response.status_code, response.headers.get('Location')
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(submit, payloads))

    def test_last_item_cannot_be_sold_twice(self):
        results = self.race(reverse('pos:terminal'), [self.data, self.data | {'token': str(uuid.uuid4())}])
        self.assertEqual(sorted(code for code, _ in results), [200, 302])
        self.assertEqual(Sale.objects.count(), 1)
        self.assertEqual(JournalEntry.objects.count(), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 0)

    def test_checkout_retries_post_once(self):
        results = self.race(reverse('pos:terminal'), [self.data, self.data])
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0][0], 302)
        self.assertEqual(Sale.objects.count(), 1)
        self.assertEqual(JournalEntry.objects.count(), 1)

    def test_refund_retries_restore_stock_once(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(reverse('pos:terminal'), self.data).status_code, 302)
        sale = Sale.objects.get()
        data = {'reason': 'Returned item', 'restock': 'on', 'paid': 'on'}
        results = self.race(reverse('pos:refund', args=[sale.pk]), [data, data])
        self.assertEqual([code for code, _ in results], [302, 302])
        self.assertEqual(Refund.objects.count(), 1)
        self.assertEqual(JournalEntry.objects.count(), 2)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 1)
