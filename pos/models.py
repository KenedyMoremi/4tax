import uuid
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.db.models.functions import Round

SECTORS = ['transport','services','ecommerce','retail','agriculture']


class Product(models.Model):
    business = models.ForeignKey('books.Business', on_delete=models.PROTECT)
    name = models.CharField(max_length=120)
    sku = models.CharField('SKU / barcode', max_length=64, blank=True)
    category = models.CharField(max_length=60, blank=True)
    unit = models.CharField(max_length=30, default='each')
    price = models.DecimalField('Unit price before VAT (M)', max_digits=11, decimal_places=2, validators=[MinValueValidator(0)])
    tax_rate = models.DecimalField('VAT rate (%)', max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0),MaxValueValidator(100)])
    track_stock = models.BooleanField('Track stock quantities', default=False)
    stock = models.DecimalField(max_digits=12, decimal_places=2, default=0, editable=False)
    active = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['name','pk']
        constraints = [models.CheckConstraint(condition=models.Q(stock__gte=0,price__gte=0,tax_rate__gte=0,tax_rate__lte=100),name='pos_product_valid_amounts'),
                       models.UniqueConstraint(fields=['business','sku'],condition=~models.Q(sku=''),name='pos_unique_sku')]

    def __str__(self):
        return self.name


class Sale(models.Model):
    business = models.ForeignKey('books.Business',on_delete=models.PROTECT)
    token = models.UUIDField(default=uuid.uuid4)
    fingerprint = models.CharField(max_length=64)
    customer_name = models.CharField(max_length=120,blank=True)
    payment_account = models.ForeignKey('books.Account',on_delete=models.PROTECT)
    payment_reference = models.CharField(max_length=100,blank=True)
    subtotal = models.DecimalField(max_digits=14,decimal_places=2)
    tax = models.DecimalField(max_digits=14,decimal_places=2)
    total = models.DecimalField(max_digits=14,decimal_places=2)
    tendered = models.DecimalField(max_digits=14,decimal_places=2)
    change = models.DecimalField(max_digits=14,decimal_places=2,default=0)
    business_snapshot = models.JSONField(default=dict)
    journal = models.OneToOneField('books.JournalEntry',on_delete=models.PROTECT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at','-pk']
        constraints = [models.UniqueConstraint(fields=['business','token'],name='pos_sale_retry_unique'),
                       models.CheckConstraint(condition=models.Q(total__gt=0,subtotal__gte=0,tax__gte=0,change__gte=0,tendered__gte=models.F('total')),name='pos_sale_valid_amounts'),
                       models.CheckConstraint(condition=models.Q(total=Round(models.F('subtotal')+models.F('tax'),2),change=Round(models.F('tendered')-models.F('total'),2)),name='pos_sale_totals_match')]
        indexes = [models.Index(fields=['business','created_at'])]

    @property
    def reference(self):
        return f'POS-{self.pk:06d}'


class SaleLine(models.Model):
    sale = models.ForeignKey(Sale,on_delete=models.PROTECT,related_name='lines')
    product = models.ForeignKey(Product,on_delete=models.PROTECT)
    name = models.CharField(max_length=120)
    sku = models.CharField(max_length=64,blank=True)
    unit = models.CharField(max_length=30)
    quantity = models.DecimalField(max_digits=9,decimal_places=2)
    unit_price = models.DecimalField(max_digits=11,decimal_places=2)
    tax_rate = models.DecimalField(max_digits=5,decimal_places=2)
    subtotal = models.DecimalField(max_digits=14,decimal_places=2)
    tax = models.DecimalField(max_digits=14,decimal_places=2)
    total = models.DecimalField(max_digits=14,decimal_places=2)
    tracked_stock = models.BooleanField(default=False)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(quantity__gt=0,unit_price__gte=0,tax_rate__gte=0,tax_rate__lte=100,subtotal__gte=0,tax__gte=0),name='pos_line_valid_amounts'),
                       models.CheckConstraint(condition=models.Q(total=Round(models.F('subtotal')+models.F('tax'),2)),name='pos_line_total_matches'),
                       models.UniqueConstraint(fields=['sale','product'],name='pos_one_line_per_product')]


class Refund(models.Model):
    sale = models.OneToOneField(Sale,on_delete=models.PROTECT,related_name='refund')
    reason = models.CharField(max_length=300)
    restock = models.BooleanField(default=True)
    journal = models.OneToOneField('books.JournalEntry',on_delete=models.PROTECT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)


class StockMovement(models.Model):
    business = models.ForeignKey('books.Business',on_delete=models.PROTECT)
    product = models.ForeignKey(Product,on_delete=models.PROTECT,related_name='movements')
    token = models.UUIDField(default=uuid.uuid4)
    quantity = models.DecimalField(max_digits=12,decimal_places=2)
    balance = models.DecimalField(max_digits=12,decimal_places=2)
    reason = models.CharField(max_length=300)
    sale = models.ForeignKey(Sale,on_delete=models.PROTECT,null=True,blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at','-pk']
        constraints = [models.UniqueConstraint(fields=['business','token'],name='pos_stock_retry_unique'),
                       models.CheckConstraint(condition=~models.Q(quantity=0) & models.Q(balance__gte=0),name='pos_valid_stock_movement')]


class StockImport(models.Model):
    """Reviewed extraction only; original screenshots are never stored."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey('books.Business', on_delete=models.PROTECT)
    digest = models.CharField(max_length=64)
    extracted = models.JSONField(default=dict)
    applied = models.BooleanField(default=False)
    applied_payload = models.JSONField(default=dict)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    applied_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['business', 'digest'], name='pos_import_image_unique'),
            models.CheckConstraint(condition=models.Q(applied=False, applied_at__isnull=True) | models.Q(applied=True, applied_at__isnull=False), name='pos_import_applied_timestamp'),
        ]
        ordering = ['-created_at']
