import hashlib
import json
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from bookkeeping.models import Business, Account, ZERO, money
from bookkeeping.services import post_journal, check_tax, check_amount
from .models import SECTORS, Product, Sale, SaleLine, Refund, StockMovement


def lock_business(owner):
    business=Business.objects.select_for_update(of=('self',)).filter(owner=owner,sector_profile__sector__in=SECTORS).first()
    if not business:
        raise ValidationError('Point of sale is available to Transport, Services, E-Commerce, Retail and Agriculture businesses.')
    return business


def stock_move(*,business,product,quantity,reason,user,token=None,sale=None):
    balance=product.stock+quantity
    if balance<0 or balance>Decimal('9999999999.99'):
        raise ValidationError(f'Insufficient stock or invalid quantity for {product.name}.')
    movement=StockMovement(business=business,product=product,quantity=quantity,balance=balance,reason=reason,created_by=user,sale=sale)
    if token:
        movement.token=token
    movement.full_clean()
    movement.save()
    product.stock=balance
    product.save(update_fields=['stock'])
    return movement


@transaction.atomic
def save_product(owner,form):
    business=lock_business(owner)
    if not form.is_valid():
        raise ValidationError('Correct the highlighted fields.')
    item=form.save(commit=False)
    old=Product.objects.filter(pk=item.pk,business=business).first() if item.pk else None
    if item.pk and not old:
        raise ValidationError('This item belongs to another business.')
    if form.cleaned_data['version'] != (old.version if old else 0):
        raise ValidationError('This item changed in another tab. Reload before editing.')
    if old and old.track_stock!=item.track_stock and (old.movements.exists() or old.saleline_set.exists()):
        raise ValidationError('Stock tracking cannot change after stock movements or sales. Create a separate item instead.')
    check_tax(business,item.tax_rate)
    item.business=business
    item.stock=old.stock if old else ZERO
    item.version=(old.version if old else 0)+1
    item.full_clean()
    item.save()
    return item


@transaction.atomic
def adjust_stock(owner,product_id,data):
    business=lock_business(owner)
    product=Product.objects.get(pk=product_id,business=business)
    previous=StockMovement.objects.filter(business=business,token=data['token']).first()
    if previous:
        if previous.product_id==product.pk and previous.quantity==data['quantity'] and previous.reason==data['reason'] and not previous.sale_id:
            return previous
        raise ValidationError('This stock request was already used for another change.')
    if not product.track_stock:
        raise ValidationError('This item does not track stock.')
    return stock_move(business=business,product=product,quantity=data['quantity'],reason=data['reason'],user=owner,token=data['token'])


@transaction.atomic
def checkout(owner,data,rows,*,unit_prices=None):
    business=lock_business(owner)
    grouped={}
    for row in rows:
        if not row:
            continue
        pk=row['product'].pk
        if pk in grouped and grouped[pk]['version']!=row['version']:
            raise ValidationError('Remove and re-add the changed item.')
        item=grouped.setdefault(pk,{'quantity':ZERO,'version':row['version']})
        item['quantity']+=row['quantity']
        if item['quantity']<=0 or item['quantity']>Decimal('9999999.99'):
            raise ValidationError('Invalid item quantity.')
    if not 1<=len(grouped)<=50:
        raise ValidationError('Add between 1 and 50 items.')
    if unit_prices is not None:
        if set(unit_prices) != set(grouped):
            raise ValidationError('Provide a selling price for each selected item.')
        for price in unit_prices.values():
            if not isinstance(price, Decimal) or not price.is_finite() or price <= 0 or price > Decimal('999999999.99') or money(price) != price:
                raise ValidationError('Invalid selling price.')
    fingerprint_data={k:str(v.pk if k=='account' else v) for k,v in data.items() if k!='token'}
    if unit_prices is not None:
        fingerprint_data['selling_prices'] = [(pk, str(money(value))) for pk, value in sorted(unit_prices.items())]
    fingerprint_data['tendered']=str(money(data['tendered']))
    fingerprint_data['items']=[(pk,str(value['quantity']),value['version']) for pk,value in sorted(grouped.items())]
    fingerprint=hashlib.sha256(json.dumps(fingerprint_data,sort_keys=True).encode()).hexdigest()
    previous=Sale.objects.filter(business=business,token=data['token']).first()
    if previous:
        if previous.fingerprint!=fingerprint:
            raise ValidationError('This checkout request was already used. Start a new sale.')
        return previous
    products={p.pk:p for p in Product.objects.filter(business=business,pk__in=grouped,active=True)}
    if len(products)!=len(grouped):
        raise ValidationError('One or more items are unavailable or belong to another business.')
    account=Account.objects.filter(pk=data['account'].pk,business=business,is_cash=True,code__in=['1000','1010','1020','1030']).first()
    if not account or not data.get('received'):
        raise ValidationError('Choose a payment account and confirm receipt of payment.')
    prepared=[]
    for pk,row in grouped.items():
        product=products[pk]
        if product.version!=row['version']:
            raise ValidationError(f'{product.name} changed. Remove it from the basket and add it again to review the current price.')
        check_tax(business,product.tax_rate)
        if product.track_stock and product.stock<row['quantity']:
            raise ValidationError(f'Not enough stock for {product.name}. Available: {product.stock} {product.unit}.')
        price = product.price if unit_prices is None else unit_prices[pk]
        subtotal=money(price*row['quantity'])
        tax=money(subtotal*product.tax_rate/100)
        prepared.append(SaleLine(product=product,name=product.name,sku=product.sku,unit=product.unit,quantity=row['quantity'],unit_price=price,tax_rate=product.tax_rate,subtotal=subtotal,tax=tax,total=subtotal+tax,tracked_stock=product.track_stock))
    subtotal=sum((line.subtotal for line in prepared),ZERO)
    tax=sum((line.tax for line in prepared),ZERO)
    total=subtotal+tax
    check_amount(total)
    tendered=data['tendered']
    if tendered<total:
        raise ValidationError(f'Payment is short. The sale total is M {total:.2f}.')
    if account.code!='1000' and tendered!=total:
        raise ValidationError('Bank and mobile-money payments must equal the sale total. Change is only available for cash.')
    accounts={a.code:a for a in Account.objects.filter(business=business,code__in=['4000','2100'])}
    if not {'4000','2100'}<=accounts.keys():
        raise ValidationError('The sales and VAT accounts must exist before checkout.')
    journal=post_journal(business=business,user=owner,date=timezone.localdate(),description='Point-of-sale receipt',source_key=f'pos-sale:{data["token"]}',lines=[(account,total,0),(accounts['4000'],0,subtotal),(accounts['2100'],0,tax)])
    sale=Sale.objects.create(business=business,token=data['token'],fingerprint=fingerprint,customer_name=data.get('customer_name',''),payment_account=account,payment_reference=data.get('reference',''),subtotal=subtotal,tax=tax,total=total,tendered=tendered,change=tendered-total,business_snapshot={key:getattr(business,key) for key in ['name','address','district','phone','tin']},journal=journal,created_by=owner)
    for line in prepared:
        line.sale=sale
        line.full_clean()
        line.save()
        if line.tracked_stock:
            stock_move(business=business,product=line.product,quantity=-line.quantity,reason=f'Sale {sale.reference}',user=owner,sale=sale)
    return sale


@transaction.atomic
def refund_sale(owner,sale_id,data):
    business=lock_business(owner)
    sale=Sale.objects.get(pk=sale_id,business=business)
    previous=Refund.objects.filter(sale=sale).first()
    if previous:
        if previous.reason==data['reason'] and previous.restock==data['restock']:
            return previous
        raise ValidationError('This sale has already been refunded.')
    if not data.get('paid'):
        raise ValidationError('Confirm that the full payment has been returned to the customer.')
    journal=post_journal(business=business,user=owner,date=timezone.localdate(),description=f'Refund {sale.reference}',source_key=f'pos-refund:{sale.pk}',lines=[(line.account,line.credit,line.debit) for line in sale.journal.lines.select_related('account')])
    refund=Refund.objects.create(sale=sale,reason=data['reason'],restock=data['restock'],journal=journal,created_by=owner)
    if refund.restock:
        for line in sale.lines.filter(tracked_stock=True).select_related('product'):
            stock_move(business=business,product=line.product,quantity=line.quantity,reason=f'Refund {sale.reference}',user=owner,sale=sale)
    return refund
