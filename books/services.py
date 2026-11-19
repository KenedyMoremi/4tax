import uuid
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from .models import Account, Business, Document, DocumentLine, Expense, JournalEntry, JournalLine, Payment, ZERO, money

CHART = [
    ('1000', 'Cash on hand', 'asset', True),
    ('1010', 'Business bank account', 'asset', True),
    ('1020', 'M-Pesa', 'asset', True),
    ('1030', 'EcoCash', 'asset', True),
    ('1100', 'Accounts receivable', 'asset', False),
    ('1200', 'Input VAT', 'asset', False),
    ('2000', 'Accounts payable', 'liability', False),
    ('2100', 'Output VAT', 'liability', False),
    ('3000', 'Owner’s capital', 'equity', False),
    ('3100', 'Owner’s drawings', 'equity', False),
    ('4000', 'Sales revenue', 'income', False),
    ('5000', 'Purchases & materials', 'expense', False),
    ('5100', 'Rent & utilities', 'expense', False),
    ('5200', 'Transport & delivery', 'expense', False),
    ('5300', 'Marketing', 'expense', False),
    ('5400', 'Office & administration', 'expense', False),
    ('5500', 'Other operating expenses', 'expense', False),
]

@transaction.atomic
def setup_business(*, owner, **data):
    business = Business.objects.create(owner=owner, **data)
    Account.objects.bulk_create([Account(business=business, code=code, name=name, kind=kind, is_cash=cash) for code, name, kind, cash in CHART])
    return business

def check_date(date):
    if date > timezone.localdate():
        raise ValidationError('Transactions cannot be posted with a future date.')

def check_tax(business, rate):
    if not business.vat_registered and rate:
        raise ValidationError('Enable VAT registration in business settings before recording VAT.')

def check_amount(amount):
    if amount <= 0 or amount > Decimal('99999999999.99'):
        raise ValidationError('Enter a positive total no greater than M 99,999,999,999.99.')

@transaction.atomic
def post_journal(*, business, user, date, description, source_key, lines, document=None):
    """The sole ledger writer. Validate ownership and balance before persisting any line."""
    check_date(date)
    if user.pk != business.owner_id:
        raise ValidationError('You do not have access to this business.')
    if document and document.business_id != business.pk:
        raise ValidationError('Document belongs to another business.')
    existing = JournalEntry.objects.filter(business=business, source_key=source_key).first()
    if existing:
        return existing
    clean = []
    for account, debit, credit in lines:
        debit, credit = money(debit), money(credit)
        if account.business_id != business.pk:
            raise ValidationError('Every account must belong to this business.')
        if debit == 0 and credit == 0:
            continue
        if debit < 0 or credit < 0 or (debit and credit):
            raise ValidationError('Each line needs either a debit or a credit.')
        check_amount(debit or credit)
        clean.append((account, debit, credit))
    if len(clean) < 2 or sum(x[1] for x in clean) != sum(x[2] for x in clean):
        raise ValidationError('Debits and credits must balance and include at least two lines.')
    entry = JournalEntry.objects.create(business=business, date=date, description=description, source_key=source_key, document=document, created_by=user)
    JournalLine.objects.bulk_create([JournalLine(entry=entry, account=a, debit=d, credit=c) for a,d,c in clean])
    return entry

def prepare_document_lines(doc, business, lines):
    prepared = []
    for row in lines:
        if not row or row.get('DELETE'):
            continue
        line = DocumentLine(document=doc, **{k: row[k] for k in ['description','quantity','unit_price','tax_rate']})
        line.full_clean(exclude=['document'])
        check_tax(business, line.tax_rate)
        prepared.append(line)
    if not prepared:
        raise ValidationError('Add at least one line item.')
    doc.subtotal = sum((x.subtotal for x in prepared), ZERO)
    doc.tax = sum((x.tax for x in prepared), ZERO)
    doc.total = doc.subtotal + doc.tax
    check_amount(doc.total)
    return prepared

@transaction.atomic
def create_document(*, business, user, data, lines, kind):
    business = Business.objects.select_for_update().get(pk=business.pk, owner=user)
    if kind not in Document.Kind.values:
        raise ValidationError('Invalid document type.')
    contact = data['contact']
    allowed = ['customer','both'] if kind == 'invoice' else ['supplier','both']
    if contact.business_id != business.pk or contact.kind not in allowed:
        raise ValidationError('Choose a contact belonging to this business with the correct type.')
    if data['due_date'] < data['issue_date']:
        raise ValidationError('Due date must be on or after issue date.')
    sequence = 'next_invoice' if kind == 'invoice' else 'next_bill'
    number = f'{"INV" if kind == "invoice" else "BILL"}-{getattr(business, sequence):04d}'
    doc = Document(business=business, kind=kind, number=number, business_snapshot={k:getattr(business,k) for k in ['name','address','district','email','phone','tin']}, contact_snapshot={k:getattr(contact,k) for k in ['name','address','email','phone','tin']}, **data)
    prepared = prepare_document_lines(doc, business, lines)
    doc.save()
    DocumentLine.objects.bulk_create(prepared)
    setattr(business, sequence, getattr(business, sequence) + 1)
    business.save(update_fields=[sequence])
    return doc

@transaction.atomic
def post_document(*, document, user):
    business = Business.objects.select_for_update().get(pk=document.business_id, owner=user)
    doc = Document.objects.select_for_update().get(pk=document.pk, business=business)
    if doc.status == 'posted':
        return doc
    if doc.status != 'draft':
        raise ValidationError('Only draft documents can be posted.')
    check_date(doc.issue_date)
    accounts = {a.code: a for a in business.account_set.all()}
    if doc.kind == 'invoice':
        lines = [(accounts['1100'], doc.total, 0), (accounts['4000'], 0, doc.subtotal), (accounts['2100'], 0, doc.tax)]
    else:
        lines = [(accounts['5000'], doc.subtotal, 0), (accounts['1200'], doc.tax, 0), (accounts['2000'], 0, doc.total)]
    post_journal(business=business, user=user, date=doc.issue_date, description=f'{doc.number} · {doc.contact.name}', source_key=f'document:{doc.pk}', lines=lines, document=doc)
    doc.status = 'posted'
    doc.save(update_fields=['status'])
    return doc

@transaction.atomic
def record_payment(*, document, user, account, amount, date, reference, token):
    business = Business.objects.select_for_update().get(pk=document.business_id, owner=user)
    doc = Document.objects.select_for_update().get(pk=document.pk, business=business)
    previous = Payment.objects.filter(token=token).first()
    if previous:
        if previous.document_id == doc.pk and previous.amount == amount and previous.account_id == account.pk and previous.date == date and previous.reference == reference:
            return previous
        raise ValidationError('This payment request has already been used.')
    check_date(date)
    check_amount(amount)
    if doc.status != 'posted' or amount > doc.balance:
        raise ValidationError('Payment must not exceed the outstanding balance of a posted document.')
    if date < doc.issue_date:
        raise ValidationError('Payment date cannot be before the document date.')
    if account.business_id != business.pk or not account.is_cash:
        raise ValidationError('Choose a cash, bank or mobile money account for this business.')
    control = business.account_set.get(code='1100' if doc.kind == 'invoice' else '2000')
    lines = [(account, amount, 0), (control, 0, amount)] if doc.kind == 'invoice' else [(control, amount, 0), (account, 0, amount)]
    payment = Payment.objects.create(document=doc, account=account, amount=amount, date=date, reference=reference, token=token)
    post_journal(business=business, user=user, date=date, description=f'Payment · {doc.number}', source_key=f'payment:{payment.pk}', lines=lines, document=doc)
    doc.paid += amount
    doc.save(update_fields=['paid'])
    return payment

@transaction.atomic
def void_document(*, document, user):
    business = Business.objects.select_for_update().get(pk=document.business_id, owner=user)
    doc = Document.objects.select_for_update().get(pk=document.pk, business=business)
    if doc.status == 'void':
        return
    if doc.paid:
        raise ValidationError('A document with payments cannot be voided.')
    if doc.status == 'posted':
        original = JournalEntry.objects.get(business=business, source_key=f'document:{doc.pk}')
        post_journal(business=business, user=user, date=timezone.localdate(), description=f'Void · {doc.number}', source_key=f'void-document:{doc.pk}', document=doc, lines=[(line.account, line.credit, line.debit) for line in original.lines.select_related('account')])
    doc.status = 'void'
    doc.save(update_fields=['status'])

@transaction.atomic
def record_expense(*, business, user, data):
    business = Business.objects.select_for_update().get(pk=business.pk, owner=user)
    previous = Expense.objects.filter(token=data['token']).first()
    if previous:
        if previous.business_id == business.pk and all(getattr(previous, k) == v for k,v in data.items()):
            return previous
        raise ValidationError('This expense request has already been used.')
    expense = Expense(business=business, **data)
    expense.full_clean()
    if expense.category.business_id != business.pk or expense.category.kind != 'expense':
        raise ValidationError('Choose an expense category for this business.')
    if expense.paid_from.business_id != business.pk or not expense.paid_from.is_cash:
        raise ValidationError('Choose a payment account for this business.')
    if expense.supplier and (expense.supplier.business_id != business.pk or expense.supplier.kind not in ['supplier','both']):
        raise ValidationError('Choose a supplier for this business.')
    check_date(expense.date)
    check_tax(business, expense.tax_rate)
    check_amount(expense.total)
    expense.save()
    post_journal(business=business, user=user, date=expense.date, description=expense.description, source_key=f'expense:{expense.pk}', lines=[(expense.category, expense.amount, 0), (business.account_set.get(code='1200'), expense.tax, 0), (expense.paid_from, 0, expense.total)])
    return expense

@transaction.atomic
def void_expense(*, expense, user):
    business = Business.objects.select_for_update().get(pk=expense.business_id, owner=user)
    expense = Expense.objects.select_for_update().get(pk=expense.pk, business=business)
    if expense.void:
        return
    original = JournalEntry.objects.get(business=business, source_key=f'expense:{expense.pk}')
    post_journal(business=business, user=user, date=timezone.localdate(), description=f'Void expense · {expense.description}'[:250], source_key=f'void-expense:{expense.pk}', lines=[(line.account, line.credit, line.debit) for line in original.lines.select_related('account')])
    expense.void = True
    expense.save(update_fields=['void'])

@transaction.atomic
def record_transfer(*, business, user, debit_account, credit_account, amount, date, description, token):
    business = Business.objects.select_for_update().get(pk=business.pk, owner=user)
    if debit_account == credit_account:
        raise ValidationError('Choose two different accounts.')
    # Control accounts are maintained only by invoices, bills and payments.
    if any(a.code in ['1100','1200','2000','2100'] for a in [debit_account,credit_account]):
        raise ValidationError('Control accounts cannot be changed with a manual entry.')
    check_amount(amount)
    return post_journal(business=business, user=user, date=date, description=description, source_key=f'manual:{token}', lines=[(debit_account,amount,0),(credit_account,0,amount)])


@transaction.atomic
def reverse_payment(*, payment, user):
    business = Business.objects.select_for_update().get(pk=payment.document.business_id, owner=user)
    doc = Document.objects.select_for_update().get(pk=payment.document_id, business=business)
    payment = Payment.objects.select_for_update().get(pk=payment.pk, document=doc)
    if payment.reversed:
        return
    original = JournalEntry.objects.get(business=business, source_key=f'payment:{payment.pk}')
    post_journal(business=business, user=user, date=timezone.localdate(), description=f'Reverse payment · {doc.number}', source_key=f'reverse-payment:{payment.pk}', document=doc, lines=[(line.account, line.credit, line.debit) for line in original.lines.select_related('account')])
    payment.reversed = True
    payment.save(update_fields=['reversed'])
    doc.paid -= payment.amount
    doc.save(update_fields=['paid'])


@transaction.atomic
def update_draft(*, document, user, data, lines):
    business = Business.objects.select_for_update().get(pk=document.business_id, owner=user)
    doc = Document.objects.select_for_update().get(pk=document.pk, business=business)
    if doc.status != 'draft':
        raise ValidationError('Only drafts can be edited. Posted amounts are final.')
    contact = data['contact']
    allowed = ['customer','both'] if doc.kind == 'invoice' else ['supplier','both']
    if contact.business_id != business.pk or contact.kind not in allowed:
        raise ValidationError('Choose a contact for this business with the correct type.')
    if data['due_date'] < data['issue_date']:
        raise ValidationError('Due date must be on or after issue date.')
    for key in ['contact','issue_date','due_date','notes']:
        setattr(doc, key, data[key])
    doc.business_snapshot = {k:getattr(business,k) for k in ['name','address','district','email','phone','tin']}
    doc.contact_snapshot = {k:getattr(contact,k) for k in ['name','address','email','phone','tin']}
    prepared = prepare_document_lines(doc,business,lines)
    doc.save()
    doc.lines.all().delete()
    DocumentLine.objects.bulk_create(prepared)
    return doc

@transaction.atomic
def reverse_manual(*, entry, user):
    business = Business.objects.select_for_update().get(pk=entry.business_id, owner=user)
    original = JournalEntry.objects.get(pk=entry.pk, business=business)
    if not original.source_key.startswith('manual:'):
        raise ValidationError('Reverse this transaction from its original document or expense.')
    return post_journal(business=business, user=user, date=timezone.localdate(), description=f'Reverse journal · JE-{original.pk:05d}', source_key=f'reverse-manual:{original.pk}', lines=[(line.account,line.credit,line.debit) for line in original.lines.select_related('account')])
