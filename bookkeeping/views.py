import csv
from datetime import timedelta
from functools import wraps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Sum, F
from django.http import HttpResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from . import forms, services
from .models import Business, Contact, Document, Expense, JournalEntry, JournalLine, Payment, ZERO, money
from .reporting import account_balances, financial_report


def business_required(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        business = Business.objects.filter(owner=request.user).first()
        if not business:
            return redirect('onboarding')
        request.business = business
        return view(request, *args, **kwargs)
    return wrapped


def paginate(request, queryset):
    return Paginator(queryset, 15).get_page(request.GET.get('page'))


def add_errors(form, error):
    for message in error.messages:
        form.add_error(None, message)


@business_required
def dashboard(request):
    business = request.business
    today = timezone.localdate()
    start = today.replace(day=1)
    report = financial_report(business, start, today)
    rows = report['balance_rows']
    cash_accounts = [r for r in rows if r['account'].is_cash]
    cash_total = sum((r['net'] for r in cash_accounts), ZERO)
    outstanding = Document.objects.filter(business=business, kind='invoice', status='posted', total__gt=F('paid'))
    receivable = sum((r['net'] for r in rows if r['account'].code == '1100'), ZERO)
    payable = -sum((r['net'] for r in rows if r['account'].code == '2000'), ZERO)
    # Six months of actual cash movement; transfers between cash accounts net to zero.
    month_dates = []
    cursor = start
    for _ in range(6):
        month_dates.append(cursor)
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    chart = []
    cash_lines = JournalLine.objects.filter(entry__business=business, account__is_cash=True, entry__date__gte=month_dates[-1], entry__date__lte=today)
    for month in reversed(month_dates):
        next_month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
        totals = cash_lines.filter(entry__date__gte=month, entry__date__lt=next_month).aggregate(incoming=Sum('debit', default=ZERO), outgoing=Sum('credit', default=ZERO))
        chart.append({'label':month.strftime('%b'), 'incoming':money(totals['incoming']), 'outgoing':money(totals['outgoing'])})
    maximum = max([x[k] for x in chart for k in ['incoming','outgoing']] + [1])
    for row in chart:
        row['in_height'] = round(row['incoming'] / maximum * 100)
        row['out_height'] = round(row['outgoing'] / maximum * 100)
    return render(request, 'bookkeeping/dashboard.html', {'active':'dashboard', 'today':today, 'report':report, 'cash_total':cash_total, 'cash_accounts':cash_accounts, 'receivable':receivable, 'payable':payable, 'overdue_count':outstanding.filter(due_date__lt=today).count(), 'recent':Document.objects.filter(business=business).select_related('contact')[:5], 'activity':JournalEntry.objects.filter(business=business)[:4], 'chart':chart, 'chart_in':sum((r['incoming'] for r in chart),ZERO), 'chart_out':sum((r['outgoing'] for r in chart),ZERO)})


@business_required
def documents(request, kind):
    if kind not in Document.Kind.values:
        raise Http404
    qs = Document.objects.filter(business=request.business, kind=kind).select_related('contact')
    query = request.GET.get('q', '').strip()
    if query:
        qs = qs.filter(Q(number__icontains=query) | Q(contact__name__icontains=query))
    status = request.GET.get('status', '')
    if status in ['draft','void']:
        qs = qs.filter(status=status)
    elif status == 'paid':
        qs = qs.filter(status='posted', paid=F('total'))
    elif status == 'unpaid':
        qs = qs.filter(status='posted', total__gt=F('paid'))
    elif status == 'overdue':
        qs = qs.filter(status='posted', total__gt=F('paid'), due_date__lt=timezone.localdate())
    return render(request, 'bookkeeping/documents.html', {'active':kind, 'kind':kind, 'title':'Sales invoices' if kind == 'invoice' else 'Purchase bills', 'page':paginate(request, qs), 'query':query, 'status':status})


@business_required
def document_create(request, kind):
    if kind not in Document.Kind.values:
        raise Http404
    form = forms.DocumentForm(request.POST or None, business=request.business, kind=kind, initial={'issue_date':timezone.localdate(), 'due_date':timezone.localdate()+timedelta(days=14)})
    formset = forms.LineFormSet(request.POST or None, prefix='lines', initial=[{'quantity':1, 'tax_rate':request.business.default_tax_rate}])
    if request.method == 'POST':
        valid_form, valid_lines = form.is_valid(), formset.is_valid()
        if valid_form and valid_lines:
            try:
                doc = services.create_document(business=request.business, user=request.user, data=form.cleaned_data, lines=formset.cleaned_data, kind=kind)
            except ValidationError as error:
                add_errors(form, error)
            else:
                messages.success(request, f'{doc.number} saved as a draft. Review it before posting to your books.')
                return redirect('document_detail', pk=doc.pk)
    return render(request, 'bookkeeping/document_form.html', {'active':kind, 'form':form, 'formset':formset, 'kind':kind, 'title':'New invoice' if kind == 'invoice' else 'New purchase bill'})


@business_required
def document_detail(request, pk):
    doc = get_object_or_404(Document.objects.select_related('contact','business').prefetch_related('lines','payments__account'), pk=pk, business=request.business)
    return render(request, 'bookkeeping/document_detail.html', {'active':doc.kind, 'doc':doc})


@business_required
@require_POST
def document_action(request, pk, action):
    doc = get_object_or_404(Document, pk=pk, business=request.business)
    try:
        if action == 'post':
            services.post_document(document=doc, user=request.user)
            messages.success(request, f'{doc.number} posted to your books.')
        elif action == 'void':
            services.void_document(document=doc, user=request.user)
            messages.success(request, f'{doc.number} voided. Any posted entries have been reversed.')
        else:
            raise Http404
    except ValidationError as error:
        messages.error(request, ' '.join(error.messages))
    return redirect('document_detail', pk=pk)


@business_required
def payment_create(request, pk):
    doc = get_object_or_404(Document, pk=pk, business=request.business)
    form = forms.PaymentForm(request.POST or None, business=request.business, initial={'amount':doc.balance})
    if request.method == 'POST' and form.is_valid():
        try:
            services.record_payment(document=doc, user=request.user, **form.cleaned_data)
        except ValidationError as error:
            add_errors(form, error)
        else:
            messages.success(request, 'Payment recorded and your books updated.')
            return redirect('document_detail', pk=pk)
    return render(request, 'bookkeeping/form.html', {'active':doc.kind, 'form':form, 'title':f'Record payment · {doc.number}', 'subtitle':f'Outstanding balance: M {doc.balance:,.2f}. This records a payment already received or made; it does not move money.', 'submit':'Record payment', 'cancel_url':reverse('document_detail', args=[pk])})


@business_required
def contacts(request):
    qs = Contact.objects.filter(business=request.business)
    query = request.GET.get('q','').strip()
    if query:
        qs = qs.filter(Q(name__icontains=query) | Q(email__icontains=query))
    return render(request, 'bookkeeping/contacts.html', {'active':'contacts', 'page':paginate(request, qs), 'query':query})


@business_required
def contact_edit(request, pk=None):
    contact = get_object_or_404(Contact, pk=pk, business=request.business) if pk else None
    form = forms.ContactForm(request.POST or None, instance=contact)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        obj.business = request.business
        obj.save()
        messages.success(request, 'Contact saved.')
        return redirect('contacts')
    return render(request, 'bookkeeping/form.html', {'active':'contacts', 'form':form, 'title':'Edit contact' if pk else 'New contact', 'subtitle':'Keep your customer and supplier details in one place.', 'submit':'Save contact', 'cancel_url':reverse('contacts')})


@business_required
def expenses(request):
    qs = Expense.objects.filter(business=request.business).select_related('supplier','category','paid_from')
    query = request.GET.get('q','').strip()
    if query:
        qs = qs.filter(description__icontains=query)
    return render(request, 'bookkeeping/expenses.html', {'active':'expenses', 'page':paginate(request, qs), 'query':query})


@business_required
def expense_create(request):
    form = forms.ExpenseForm(request.POST or None, business=request.business)
    if request.method == 'POST' and form.is_valid():
        try:
            services.record_expense(business=request.business, user=request.user, data=form.cleaned_data)
        except ValidationError as error:
            add_errors(form, error)
        else:
            messages.success(request, 'Expense recorded and posted to your books.')
            return redirect('expenses')
    return render(request, 'bookkeeping/form.html', {'active':'expenses', 'form':form, 'title':'Record an expense', 'subtitle':'For purchases you have already paid. Use a purchase bill for amounts you still owe.', 'submit':'Record expense', 'cancel_url':reverse('expenses')})


@business_required
@require_POST
def expense_void(request, pk):
    expense = get_object_or_404(Expense, pk=pk, business=request.business)
    try:
        services.void_expense(expense=expense, user=request.user)
        messages.success(request, 'Expense reversed. The original entry remains in your audit trail.')
    except ValidationError as error:
        messages.error(request, ' '.join(error.messages))
    return redirect('expenses')


@business_required
def ledger(request):
    entries = JournalEntry.objects.filter(business=request.business).select_related('created_by').prefetch_related('lines__account')
    query = request.GET.get('q','').strip()
    if query:
        entries = entries.filter(description__icontains=query)
    page = paginate(request, entries)
    reversed_keys = set(JournalEntry.objects.filter(business=request.business, source_key__in=[f'reverse-manual:{entry.pk}' for entry in page]).values_list('source_key', flat=True))
    for entry in page:
        entry.can_reverse = entry.source_key.startswith('manual:') and f'reverse-manual:{entry.pk}' not in reversed_keys
    return render(request, 'bookkeeping/ledger.html', {'active':'ledger', 'page':page, 'query':query})


@business_required
def transfer_create(request):
    form = forms.TransferForm(request.POST or None, business=request.business)
    if request.method == 'POST' and form.is_valid():
        try:
            services.record_transfer(business=request.business, user=request.user, **form.cleaned_data)
        except ValidationError as error:
            add_errors(form, error)
        else:
            messages.success(request, 'Journal entry posted.')
            return redirect('ledger')
    return render(request, 'bookkeeping/form.html', {'active':'ledger', 'form':form, 'title':'New journal entry', 'subtitle':'Record opening cash, owner funding, drawings, or account transfers. Both sides are posted together. Receivables, payables and VAT are managed through documents.', 'submit':'Post entry', 'cancel_url':reverse('ledger')})


@business_required
def reports(request):
    form = forms.ReportForm(request.GET or {'start':timezone.localdate().replace(month=1,day=1), 'end':timezone.localdate()})
    report = None
    if form.is_valid():
        report = financial_report(request.business, **form.cleaned_data)
        if request.GET.get('export') == 'csv':
            return report_csv(report, form.cleaned_data)
    return render(request, 'bookkeeping/reports.html', {'active':'reports', 'form':form, 'report':report})


def report_csv(report, dates):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="khumo-financial-report.csv"'
    writer = csv.writer(response)
    writer.writerow(['Khumo Books financial report (LSL)', dates['start'], dates['end']])
    writer.writerow(['Section','Code','Account','Debit','Credit','Balance'])
    for title, rows in [('Period activity',report['period_rows']),('Closing balances',report['balance_rows'])]:
        for row in rows:
            writer.writerow([title,row['account'].code,row['account'].name,row['debits'],row['credits'],row['balance']])
    writer.writerow(['Net profit','','','','',report['profit']])
    writer.writerow(['VAT net movement','','','','',report['vat_net']])
    return response


@business_required
def accounts(request):
    rows = account_balances(request.business, timezone.localdate())
    return render(request, 'bookkeeping/accounts.html', {'active':'accounts', 'rows':rows})


@business_required
def settings_view(request):
    form = forms.BusinessForm(request.POST or None, instance=request.business)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Business settings updated.')
        return redirect('settings')
    return render(request, 'bookkeeping/form.html', {'active':'settings', 'form':form, 'title':'Business settings', 'subtitle':'Business details, location and tax preferences. All books are kept in Lesotho loti (LSL).', 'submit':'Save changes'})


@business_required
@require_POST
def payment_reverse(request, pk):
    payment = get_object_or_404(Payment.objects.select_related('document'), pk=pk, document__business=request.business)
    try:
        services.reverse_payment(payment=payment, user=request.user)
        messages.success(request, 'Payment reversed. The original remains in your audit trail.')
    except ValidationError as error:
        messages.error(request, ' '.join(error.messages))
    return redirect('document_detail', pk=payment.document_id)


@business_required
def document_edit(request, pk):
    doc = get_object_or_404(Document, pk=pk, business=request.business)
    if doc.status != 'draft':
        messages.error(request, 'Only draft documents can be edited.')
        return redirect('document_detail', pk=doc.pk)
    form = forms.DocumentForm(request.POST or None, instance=doc, business=request.business, kind=doc.kind)
    initial = list(doc.lines.values('description','quantity','unit_price','tax_rate'))
    formset = forms.LineFormSet(request.POST or None, prefix='lines', initial=initial)
    if request.method == 'POST':
        valid_form, valid_lines = form.is_valid(), formset.is_valid()
        if valid_form and valid_lines:
            try:
                services.update_draft(document=doc,user=request.user,data=form.cleaned_data,lines=formset.cleaned_data)
            except ValidationError as error:
                add_errors(form,error)
            else:
                messages.success(request, f'{doc.number} draft updated.')
                return redirect('document_detail', pk=doc.pk)
    return render(request, 'bookkeeping/document_form.html', {'active':doc.kind,'form':form,'formset':formset,'kind':doc.kind,'title':f'Edit draft · {doc.number}'})

@business_required
@require_POST
def journal_reverse(request, pk):
    entry = get_object_or_404(JournalEntry, pk=pk, business=request.business)
    try:
        services.reverse_manual(entry=entry,user=request.user)
        messages.success(request, 'Journal entry reversed. The original remains in the ledger.')
    except ValidationError as error:
        messages.error(request, ' '.join(error.messages))
    return redirect('ledger')
