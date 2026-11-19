from functools import wraps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods
from bookkeeping.models import Business, ZERO
from .models import SECTORS, Product, Sale, Refund, StockMovement
from .forms import ProductForm, CheckoutForm, CartFormSet, StockForm, RefundForm
from . import services


def pos_required(view):
    @login_required
    @wraps(view)
    def wrapped(request,*args,**kwargs):
        business=Business.objects.filter(owner=request.user).first()
        if not business:
            return redirect('onboarding')
        if not Business.objects.filter(pk=business.pk,sector_profile__sector__in=SECTORS).exists():
            return render(request,'pos/ineligible.html',{'active':'pos'},status=403)
        request.pos_business=business
        return view(request,*args,**kwargs)
    return never_cache(wrapped)


def errors(form,error):
    for message in error.messages:
        form.add_error(None,message)


def product_data(product):
    return {'id':product.pk,'name':product.name,'price':str(product.price),'tax':str(product.tax_rate),
            'unit':product.unit,'stock':str(product.stock) if product.track_stock else None,'version':product.version}


@sensitive_post_parameters()
@pos_required
@require_http_methods(['GET','POST'])
def terminal(request):
    business=request.pos_business
    data=request.POST if request.method=='POST' else None
    form=CheckoutForm(data,business=business)
    rows=CartFormSet(data,prefix='items',form_kwargs={'business':business})
    if request.method=='POST':
        valid_form=form.is_valid()
        valid_rows=rows.is_valid()
        if valid_form and valid_rows:
            try:
                sale=services.checkout(request.user,form.cleaned_data,rows.cleaned_data)
            except ValidationError as error:
                errors(form,error)
            else:
                return redirect('pos:receipt',pk=sale.pk)
    query=request.GET.get('q','').strip()[:100]
    products=Product.objects.filter(business=business,active=True)
    if query:
        products=products.filter(Q(name__icontains=query)|Q(sku__icontains=query)|Q(category__icontains=query))
    page=Paginator(products,24).get_page(request.GET.get('page'))
    initial=[]
    if request.method=='POST':
        for row in rows:
            pk=row['product'].value()
            try:
                product=Product.objects.filter(business=business,pk=int(pk)).first() if 0<int(pk)<2**63 else None
            except (TypeError,ValueError,OverflowError):
                product=None
            if product:
                initial.append(product_data(product)|{'quantity':str(row['quantity'].value() or ''),'version':row['version'].value()})
    return render(request,'pos/terminal.html',{'active':'pos','form':form,'rows':rows,'page':page,'query':query,
        'products_json':[product_data(p) for p in page], 'initial_cart':initial,'posted':request.method=='POST',
        'business_id':business.pk,'sector':business.sector_profile.get_sector_display()})


@pos_required
@require_http_methods(['GET','POST'])
def products(request,pk=None):
    business=request.pos_business
    product=get_object_or_404(Product,pk=pk,business=business) if pk else Product(business=business,tax_rate=business.default_tax_rate if business.vat_registered else 0)
    form=ProductForm(request.POST if request.method=='POST' else None,instance=product,initial={'version':product.version if pk else 0})
    if request.method=='POST' and form.is_valid():
        try:
            services.save_product(request.user,form)
        except ValidationError as error:
            errors(form,error)
        else:
            messages.success(request,'Catalogue item saved.')
            return redirect('pos:products')
    query=request.GET.get('q','').strip()[:100]
    items=Product.objects.filter(business=business)
    if query:
        items=items.filter(Q(name__icontains=query)|Q(sku__icontains=query))
    return render(request,'pos/products.html',{'active':'pos','form':form,'editing':bool(pk),'query':query,
        'page':Paginator(items,20).get_page(request.GET.get('page'))})


@pos_required
@require_http_methods(['GET','POST'])
def stock(request,pk):
    product=get_object_or_404(Product,pk=pk,business=request.pos_business,track_stock=True)
    form=StockForm(request.POST if request.method=='POST' else None)
    if request.method=='POST' and form.is_valid():
        try:
            services.adjust_stock(request.user,product.pk,form.cleaned_data)
        except ValidationError as error:
            errors(form,error)
        else:
            messages.success(request,'Stock quantity updated.')
            return redirect('pos:stock',pk=pk)
    return render(request,'pos/stock.html',{'active':'pos','product':product,'form':form,
        'page':Paginator(product.movements.all(),20).get_page(request.GET.get('page'))})


@pos_required
@require_http_methods(['GET'])
def sales(request):
    business=request.pos_business
    qs=Sale.objects.filter(business=business).select_related('payment_account','refund')
    query=request.GET.get('q','').strip()[:100]
    if query:
        if query.upper().startswith('POS-') and query[4:].isdigit():
            qs=qs.filter(pk=int(query[4:])) if int(query[4:])<2**63 else qs.none()
        else:
            qs=qs.filter(Q(customer_name__icontains=query)|Q(payment_reference__icontains=query))
    today=timezone.localdate()
    gross=Sale.objects.filter(business=business,created_at__date=today).aggregate(value=Sum('total',default=ZERO))['value']
    refunds=Refund.objects.filter(sale__business=business,created_at__date=today).aggregate(value=Sum('sale__total',default=ZERO))['value']
    return render(request,'pos/sales.html',{'active':'pos','page':Paginator(qs,20).get_page(request.GET.get('page')),
        'query':query,'gross':gross,'refunds':refunds,'net':gross-refunds})


@pos_required
@require_http_methods(['GET'])
def receipt(request,pk):
    sale=get_object_or_404(Sale.objects.select_related('payment_account','refund').prefetch_related('lines'),pk=pk,business=request.pos_business)
    return render(request,'pos/receipt.html',{'active':'pos','sale':sale,'business_id':request.pos_business.pk})


@sensitive_post_parameters()
@pos_required
@require_http_methods(['GET','POST'])
def refund(request,pk):
    sale=get_object_or_404(Sale,pk=pk,business=request.pos_business)
    form=RefundForm(request.POST if request.method=='POST' else None)
    if request.method=='POST' and form.is_valid():
        try:
            services.refund_sale(request.user,sale.pk,form.cleaned_data)
        except ValidationError as error:
            errors(form,error)
        else:
            messages.success(request,'Full refund recorded. The original receipt is retained.')
            return redirect('pos:receipt',pk=pk)
    return render(request,'pos/refund.html',{'active':'pos','sale':sale,'form':form})
