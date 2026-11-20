import uuid
from decimal import Decimal
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from bookkeeping.models import Account, JournalEntry, JournalLine
from bookkeeping.services import setup_business
from bookkeeping.reporting import financial_report
from django.utils import timezone
from business_profiles.models import SectorProfile
from .models import Product, Sale, Refund, StockMovement


class PosTests(TestCase):
    def setUp(self):
        self.owner=get_user_model().objects.create_user(username='pos-owner',password='test-password')
        self.other=get_user_model().objects.create_user(username='pos-other')
        self.business=setup_business(owner=self.owner,name='Example store')
        self.foreign=setup_business(owner=self.other,name='Other store')
        for business in [self.business,self.foreign]:
            SectorProfile.objects.create(business=business,sector='retail',owner_id_number='000001')
        self.product=Product.objects.create(business=self.business,name='Apples',sku='TEST-1',unit='kg',price='20.00',track_stock=True,stock='10.00')
        self.cash=Account.objects.get(business=self.business,code='1000')
        self.client.force_login(self.owner)

    def payload(self,**changes):
        return {'token':str(uuid.uuid4()),'account':str(self.cash.pk),'tendered':'100.00','received':'on','customer_name':'Test Customer','reference':'',
                'items-TOTAL_FORMS':'1','items-INITIAL_FORMS':'0','items-0-product':str(self.product.pk),'items-0-quantity':'2.50','items-0-version':'1'} | changes

    def buy(self,**changes):
        response=self.client.post(reverse('pos:terminal'),self.payload(**changes))
        self.assertEqual(response.status_code,302,response.content.decode()[:3000])
        return Sale.objects.latest('pk')

    def test_checkout_posts_balanced_sale_and_stock_and_receipt(self):
        sale=self.buy()
        self.assertEqual(sale.total,Decimal('50.00'))
        self.assertEqual(sale.change,Decimal('50.00'))
        self.product.refresh_from_db();self.assertEqual(self.product.stock,Decimal('7.50'))
        self.assertEqual(StockMovement.objects.get().quantity,Decimal('-2.50'))
        lines=sale.journal.lines.aggregate(debits=Sum('debit'),credits=Sum('credit'))
        self.assertEqual(lines,{'debits':Decimal('50.00'),'credits':Decimal('50.00')})
        report=financial_report(self.business,timezone.localdate(),timezone.localdate())
        self.assertEqual(report['income'],Decimal('50.00'))
        response=self.client.get(reverse('pos:receipt',args=[sale.pk]))
        self.assertContains(response,sale.reference)
        self.assertContains(response,'50.00')
        self.assertIn('no-store',response.headers['Cache-Control'])

    def test_retry_does_not_repost_or_reduce_stock_twice(self):
        data=self.payload()
        first=self.client.post(reverse('pos:terminal'),data)
        second=self.client.post(reverse('pos:terminal'),data)
        self.assertEqual(first.url,second.url)
        self.assertEqual(Sale.objects.count(),1)
        self.assertEqual(JournalEntry.objects.count(),1)
        self.assertEqual(StockMovement.objects.count(),1)
        response=self.client.post(reverse('pos:terminal'),data|{'customer_name':'Changed'})
        self.assertContains(response,'already used')

    def test_insufficient_stock_underpayment_and_changed_price_are_rejected(self):
        for changes in [{'items-0-quantity':'11','tendered':'500'}, {'tendered':'49.99'}, {'items-0-version':'2'}, {'items-0-quantity':'-1'}]:
            self.assertEqual(self.client.post(reverse('pos:terminal'),self.payload(**changes)).status_code,200)
        self.assertFalse(Sale.objects.exists())
        self.assertFalse(JournalEntry.objects.exists())
        self.product.refresh_from_db();self.assertEqual(self.product.stock,Decimal('10'))

    def test_mobile_money_requires_exact_payment_and_records_correct_account(self):
        mpesa=Account.objects.get(business=self.business,code='1020')
        response=self.client.post(reverse('pos:terminal'),self.payload(account=str(mpesa.pk)))
        self.assertContains(response,'must equal the sale total')
        sale=self.buy(account=str(mpesa.pk),tendered='50',reference='TEST-MPESA')
        self.assertEqual(sale.payment_account,mpesa)
        self.assertEqual(sale.change,0)
        self.assertEqual(sale.journal.lines.get(account=mpesa).debit,Decimal('50'))

    def test_tax_uses_existing_registration_and_per_line_rounding(self):
        self.product.tax_rate=Decimal('15');self.product.price=Decimal('0.05');self.product.save()
        self.assertEqual(self.client.post(reverse('pos:terminal'),self.payload()).status_code,200)
        self.assertFalse(Sale.objects.exists())
        self.business.vat_registered=True;self.business.save()
        sale=self.buy(**{'items-0-quantity':'3'})
        self.assertEqual(sale.subtotal,Decimal('0.15'))
        self.assertEqual(sale.tax,Decimal('0.02'))
        self.assertEqual(sale.total,Decimal('0.17'))
        self.assertEqual(sale.journal.lines.get(account__code='2100').credit,Decimal('0.02'))

    def test_cross_business_items_accounts_receipts_and_catalog_are_rejected(self):
        product=Product.objects.create(business=self.foreign,name='Foreign item',price=10)
        account=Account.objects.get(business=self.foreign,code='1000')
        for changes in [{'items-0-product':str(product.pk)},{'account':str(account.pk)}]:
            self.assertEqual(self.client.post(reverse('pos:terminal'),self.payload(**changes)).status_code,200)
        self.assertFalse(Sale.objects.exists())
        sale=self.buy()
        self.client.force_login(self.other)
        for route,args in [('pos:receipt',[sale.pk]),('pos:refund',[sale.pk]),('pos:product_edit',[self.product.pk]),('pos:stock',[self.product.pk])]:
            self.assertEqual(self.client.get(reverse(route,args=args)).status_code,404)
        self.assertEqual(self.client.post(reverse('pos:refund',args=[sale.pk]),{'reason':'Wrong tenant','paid':'on','restock':'on'}).status_code,404)

    def test_refund_reverses_ledger_and_restocks_exactly_once(self):
        sale=self.buy()
        data={'reason':'Customer return','restock':'on','paid':'on'}
        url=reverse('pos:refund',args=[sale.pk])
        for _ in range(2):self.assertEqual(self.client.post(url,data).status_code,302)
        self.assertEqual(Refund.objects.count(),1)
        self.assertEqual(JournalEntry.objects.count(),2)
        self.product.refresh_from_db();self.assertEqual(self.product.stock,Decimal('10'))
        self.assertEqual(StockMovement.objects.count(),2)
        report=financial_report(self.business,timezone.localdate(),timezone.localdate())
        self.assertEqual(report['income'],Decimal('0'))
        self.assertContains(self.client.get(reverse('pos:receipt',args=[sale.pk])),'Refunded sale')
        self.assertContains(self.client.post(url,data|{'restock':''}),'already been refunded')

    def test_refund_without_restock_and_payment_acknowledgement(self):
        sale=self.buy()
        url=reverse('pos:refund',args=[sale.pk])
        self.assertEqual(self.client.post(url,{'reason':'Damaged goods'}).status_code,200)
        self.assertFalse(Refund.objects.exists())
        self.assertEqual(self.client.post(url,{'reason':'Damaged goods','paid':'on'}).status_code,302)
        self.product.refresh_from_db();self.assertEqual(self.product.stock,Decimal('7.50'))

    def test_stock_adjustments_are_audited_idempotent_and_nonnegative(self):
        url=reverse('pos:stock',args=[self.product.pk])
        data={'token':str(uuid.uuid4()),'quantity':'5','reason':'Delivery'}
        for _ in range(2):self.assertEqual(self.client.post(url,data).status_code,302)
        self.product.refresh_from_db();self.assertEqual(self.product.stock,Decimal('15'))
        self.assertEqual(StockMovement.objects.count(),1)
        self.assertEqual(self.client.post(url,data|{'token':str(uuid.uuid4()),'quantity':'-16'}).status_code,200)
        self.product.refresh_from_db();self.assertEqual(self.product.stock,Decimal('15'))
        self.assertFalse(JournalEntry.objects.exists())

    def test_catalog_snapshots_stale_edits_and_stock_tracking_guard(self):
        sale=self.buy()
        url=reverse('pos:product_edit',args=[self.product.pk])
        data={'name':'New name','sku':'TEST-1','unit':'kg','price':'30','tax_rate':'0','track_stock':'on','active':'on','version':'1'}
        self.assertEqual(self.client.post(url,data).status_code,302)
        self.assertContains(self.client.post(url,data),'another tab')
        self.assertEqual(sale.lines.get().unit_price,Decimal('20'))
        self.assertEqual(sale.lines.get().name,'Apples')
        self.assertContains(self.client.post(url,data|{'version':'2','track_stock':''}),'cannot change')

    def test_all_five_sectors_allowed_and_missing_profile_denied(self):
        for sector in ['transport','services','ecommerce','retail','agriculture']:
            SectorProfile.objects.filter(business=self.business).update(sector=sector)
            self.assertEqual(self.client.get(reverse('pos:terminal')).status_code,200)
        SectorProfile.objects.filter(business=self.business).delete()
        self.assertEqual(self.client.post(reverse('pos:terminal'),self.payload()).status_code,403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('pos:terminal')).status_code,302)

    def test_csrf_and_atomic_rollback(self):
        csrf=Client(enforce_csrf_checks=True);csrf.force_login(self.owner)
        self.assertEqual(csrf.post(reverse('pos:terminal'),self.payload()).status_code,403)
        with patch('pos.services.stock_move',side_effect=ValidationError('Stock failure')):
            self.assertContains(self.client.post(reverse('pos:terminal'),self.payload()),'Stock failure')
        self.assertFalse(Sale.objects.exists())
        self.assertFalse(JournalEntry.objects.exists())
        self.product.refresh_from_db();self.assertEqual(self.product.stock,Decimal('10'))

    def test_duplicate_cart_lines_are_grouped_and_cannot_bypass_stock(self):
        data=self.payload(**{'items-TOTAL_FORMS':'2','items-0-quantity':'6','items-1-product':str(self.product.pk),'items-1-version':'1','items-1-quantity':'6','tendered':'500'})
        self.assertEqual(self.client.post(reverse('pos:terminal'),data).status_code,200)
        self.assertFalse(Sale.objects.exists())
        data['items-1-quantity']='1'
        self.assertEqual(self.client.post(reverse('pos:terminal'),data).status_code,302)
        self.assertEqual(Sale.objects.get().lines.get().quantity,Decimal('7'))

    def test_untracked_fares_and_server_prices(self):
        self.product.track_stock=False;self.product.save()
        sale=self.buy(**{'items-0-quantity':'50','tendered':'1000','items-0-price':'0.01','total':'0.50'})
        self.assertEqual(sale.total,Decimal('1000'))
        self.assertFalse(StockMovement.objects.exists())
        self.product.refresh_from_db();self.assertEqual(self.product.stock,Decimal('10'))
