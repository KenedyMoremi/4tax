import uuid
from decimal import Decimal, ROUND_HALF_UP
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone

ZERO = Decimal('0.00')
def money(value):
    return Decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

DISTRICTS = [(x, x) for x in ['Maseru', 'Berea', 'Leribe', 'Butha-Buthe', 'Mokhotlong', 'Thaba-Tseka', 'Qacha’s Nek', 'Quthing', 'Mohale’s Hoek', 'Mafeteng']]

class User(AbstractUser):
    pass

class Business(models.Model):
    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='business')
    name = models.CharField(max_length=150)
    district = models.CharField(max_length=30, choices=DISTRICTS, default='Maseru')
    address = models.CharField(max_length=250, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    tin = models.CharField('Tax identification number', max_length=40, blank=True)
    vat_registered = models.BooleanField(default=False)
    default_tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    next_invoice = models.PositiveIntegerField(default=1)
    next_bill = models.PositiveIntegerField(default=1)
    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(default_tax_rate__gte=0, default_tax_rate__lte=100), name='valid_default_tax')]
    def __str__(self):
        return self.name

class Contact(models.Model):
    class Kind(models.TextChoices):
        CUSTOMER = 'customer', 'Customer'
        SUPPLIER = 'supplier', 'Supplier'
        BOTH = 'both', 'Customer & supplier'
    business = models.ForeignKey(Business, on_delete=models.CASCADE)
    name = models.CharField(max_length=150)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.CUSTOMER)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    address = models.CharField(max_length=250, blank=True)
    tin = models.CharField(max_length=40, blank=True)
    class Meta:
        ordering = ['name']
    def __str__(self):
        return self.name

class Account(models.Model):
    class Kind(models.TextChoices):
        ASSET = 'asset', 'Asset'
        LIABILITY = 'liability', 'Liability'
        EQUITY = 'equity', 'Equity'
        INCOME = 'income', 'Income'
        EXPENSE = 'expense', 'Expense'
    business = models.ForeignKey(Business, on_delete=models.CASCADE)
    code = models.CharField(max_length=10)
    name = models.CharField(max_length=100)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    is_cash = models.BooleanField(default=False)
    class Meta:
        ordering = ['code']
        constraints = [models.UniqueConstraint(fields=['business','code'], name='unique_account_code')]
    def __str__(self):
        return f'{self.code} · {self.name}'

class Document(models.Model):
    class Kind(models.TextChoices):
        INVOICE = 'invoice', 'Sales invoice'
        BILL = 'bill', 'Purchase bill'
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        POSTED = 'posted', 'Posted'
        VOID = 'void', 'Void'
    business = models.ForeignKey(Business, on_delete=models.PROTECT)
    contact = models.ForeignKey(Contact, on_delete=models.PROTECT)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    number = models.CharField(max_length=30)
    issue_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField()
    notes = models.TextField(max_length=2000, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    business_snapshot = models.JSONField(default=dict)
    contact_snapshot = models.JSONField(default=dict)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    paid = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-issue_date','-pk']
        constraints = [models.UniqueConstraint(fields=['business','number'], name='unique_document_number'), models.CheckConstraint(condition=models.Q(due_date__gte=models.F('issue_date')), name='due_after_issue'), models.CheckConstraint(condition=models.Q(paid__gte=0, paid__lte=models.F('total')), name='valid_paid_amount')]
        indexes = [models.Index(fields=['business','kind','status','due_date'])]
    @property
    def balance(self):
        return money(self.total - self.paid)
    @property
    def display_status(self):
        if self.status != 'posted':
            return self.get_status_display()
        if self.balance == 0:
            return 'Paid'
        if self.due_date < timezone.localdate():
            return 'Overdue'
        return 'Part paid' if self.paid else 'Unpaid'
    def __str__(self):
        return self.number

class DocumentLine(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='lines')
    description = models.CharField(max_length=250)
    quantity = models.DecimalField(max_digits=9, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    unit_price = models.DecimalField(max_digits=11, decimal_places=2, validators=[MinValueValidator(0)])
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(quantity__gt=0, unit_price__gte=0, tax_rate__gte=0, tax_rate__lte=100), name='valid_document_line')]
    @property
    def subtotal(self):
        return money(self.quantity * self.unit_price)
    @property
    def tax(self):
        return money(self.subtotal * self.tax_rate / 100)
    @property
    def total(self):
        return self.subtotal + self.tax

class JournalEntry(models.Model):
    business = models.ForeignKey(Business, on_delete=models.PROTECT)
    date = models.DateField()
    description = models.CharField(max_length=250)
    source_key = models.CharField(max_length=100)
    document = models.ForeignKey(Document, null=True, blank=True, on_delete=models.PROTECT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-date','-pk']
        constraints = [models.UniqueConstraint(fields=['business','source_key'], name='idempotent_journal_source')]

class JournalLine(models.Model):
    entry = models.ForeignKey(JournalEntry, on_delete=models.PROTECT, related_name='lines')
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    debit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    class Meta:
        constraints = [models.CheckConstraint(condition=(models.Q(debit__gt=0, credit=0) | models.Q(credit__gt=0, debit=0)), name='one_positive_journal_side')]

class Payment(models.Model):
    document = models.ForeignKey(Document, on_delete=models.PROTECT, related_name='payments')
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    date = models.DateField(default=timezone.localdate)
    reference = models.CharField(max_length=100, blank=True)
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    reversed = models.BooleanField(default=False)
    class Meta:
        ordering = ['-date','-pk']
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0), name='positive_payment')]

class Expense(models.Model):
    business = models.ForeignKey(Business, on_delete=models.PROTECT)
    description = models.CharField(max_length=250)
    supplier = models.ForeignKey(Contact, null=True, blank=True, on_delete=models.PROTECT)
    category = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='expenses')
    paid_from = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='outgoings')
    date = models.DateField(default=timezone.localdate)
    amount = models.DecimalField('Amount before tax (M)', max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    void = models.BooleanField(default=False)
    class Meta:
        ordering = ['-date','-pk']
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0, tax_rate__gte=0, tax_rate__lte=100), name='valid_expense_amount')]
    @property
    def tax(self):
        return money(self.amount * self.tax_rate / 100)
    @property
    def total(self):
        return self.amount + self.tax
