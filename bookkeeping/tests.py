import uuid
from datetime import timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from . import services
from .models import Account, Business, Contact, Document, Expense, JournalEntry, JournalLine, Payment
from .reporting import financial_report

class BooksTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username='owner', password='Test-safe-password-381')
        cls.other = get_user_model().objects.create_user(username='other', password='Test-safe-password-382')
        cls.business = services.setup_business(owner=cls.user, name='Test enterprise', vat_registered=True, default_tax_rate=Decimal('14'))
        cls.other_business = services.setup_business(owner=cls.other, name='Other enterprise')
        cls.customer = Contact.objects.create(business=cls.business, name='Sample customer')
        cls.supplier = Contact.objects.create(business=cls.business, name='Sample supplier', kind='supplier')
        cls.other_contact = Contact.objects.create(business=cls.other_business, name='Private customer')
        cls.today = timezone.localdate()

    def setUp(self):
        self.client.force_login(self.user)

    def account(self, code, business=None):
        return Account.objects.get(business=business or self.business, code=code)

    def document(self, kind='invoice', price='100', tax='14', business=None, user=None, contact=None, date=None):
        return services.create_document(business=business or self.business, user=user or self.user, kind=kind, data={'contact':contact or (self.customer if kind == 'invoice' else self.supplier), 'issue_date':date or self.today, 'due_date':self.today+timedelta(days=14), 'notes':''}, lines=[{'description':'Test service', 'quantity':Decimal('1'), 'unit_price':Decimal(price), 'tax_rate':Decimal(tax)}])

    def pay(self, doc, amount='50', token=None, **kwargs):
        return services.record_payment(document=doc, user=self.user, account=self.account('1010'), amount=Decimal(amount), date=kwargs.pop('date',self.today), reference='Receipt', token=token or uuid.uuid4(), **kwargs)

    def expense_data(self, **overrides):
        data = {'description':'Office expense', 'supplier':self.supplier, 'date':self.today, 'category':self.account('5400'), 'paid_from':self.account('1010'), 'amount':Decimal('50'), 'tax_rate':Decimal('14'), 'token':uuid.uuid4()}
        return data | overrides

    def test_new_business_has_chart(self):
        self.assertEqual(Account.objects.filter(business=self.business).count(),17)

    def test_document_and_payment_balanced_and_idempotent(self):
        doc = self.document()
        self.assertEqual(doc.total,Decimal('114'))
        self.assertFalse(JournalEntry.objects.exists())
        services.post_document(document=doc, user=self.user)
        services.post_document(document=doc, user=self.user)
        self.assertEqual(JournalEntry.objects.count(),1)
        token = uuid.uuid4()
        first = self.pay(doc,token=token)
        second = self.pay(doc,token=token)
        self.assertEqual(first.pk,second.pk)
        doc.refresh_from_db()
        self.assertEqual(doc.balance,Decimal('64'))
        self.assertEqual(doc.display_status,'Part paid')
        totals = JournalLine.objects.aggregate(d=Sum('debit'), c=Sum('credit'))
        self.assertEqual(totals['d'], totals['c'])
        self.assertEqual(Payment.objects.count(),1)

    def test_overpayment_rolls_back(self):
        doc = self.document()
        services.post_document(document=doc,user=self.user)
        with self.assertRaises(ValidationError):
            self.pay(doc,amount='115')
        self.assertEqual(Payment.objects.count(),0)
        self.assertEqual(JournalEntry.objects.count(),1)

    def test_draft_cannot_be_paid(self):
        with self.assertRaises(ValidationError):
            self.pay(self.document())

    def test_paid_document_cannot_be_voided(self):
        doc = self.document()
        services.post_document(document=doc,user=self.user)
        self.pay(doc)
        with self.assertRaises(ValidationError):
            services.void_document(document=doc,user=self.user)

    def test_void_reverses_entries_only_once(self):
        doc = self.document()
        services.post_document(document=doc,user=self.user)
        services.void_document(document=doc,user=self.user)
        services.void_document(document=doc,user=self.user)
        self.assertEqual(JournalEntry.objects.count(),2)
        report = financial_report(self.business, self.today,self.today)
        self.assertEqual(report['income'],0)
        self.assertEqual(report['assets'],0)
        with self.assertRaises(ValidationError):
            services.post_document(document=doc,user=self.user)

    def test_bill_and_expense_report(self):
        doc = self.document(kind='bill')
        services.post_document(document=doc,user=self.user)
        services.record_expense(business=self.business,user=self.user,data=self.expense_data())
        report = financial_report(self.business,self.today,self.today)
        self.assertEqual(report['expenses'],Decimal('150'))
        self.assertEqual(report['vat_in'],Decimal('21'))
        self.assertEqual(report['liabilities'],Decimal('114'))
        self.assertEqual(report['balance_difference'],0)
        self.assertEqual(report['trial_debits'],report['trial_credits'])

    def test_rounding_per_line(self):
        doc = self.document(price='0.05',tax='10')
        self.assertEqual(doc.tax,Decimal('0.01'))
        self.assertEqual(doc.total,Decimal('0.06'))

    def test_expense_idempotency_and_reversal(self):
        data = self.expense_data()
        expense = services.record_expense(business=self.business,user=self.user,data=data)
        again = services.record_expense(business=self.business,user=self.user,data=data)
        self.assertEqual(expense.pk,again.pk)
        services.void_expense(expense=expense,user=self.user)
        services.void_expense(expense=expense,user=self.user)
        self.assertEqual(JournalEntry.objects.count(),2)
        self.assertEqual(financial_report(self.business,self.today,self.today)['expenses'],0)

    def test_tax_requires_registration(self):
        with self.assertRaises(ValidationError):
            self.document(business=self.other_business,user=self.other,contact=self.other_contact)
        self.assertFalse(Document.objects.exists())

    def test_invalid_dates_and_future_posting(self):
        doc = self.document(date=self.today+timedelta(days=1))
        with self.assertRaises(ValidationError):
            services.post_document(document=doc,user=self.user)
        self.assertFalse(JournalEntry.objects.exists())
        doc = self.document()
        services.post_document(document=doc,user=self.user)
        with self.assertRaises(ValidationError):
            self.pay(doc,date=self.today-timedelta(days=1))

    def test_journal_rejects_unbalanced_and_cross_tenant_lines(self):
        for lines in [[(self.account('1000'),10,0),(self.account('3000'),0,9)],[(self.account('1000'),10,0),(self.account('3000',self.other_business),0,10)]]:
            with self.assertRaises(ValidationError):
                services.post_journal(business=self.business,user=self.user,date=self.today,description='Invalid',source_key=str(uuid.uuid4()),lines=lines)
        self.assertFalse(JournalEntry.objects.exists())

    def test_cannot_manually_adjust_control_accounts(self):
        with self.assertRaises(ValidationError):
            services.record_transfer(business=self.business,user=self.user,debit_account=self.account('1100'),credit_account=self.account('3000'),amount=Decimal('100'),date=self.today,description='Bad adjustment',token=uuid.uuid4())

    def test_cross_tenant_detail_write_and_lists(self):
        doc = self.document(business=self.other_business,user=self.other,contact=self.other_contact,tax='0')
        for name,args in [('document_detail',[doc.pk]),('payment_create',[doc.pk]),('contact_edit',[self.other_contact.pk])]:
            self.assertEqual(self.client.get(reverse(name,args=args)).status_code,404)
        for action in ['post','void']:
            self.assertEqual(self.client.post(reverse('document_action',args=[doc.pk,action])).status_code,404)
        self.assertNotContains(self.client.get(reverse('contacts')),'Private customer')
        self.assertNotContains(self.client.get(reverse('documents',args=['invoice'])),'INV-0001')

    def test_form_rejects_foreign_contact(self):
        response = self.client.post(reverse('document_create',args=['invoice']), self.document_payload(contact=self.other_contact.pk))
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'Select a valid choice')
        self.assertFalse(Document.objects.exists())

    def document_payload(self, **overrides):
        return {'contact':self.customer.pk, 'issue_date':str(self.today), 'due_date':str(self.today), 'notes':'Test', 'lines-TOTAL_FORMS':'1','lines-INITIAL_FORMS':'0','lines-MIN_NUM_FORMS':'1','lines-MAX_NUM_FORMS':'50', 'lines-0-description':'Design work','lines-0-quantity':'2','lines-0-unit_price':'125.50','lines-0-tax_rate':'14'} | overrides

    def test_complete_invoice_through_views(self):
        response = self.client.post(reverse('document_create',args=['invoice']),self.document_payload())
        doc = Document.objects.get()
        self.assertRedirects(response,reverse('document_detail',args=[doc.pk]))
        self.assertEqual(doc.total,Decimal('286.14'))
        self.assertEqual(self.client.get(reverse('document_action',args=[doc.pk,'post'])).status_code,405)
        self.client.post(reverse('document_action',args=[doc.pk,'post']))
        response = self.client.post(reverse('payment_create',args=[doc.pk]),{'amount':'286.14','date':str(self.today),'account':self.account('1020').pk,'reference':'Mobile receipt','token':str(uuid.uuid4())})
        self.assertEqual(response.status_code,302)
        doc.refresh_from_db()
        self.assertEqual(doc.display_status,'Paid')
        self.assertContains(self.client.get(reverse('document_detail',args=[doc.pk])),'Mobile receipt')

    def test_expense_form_rejects_foreign_accounts(self):
        data = {'description':'Expense','date':str(self.today),'category':self.account('5400',self.other_business).pk,'paid_from':self.account('1010').pk,'amount':'20','tax_rate':'0','token':str(uuid.uuid4())}
        response = self.client.post(reverse('expense_create'),data)
        self.assertContains(response,'Select a valid choice')
        self.assertFalse(Expense.objects.exists())

    def test_all_pages_render_and_csv(self):
        doc = self.document()
        services.post_document(document=doc,user=self.user)
        self.pay(doc)
        services.record_expense(business=self.business,user=self.user,data=self.expense_data())
        for name, args in [('dashboard',[]),('documents',['invoice']),('documents',['bill']),('document_create',['invoice']),('document_create',['bill']),('document_detail',[doc.pk]),('payment_create',[doc.pk]),('contacts',[]),('contact_create',[]),('contact_edit',[self.customer.pk]),('expenses',[]),('expense_create',[]),('ledger',[]),('transfer_create',[]),('reports',[]),('accounts',[]),('settings',[]),('password_change',[])]:
            with self.subTest(page=name,args=args):
                self.assertEqual(self.client.get(reverse(name,args=args)).status_code,200)
        response = self.client.get(reverse('reports'),{'export':'csv'})
        self.assertEqual(response.status_code,200)
        self.assertIn('text/csv',response['Content-Type'])
        self.assertContains(response,'Sales revenue')

    def test_period_reports_exclude_earlier_income_but_keep_balance(self):
        doc = self.document(date=self.today-timedelta(days=40))
        services.post_document(document=doc,user=self.user)
        report = financial_report(self.business,self.today,self.today)
        self.assertEqual(report['income'],0)
        self.assertEqual(report['retained'],100)
        self.assertEqual(report['balance_difference'],0)

    def test_report_date_validation(self):
        response = self.client.get(reverse('reports'),{'start':'not-a-date','end':str(self.today)})
        self.assertContains(response,'Enter a valid date')
        response = self.client.get(reverse('reports'),{'start':str(self.today),'end':str(self.today-timedelta(days=1))})
        self.assertContains(response,'Start date must be before')

    def test_csrf_required(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        response = client.post(reverse('document_create',args=['invoice']),self.document_payload())
        self.assertEqual(response.status_code,403)

    def test_anonymous_redirect_and_onboarding(self):
        self.client.logout()
        self.assertRedirects(self.client.get('/'),reverse('login')+'?next=/')
        user = get_user_model().objects.create_user(username='new-owner',password='Test-safe-password-389')
        self.client.force_login(user)
        self.assertRedirects(self.client.get('/'),reverse('onboarding'))
        response = self.client.post(reverse('onboarding'),{'name':'New business','district':'Maseru','default_tax_rate':'0'})
        self.assertRedirects(response,'/')
        self.assertEqual(Account.objects.filter(business__owner=user).count(),17)

    def test_signup_creates_custom_user(self):
        self.client.logout()
        response = self.client.post(reverse('signup'),{'username':'new-person','email':'person@example.invalid','password1':'Fresh-password-5261','password2':'Fresh-password-5261'})
        self.assertRedirects(response,reverse('onboarding'))
        self.assertTrue(get_user_model().objects.filter(username='new-person').exists())

    def test_payment_reversal_restores_balance_once(self):
        doc = self.document()
        services.post_document(document=doc,user=self.user)
        payment = self.pay(doc,amount='114')
        response = self.client.post(reverse('payment_reverse',args=[payment.pk]))
        self.assertRedirects(response,reverse('document_detail',args=[doc.pk]))
        self.client.post(reverse('payment_reverse',args=[payment.pk]))
        doc.refresh_from_db()
        self.assertEqual(doc.paid,0)
        self.assertEqual(JournalEntry.objects.count(),3)
        services.void_document(document=doc,user=self.user)
        report = financial_report(self.business,self.today,self.today)
        self.assertEqual(report['assets'],0)
        self.assertEqual(report['income'],0)

    def test_payment_reversal_tenant_isolation(self):
        doc = self.document()
        services.post_document(document=doc,user=self.user)
        payment = self.pay(doc)
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(reverse('payment_reverse',args=[payment.pk])).status_code,404)
        payment.refresh_from_db()
        self.assertFalse(payment.reversed)

    def test_invoice_keeps_business_and_customer_snapshot(self):
        doc = self.document()
        self.customer.name = 'Changed customer'
        self.customer.save()
        self.business.name = 'Changed business'
        self.business.save()
        response = self.client.get(reverse('document_detail',args=[doc.pk]))
        self.assertContains(response,'Sample customer')
        self.assertContains(response,'Test enterprise')

    def test_edit_draft_preserves_number_and_replaces_lines(self):
        doc = self.document()
        response = self.client.post(reverse('document_edit',args=[doc.pk]),self.document_payload(**{'lines-0-unit_price':'200'}))
        self.assertRedirects(response,reverse('document_detail',args=[doc.pk]))
        doc.refresh_from_db()
        self.assertEqual(doc.number,'INV-0001')
        self.assertEqual(doc.total,Decimal('456'))
        self.assertEqual(doc.lines.count(),1)
        self.assertFalse(JournalEntry.objects.exists())
        services.post_document(document=doc,user=self.user)
        self.client.post(reverse('document_edit',args=[doc.pk]),self.document_payload())
        doc.refresh_from_db()
        self.assertEqual(doc.total,Decimal('456'))
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse('document_edit',args=[doc.pk])).status_code,404)

    def test_manual_entry_reversal_is_idempotent(self):
        entry = services.record_transfer(business=self.business,user=self.user,debit_account=self.account('1010'),credit_account=self.account('3000'),amount=Decimal('200'),date=self.today,description='Owner funding',token=uuid.uuid4())
        for _ in range(2):
            self.client.post(reverse('journal_reverse',args=[entry.pk]))
        self.assertEqual(JournalEntry.objects.count(),2)
        self.assertEqual(financial_report(self.business,self.today,self.today)['assets'],0)
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(reverse('journal_reverse',args=[entry.pk])).status_code,404)
