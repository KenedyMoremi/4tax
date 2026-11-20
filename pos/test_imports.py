import io
import json
import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from agents.bookkeeping import AgentUnavailable
from agents.stock_import import extract_stock
from bookkeeping.models import Account, JournalEntry
from bookkeeping.services import setup_business
from business_profiles.models import SectorProfile
from .images import prepare_images, MAX_BYTES
from .models import Product, StockImport, StockMovement, Sale


EXTRACTED = {'items': [
    {'name': 'Blue shirt · size M', 'sku': 'SHIRT-M', 'quantity': 2, 'unit_cost': '75.50', 'currency': 'ZAR', 'note': ''},
    {'name': 'Black skirt · size S', 'sku': None, 'quantity': None, 'unit_cost': None, 'currency': None, 'note': 'Quantity unclear'},
], 'warnings': ['Check quantities against goods received.']}


def screenshot(colour='white'):
    stream = io.BytesIO()
    Image.new('RGB', (80, 100), colour).save(stream, 'PNG')
    return SimpleUploadedFile('checkout.png', stream.getvalue(), content_type='image/png')


@override_settings(GROQ_API_KEY='test-vision-key')
class StockImportTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(username='stock-owner')
        self.business = setup_business(owner=self.owner, name='Stock business')
        SectorProfile.objects.create(business=self.business, sector='services', owner_id_number='000000')
        self.other = get_user_model().objects.create_user(username='foreign-stock')
        self.foreign = setup_business(owner=self.other, name='Other stock')
        SectorProfile.objects.create(business=self.foreign, sector='retail', owner_id_number='111111')
        self.cash = Account.objects.get(business=self.business, code='1000')
        self.client.force_login(self.owner)

    def batch(self):
        return StockImport.objects.create(business=self.business, digest=uuid.uuid4().hex, extracted=EXTRACTED, created_by=self.owner)

    def review_payload(self, **changes):
        return {'items-TOTAL_FORMS':'2', 'items-INITIAL_FORMS':'2',
                'items-0-include':'on', 'items-0-name':'Blue shirt · size M', 'items-0-sku':'SHIRT-M',
                'items-0-quantity':'2', 'items-0-product':'',
                'items-1-include':'', 'items-1-name':'Black skirt', 'items-1-sku':'',
                'items-1-quantity':'', 'items-1-product':'',
                'received':'on', 'reviewed':'on'} | changes

    @patch('pos.import_views.extract_stock', return_value=EXTRACTED)
    def test_extract_is_private_and_does_not_change_stock(self, extract):
        response = self.client.post(reverse('pos:import_upload'), {'screenshots': [screenshot()], 'consent':'on'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(StockImport.objects.count(), 1)
        self.assertFalse(Product.objects.exists())
        self.assertFalse(JournalEntry.objects.exists())
        self.assertNotIn('data:image', json.dumps(StockImport.objects.get().extracted))
        page = self.client.get(response.url)
        self.assertContains(page, 'Blue shirt')
        self.assertContains(page, 'ZAR')
        self.assertIn('no-store', page['Cache-Control'])
        again = self.client.post(reverse('pos:import_upload'), {'screenshots': [screenshot()], 'consent':'on'})
        self.assertEqual(again.url, response.url)
        self.assertEqual(extract.call_count, 1)

    @patch('pos.import_views.extract_stock')
    def test_invalid_uploads_and_missing_consent_never_call_ai(self, extract):
        bad = SimpleUploadedFile('fake.png', b'<script>alert(1)</script>', content_type='image/png')
        for files, consent in [([bad], 'on'), ([screenshot()], ''),
                               ([screenshot(), screenshot()], 'on'),
                               ([SimpleUploadedFile('big.png', b'x' * (MAX_BYTES+1))], 'on')]:
            response = self.client.post(reverse('pos:import_upload'), {'screenshots': files, 'consent':consent})
            self.assertEqual(response.status_code, 200)
        extract.assert_not_called()
        self.assertFalse(StockImport.objects.exists())

    def test_received_review_creates_stock_once_without_a_purchase_or_sale(self):
        batch = self.batch()
        url = reverse('pos:import_review', args=[batch.pk])
        data = self.review_payload()
        self.assertEqual(self.client.post(url, data).status_code, 302)
        product = Product.objects.get()
        self.assertEqual(product.stock, Decimal('2'))
        self.assertEqual(product.price, Decimal('0'))
        self.assertEqual(product.name, 'Blue shirt · size M')
        self.assertEqual(StockMovement.objects.count(), 1)
        self.assertFalse(JournalEntry.objects.exists())
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertEqual(StockMovement.objects.count(), 1)
        self.assertEqual(self.client.post(url, data | {'items-0-quantity':'3'}).status_code, 200)
        product.refresh_from_db()
        self.assertEqual(product.stock, 2)

    def test_matches_existing_item_and_preserves_price(self):
        product = Product.objects.create(business=self.business, name='Existing shirt', price=120, track_stock=True, stock=3)
        batch = self.batch()
        response = self.client.post(reverse('pos:import_review', args=[batch.pk]), self.review_payload(**{'items-0-product':str(product.pk)}))
        self.assertEqual(response.status_code, 302)
        product.refresh_from_db()
        self.assertEqual((product.stock, product.price, product.name), (Decimal('5'), Decimal('120'), 'Existing shirt'))
        self.assertEqual(Product.objects.count(), 1)

    def test_confirmation_and_valid_quantities_required(self):
        batch = self.batch()
        url = reverse('pos:import_review', args=[batch.pk])
        for changes in [{'received':''}, {'reviewed':''}, {'items-0-quantity':'-2'}, {'items-0-include':''}]:
            self.assertEqual(self.client.post(url, self.review_payload(**changes)).status_code, 200)
        self.assertFalse(Product.objects.exists())

    def test_tenant_scope_for_upload_review_matching_and_inventory(self):
        foreign = StockImport.objects.create(business=self.foreign, digest='foreign', extracted=EXTRACTED, created_by=self.other)
        url = reverse('pos:import_review', args=[foreign.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, self.review_payload()).status_code, 404)
        product = Product.objects.create(business=self.foreign, name='Hidden foreign stock', price=10, track_stock=True)
        batch = self.batch()
        response = self.client.post(reverse('pos:import_review', args=[batch.pk]), self.review_payload(**{'items-0-product':str(product.pk)}))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(self.client.get(reverse('pos:inventory')), 'Hidden foreign stock')
        self.assertFalse(StockMovement.objects.exists())

    def test_import_rollback_on_stock_failure(self):
        batch = self.batch()
        with patch('pos.import_services.stock_move', side_effect=ValidationError('Stock failure')):
            response = self.client.post(reverse('pos:import_review', args=[batch.pk]), self.review_payload())
        self.assertContains(response, 'Stock failure')
        self.assertFalse(Product.objects.exists())
        batch.refresh_from_db()
        self.assertFalse(batch.applied)

    def sale_payload(self, product, **changes):
        return {'token':str(uuid.uuid4()), 'account':str(self.cash.pk), 'tendered':'150', 'received':'on',
                'items-TOTAL_FORMS':'1', 'items-INITIAL_FORMS':'1', 'items-0-selected':'on',
                'items-0-product':str(product.pk), 'items-0-version':str(product.version),
                'items-0-quantity':'1', 'items-0-selling_price':'150'} | changes

    def test_tick_resale_reduces_stock_posts_journal_and_preserves_catalogue_price(self):
        product = Product.objects.create(business=self.business, name='Imported shirt', price=0, track_stock=True, stock=2)
        data = self.sale_payload(product)
        url = reverse('pos:inventory')
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        sale = Sale.objects.get()
        self.assertEqual(sale.lines.get().unit_price, Decimal('150'))
        product.refresh_from_db()
        self.assertEqual(product.stock, 1)
        self.assertEqual(product.price, 0)
        self.assertEqual(JournalEntry.objects.count(), 1)
        self.assertEqual(self.client.post(url, data).url, response.url)
        self.assertEqual(StockMovement.objects.count(), 1)
        changed = self.client.post(url, data | {'items-0-selling_price':'160','tendered':'160'})
        self.assertContains(changed, 'already used')

    def test_resale_cannot_oversell_or_sell_foreign_stock_or_skip_payment(self):
        product = Product.objects.create(business=self.business, name='Shirt', price=0, track_stock=True, stock=2)
        foreign = Product.objects.create(business=self.foreign, name='Other shirt', price=0, track_stock=True, stock=2)
        for changes in [{'items-0-quantity':'3','tendered':'450'}, {'items-0-product':str(foreign.pk)},
                        {'received':''}, {'items-0-selling_price':'-1'}, {'items-0-selected':''}]:
            self.assertEqual(self.client.post(reverse('pos:inventory'), self.sale_payload(product, **changes)).status_code, 200)
        self.assertFalse(Sale.objects.exists())
        product.refresh_from_db()
        self.assertEqual(product.stock, 2)

    @patch('pos.import_views.extract_stock', side_effect=AgentUnavailable('provider-secret-details'))
    def test_failure_is_safe_and_csrf_is_required(self, extract):
        response = self.client.post(reverse('pos:import_upload'), {'screenshots':[screenshot()], 'consent':'on'})
        self.assertContains(response, 'reader is unavailable')
        self.assertNotContains(response, 'provider-secret-details')
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.owner)
        for name in ['pos:import_upload', 'pos:inventory']:
            self.assertEqual(csrf.post(reverse(name), {}).status_code, 403)

    def test_metadata_stripped_and_large_dimensions_rejected(self):
        images, digest = prepare_images([screenshot()])
        with Image.open(io.BytesIO(images[0])) as image:
            self.assertEqual(image.format, 'JPEG')
            self.assertFalse(image.getexif())
        with patch('pos.images.MAX_PIXELS', 100):
            with self.assertRaises(ValidationError):
                prepare_images([screenshot()])

    @patch('agents.stock_import.OpenAI')
    def test_vision_response_is_validated(self, provider):
        client = provider.return_value.__enter__.return_value
        choice = SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content=json.dumps(EXTRACTED)))
        client.chat.completions.create.return_value = SimpleNamespace(choices=[choice])
        self.assertEqual(extract_stock([b'jpeg-test']), EXTRACTED)
        self.assertEqual(provider.call_args.kwargs['api_key'], 'test-vision-key')
        choice.message.content = '{"customer_address": "unexpected"}'
        with self.assertRaises(AgentUnavailable):
            extract_stock([b'jpeg-test'])
        choice.finish_reason = 'length'
        with self.assertRaises(AgentUnavailable):
            extract_stock([b'jpeg-test'])
