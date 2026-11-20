from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods
from agents.bookkeeping import AgentUnavailable
from agents.stock_import import extract_stock
from .models import Product, StockImport
from .forms import CheckoutForm
from .import_forms import UploadForm, ImportRows, ConfirmImport, StockSaleRows
from .import_services import apply_import
from .views import pos_required, errors
from . import services


@sensitive_post_parameters()
@pos_required
@require_http_methods(['GET', 'POST'])
def upload(request):
    form = UploadForm(request.POST if request.method == 'POST' else None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        images, digest = form.cleaned_data['screenshots']
        previous = StockImport.objects.filter(business=request.pos_business, digest=digest).first()
        if previous:
            messages.info(request, 'These exact screenshots have already been uploaded. Review the existing import below.')
            return redirect('pos:import_review', pk=previous.pk)
        try:
            extracted = extract_stock(images)
        except AgentUnavailable:
            form.add_error(None, 'The screenshot reader is unavailable. Your stock has not changed. Please try again later.')
        else:
            if not extracted['items']:
                form.add_error(None, 'No readable stock items were found. Crop clear screenshots of the item names and quantities and try again.')
            else:
                batch, _ = StockImport.objects.get_or_create(
                    business=request.pos_business, digest=digest,
                    defaults={'extracted': extracted, 'created_by': request.user})
                return redirect('pos:import_review', pk=batch.pk)
    return render(request, 'pos/import_upload.html', {
        'active': 'pos', 'form': form, 'configured': bool(settings.GROQ_API_KEY),
        'page': Paginator(StockImport.objects.filter(business=request.pos_business), 15).get_page(request.GET.get('page')),
    })


@sensitive_post_parameters()
@pos_required
@require_http_methods(['GET', 'POST'])
def review(request, pk):
    batch = get_object_or_404(StockImport, pk=pk, business=request.pos_business)
    data = request.POST if request.method == 'POST' else None
    initial = [{'include': True, 'name': item['name'], 'sku': item.get('sku') or '',
                'quantity': item.get('quantity')} for item in batch.extracted['items']]
    rows = ImportRows(data, initial=initial, prefix='items', form_kwargs={'business': request.pos_business})
    form = ConfirmImport(data)
    if request.method == 'POST':
        rows_valid, form_valid = rows.is_valid(), form.is_valid()
        if rows_valid and form_valid:
            try:
                apply_import(request.user, batch.pk, rows.cleaned_data, form.cleaned_data)
            except ValidationError as error:
                errors(form, error)
            else:
                messages.success(request, 'Import recorded once. Review your stock below and enter selling prices when items are resold.')
                return redirect('pos:inventory')
    display = []
    for index, row in enumerate(rows):
        source = batch.extracted['items'][index] if index < len(batch.extracted['items']) else {}
        display.append({'form': row, 'source': source})
    return render(request, 'pos/import_review.html', {'active': 'pos', 'batch': batch, 'rows': rows, 'display': display, 'form': form})


@sensitive_post_parameters()
@pos_required
@require_http_methods(['GET', 'POST'])
def inventory(request):
    business = request.pos_business
    query = request.GET.get('q', '').strip()[:100]
    products = Product.objects.filter(business=business, track_stock=True)
    if query:
        products = products.filter(Q(name__icontains=query) | Q(sku__icontains=query))
    page = Paginator(products, 25).get_page(request.GET.get('page'))
    data = request.POST if request.method == 'POST' else None
    rows = StockSaleRows(data, prefix='items', initial=[
        {'product': p.pk, 'version': p.version, 'quantity': 1, 'selling_price': p.price if p.price > 0 else None}
        for p in page], form_kwargs={'business': business})
    form = CheckoutForm(data, business=business)
    if request.method == 'POST':
        rows_valid, form_valid = rows.is_valid(), form.is_valid()
        if rows_valid and form_valid:
            selected = [row for row in rows.cleaned_data if row.get('selected')]
            try:
                sale = services.checkout(request.user, form.cleaned_data, selected,
                                         unit_prices={row['product'].pk: row['selling_price'] for row in selected})
            except ValidationError as error:
                errors(form, error)
            else:
                return redirect('pos:receipt', pk=sale.pk)
    display = []
    # Render only owned product descriptions, even when a forged form is invalid.
    ids = []
    for row in rows:
        try:
            value = int(row['product'].value())
            if 0 < value < 2**63:
                ids.append(value)
        except (ValueError, TypeError):
            pass
    owned = {str(p.pk): p for p in Product.objects.filter(business=business, pk__in=ids)}
    for row in rows:
        display.append({'form': row, 'product': owned.get(str(row['product'].value()))})
    return render(request, 'pos/inventory.html', {
        'active': 'pos', 'page': page, 'query': query, 'rows': rows, 'display': display, 'form': form,
    })
