"""Validated, owner-scoped actions shared by the WhatsApp agent and review screen."""
import json
import uuid
from datetime import timedelta
from decimal import Decimal
from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from . import services
from .models import Account, Business, Contact, Document, RecordProposal, money
from .reporting import financial_report


class IntentForm(forms.Form):
    action = forms.ChoiceField(choices=[(x,x) for x in ['expense','sale','invoice','bill','payment']])
    description = forms.CharField(max_length=250, required=False)
    amount = forms.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'))
    currency = forms.ChoiceField(choices=[('LSL','LSL')])
    date = forms.DateField()
    due_date = forms.DateField(required=False)
    contact_name = forms.CharField(max_length=150, required=False)
    payment_account = forms.CharField(max_length=10, required=False)
    expense_account = forms.CharField(max_length=10, required=False)
    tax_rate = forms.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100)
    amount_basis = forms.ChoiceField(choices=[(x,x) for x in ['inclusive','exclusive','unspecified']])
    document_number = forms.CharField(max_length=30, required=False)


def context_for(business, day):
    return json.dumps({'message_date':day.isoformat(), 'currency':'LSL', 'payment_accounts':list(Account.objects.filter(business=business,is_cash=True).values('code','name')), 'expense_categories':list(Account.objects.filter(business=business,kind='expense').values('code','name'))})


def matching_contact(business, name, kind):
    matches = list(Contact.objects.filter(business=business,name__iexact=name)[:2])
    if len(matches)>1:
        raise ValidationError('More than one contact has that name. Give contacts distinct names in the app first.')
    if matches and matches[0].kind not in [kind,'both']:
        raise ValidationError('That contact has a different customer/supplier type. Update it in the app first.')
    return matches[0] if matches else None


def validate_intent(business, data):
    form = IntentForm(data)
    if not form.is_valid():
        missing = ', '.join(form.errors.keys()).replace('_',' ')
        raise ValidationError(f'Please resend the complete record with valid {missing}. Use Maloti (M), YYYY-MM-DD dates and HELP for examples.')
    clean = form.cleaned_data
    action = clean['action']
    services.check_date(clean['date'])
    services.check_tax(business, clean['tax_rate'])
    if action != 'payment' and not clean['description']:
        raise ValidationError('Please include a description and resend the complete record.')
    if clean['tax_rate'] and clean['amount_basis']=='unspecified':
        raise ValidationError('Please state whether the amount includes VAT and resend the complete record.')
    if action == 'payment' and clean['tax_rate']:
        raise ValidationError('A payment settles the existing document; do not add VAT to the payment.')
    net = clean['amount']
    if clean['amount_basis']=='inclusive':
        net = money(net / (1 + clean['tax_rate']/100))
    tax = money(net * clean['tax_rate']/100)
    total = net + tax
    if clean['amount_basis']=='inclusive' and total != clean['amount']:
        raise ValidationError('That inclusive amount cannot be represented exactly with line rounding. Provide the amount before VAT.')
    services.check_amount(net)
    clean.update(net=net,tax=tax,total=total)
    if action in ['expense','sale','payment']:
        try:
            clean['account'] = Account.objects.get(business=business,code=clean['payment_account'],is_cash=True)
        except Account.DoesNotExist:
            raise ValidationError('Choose cash, business bank, M-Pesa or EcoCash and resend the complete record.') from None
    if action=='expense':
        try:
            clean['category'] = Account.objects.get(business=business,code=clean['expense_account'],kind='expense')
        except Account.DoesNotExist:
            raise ValidationError('Choose an existing expense category and resend the complete record.') from None
    if action in ['invoice','bill']:
        if not clean['contact_name'] or not clean['due_date']:
            raise ValidationError('Include the customer/supplier name and due date, then resend the complete record.')
        if clean['due_date'] < clean['date']:
            raise ValidationError('The due date cannot be before the document date.')
    if action=='sale' and not clean['contact_name']:
        clean['contact_name']='Cash customer'
    if action!='payment' and clean['contact_name']:
        clean['contact_kind']='supplier' if action in ['bill','expense'] else 'customer'
        clean['contact']=matching_contact(business,clean['contact_name'],clean['contact_kind'])
    if action=='payment':
        doc=Document.objects.filter(business=business,number__iexact=clean['document_number'],status='posted').first()
        if not doc:
            raise ValidationError('No posted invoice or bill with that number exists in your business.')
        if clean['amount']>doc.balance or clean['date']<doc.issue_date:
            raise ValidationError('The payment exceeds the balance or predates the document. Check it in the app.')
        clean['document']=doc
    return clean


def summary_for(clean):
    labels={'expense':'Paid expense','sale':'Paid sale','invoice':'Sales invoice','bill':'Purchase bill','payment':'Document payment'}
    lines=[labels[clean['action']],f"Date: {clean['date'].isoformat()}"]
    if clean['description']:
        lines.append(clean['description'])
    if clean['action']=='payment':
        lines.extend([f"Document: {clean['document'].number}",f"Payment: M {clean['amount']:,.2f}"])
    else:
        lines.extend([f"Before VAT: M {clean['net']:,.2f}",f"VAT ({clean['tax_rate']}%): M {clean['tax']:,.2f}",f"Total: M {clean['total']:,.2f}"])
    if clean['contact_name']:
        lines.append('Contact: '+clean['contact_name']+(' (new)' if clean.get('contact') is None else ''))
    if clean.get('account'):
        lines.append('Payment account: '+clean['account'].name)
    if clean.get('category'):
        lines.append('Category: '+clean['category'].name)
    if clean['action'] in ['invoice','bill']:
        lines.append(f"Due: {clean['due_date'].isoformat()}")
    return '\n'.join(lines)


@transaction.atomic
def propose(*,business,owner,source_key,data):
    business=Business.objects.select_for_update().get(pk=business.pk,owner=owner,owner__is_active=True)
    existing=RecordProposal.objects.filter(source_key=source_key,business=business,owner=owner).first()
    if existing:
        return existing
    clean=validate_intent(business,data)
    # Preserve only the validated form fields; never store executable model instructions.
    payload={key:(value.isoformat() if hasattr(value,'isoformat') else str(value) if isinstance(value,Decimal) else value) for key,value in clean.items() if key in IntentForm.base_fields}
    return RecordProposal.objects.create(business=business,owner=owner,source_key=source_key,payload=payload,summary=summary_for(clean),expires_at=timezone.now()+timedelta(minutes=30))


@transaction.atomic
def resolve_proposal(*,business,owner,reference,confirm,channel='WhatsApp'):
    business=Business.objects.select_for_update().get(pk=business.pk,owner=owner,owner__is_active=True)
    proposal=RecordProposal.objects.select_for_update().filter(business=business,owner=owner,reference=reference.upper()).first()
    if not proposal:
        raise ValidationError('That proposal was not found in your business.')
    if proposal.status=='posted':
        return proposal.result
    if proposal.status!='pending':
        raise ValidationError('This proposal has already been cancelled.')
    if not confirm:
        proposal.status='cancelled'
        proposal.save(update_fields=['status'])
        return 'Proposal cancelled. No financial record was created.'
    if proposal.expires_at<=timezone.now():
        raise ValidationError('This proposal has expired. Please send the complete record again.')
    clean=validate_intent(business,proposal.payload)
    # Changes to account names or contact existence require a fresh reviewed proposal.
    if summary_for(clean)!=proposal.summary:
        raise ValidationError('The record details have changed. Please send the instruction again for a fresh preview.')
    contact=clean.get('contact')
    if clean['action']!='payment' and clean['contact_name'] and not contact:
        contact=Contact.objects.create(business=business,name=clean['contact_name'],kind=clean['contact_kind'])
    token=uuid.uuid5(uuid.NAMESPACE_URL,'khumo-proposal:'+proposal.reference)
    action=clean['action']
    if action=='expense':
        expense=services.record_expense(business=business,user=owner,data={'description':clean['description'],'supplier':contact,'date':clean['date'],'category':clean['category'],'paid_from':clean['account'],'amount':clean['net'],'tax_rate':clean['tax_rate'],'token':token})
        result=f'Expense #{expense.pk} recorded: M {expense.total:,.2f}.'
    elif action=='payment':
        doc=clean['document']
        services.record_payment(document=doc,user=owner,account=clean['account'],amount=clean['amount'],date=clean['date'],reference=channel+' '+proposal.reference,token=token)
        result=f'Payment recorded against {doc.number}: M {clean["amount"]:,.2f}.'
    else:
        kind='bill' if action=='bill' else 'invoice'
        doc=services.create_document(business=business,user=owner,kind=kind,data={'contact':contact,'issue_date':clean['date'],'due_date':clean['due_date'] if action in ['bill','invoice'] else clean['date'],'notes':'Confirmed via '+channel+' · '+proposal.reference},lines=[{'description':clean['description'],'quantity':Decimal('1'),'unit_price':clean['net'],'tax_rate':clean['tax_rate']}])
        services.post_document(document=doc,user=owner)
        if action=='sale':
            services.record_payment(document=doc,user=owner,account=clean['account'],amount=doc.total,date=clean['date'],reference=channel+' '+proposal.reference,token=token)
        result=f'{doc.number} recorded: M {doc.total:,.2f}'+(' (paid).' if action=='sale' else '.')
    proposal.status='posted'
    proposal.confirmed_at=timezone.now()
    proposal.result=result
    proposal.save(update_fields=['status','confirmed_at','result'])
    return result


def summary(business):
    today=timezone.localdate()
    report=financial_report(business,today.replace(day=1),today)
    return f"This month in Maloti (posted records):\nRevenue: M {report['income']:,.2f}\nExpenses: M {report['expenses']:,.2f}\nNet profit: M {report['profit']:,.2f}\nAs at {today.isoformat()}. Full reports are in the app."
