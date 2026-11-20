from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from .models import Product, StockImport
from .services import lock_business, stock_move


@transaction.atomic
def apply_import(owner, import_id, rows, confirmation):
    business = lock_business(owner)
    batch = StockImport.objects.get(pk=import_id, business=business)
    selected = [row for row in rows if row.get('include')]
    if not selected:
        raise ValidationError('Select at least one item to import.')
    payload = {'items': [
        {'name': row['name'], 'sku': row['sku'], 'quantity': str(row['quantity'].quantize(Decimal('0.01'))),
         'product': row['product'].pk if row.get('product') else None}
        for row in selected
    ]}
    if batch.applied:
        if batch.applied_payload.get('request') != payload:
            raise ValidationError('This screenshot batch was already imported with different details.')
        return batch
    if not confirmation.get('received') or not confirmation.get('reviewed'):
        raise ValidationError('Review the extracted items and confirm the goods have arrived.')
    created = []
    for row in selected:
        if row.get('product'):
            product = Product.objects.filter(pk=row['product'].pk, business=business, active=True, track_stock=True).first()
            if not product:
                raise ValidationError('The selected existing stock item is unavailable.')
        else:
            product = Product(business=business, name=row['name'], sku=row['sku'], price=0,
                              track_stock=True, tax_rate=business.default_tax_rate if business.vat_registered else 0)
            product.full_clean()
            product.save()
        quantity = row['quantity']
        if not isinstance(quantity, Decimal) or not quantity.is_finite() or quantity <= 0:
            raise ValidationError('Enter a positive quantity received.')
        stock_move(business=business, product=product, quantity=quantity,
                   reason=f'Checkout screenshot import {batch.pk}', user=owner)
        created.append({'product_id': product.pk, 'quantity': str(quantity)})
    batch.applied = True
    batch.applied_at = timezone.now()
    batch.applied_payload = {'request': payload, 'stock': created}
    batch.save(update_fields=['applied', 'applied_at', 'applied_payload'])
    return batch
