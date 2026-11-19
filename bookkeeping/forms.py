import uuid
from decimal import Decimal
from django import forms
from django.forms import formset_factory
from django.utils import timezone
from .models import Business, Contact, Account, Document, Expense

class BusinessForm(forms.ModelForm):
    class Meta:
        model = Business
        fields = ['name','district','address','email','phone','tin','vat_registered','default_tax_rate']
        labels = {'name':'Business name', 'default_tax_rate':'Default VAT rate (%)'}
        help_texts = {'default_tax_rate':'Confirm the applicable rate for your business with RSL. This app does not file tax returns.', 'vat_registered':'Only enable this if your business is registered for VAT.'}
    def clean(self):
        data = super().clean()
        if data.get('default_tax_rate') and not data.get('vat_registered'):
            raise forms.ValidationError('A VAT rate requires VAT registration.')
        return data

class ContactForm(forms.ModelForm):
    class Meta:
        model = Contact
        fields = ['name','kind','email','phone','address','tin']

class DocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ['contact','issue_date','due_date','notes']
        widgets = {'issue_date': forms.DateInput(attrs={'type':'date'}), 'due_date': forms.DateInput(attrs={'type':'date'}), 'notes': forms.Textarea(attrs={'rows':3})}
    def __init__(self, *args, business, kind, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['contact'].queryset = Contact.objects.filter(business=business, kind__in=['customer','both'] if kind == 'invoice' else ['supplier','both'])
        self.fields['contact'].label = 'Customer' if kind == 'invoice' else 'Supplier'
    def clean(self):
        data = super().clean()
        if data.get('issue_date') and data.get('due_date') and data['due_date'] < data['issue_date']:
            raise forms.ValidationError('Due date must be on or after issue date.')
        return data

class LineForm(forms.Form):
    description = forms.CharField(max_length=250)
    quantity = forms.DecimalField(max_digits=9, decimal_places=2, min_value=Decimal('0.01'), initial=1)
    unit_price = forms.DecimalField(max_digits=11, decimal_places=2, min_value=0, label='Unit price (M)')
    tax_rate = forms.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100, initial=0, label='VAT %')
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs['aria-label'] = field.label or name.replace('_', ' ').title()

LineFormSet = formset_factory(LineForm, extra=1, min_num=1, validate_min=True, max_num=50, validate_max=True, can_delete=True)

class PaymentForm(forms.Form):
    amount = forms.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal('0.01'), label='Amount (M)')
    date = forms.DateField(initial=timezone.localdate, widget=forms.DateInput(attrs={'type':'date'}))
    account = forms.ModelChoiceField(queryset=Account.objects.none(), label='Payment account')
    reference = forms.CharField(max_length=100, required=False)
    token = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    def __init__(self, *args, business, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['account'].queryset = Account.objects.filter(business=business, is_cash=True)

class ExpenseForm(forms.ModelForm):
    token = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    class Meta:
        model = Expense
        fields = ['description','supplier','date','category','paid_from','amount','tax_rate']
        widgets = {'date':forms.DateInput(attrs={'type':'date'})}
        labels = {'tax_rate':'VAT (%)'}
    def __init__(self, *args, business, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['supplier'].queryset = Contact.objects.filter(business=business, kind__in=['supplier','both'])
        self.fields['category'].queryset = Account.objects.filter(business=business, kind='expense')
        self.fields['paid_from'].queryset = Account.objects.filter(business=business, is_cash=True)
        self.fields['tax_rate'].initial = business.default_tax_rate

class TransferForm(forms.Form):
    date = forms.DateField(initial=timezone.localdate, widget=forms.DateInput(attrs={'type':'date'}))
    description = forms.CharField(max_length=250)
    debit_account = forms.ModelChoiceField(queryset=Account.objects.none(), help_text='For owner funding, debit your bank or cash account.')
    credit_account = forms.ModelChoiceField(queryset=Account.objects.none(), help_text='For owner funding, credit Owner’s capital.')
    amount = forms.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal('0.01'), label='Amount (M)')
    token = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    def __init__(self, *args, business, **kwargs):
        super().__init__(*args, **kwargs)
        accounts = Account.objects.filter(business=business).exclude(code__in=['1100','1200','2000','2100'])
        self.fields['debit_account'].queryset = accounts
        self.fields['credit_account'].queryset = accounts

class ReportForm(forms.Form):
    start = forms.DateField(required=False, widget=forms.DateInput(attrs={'type':'date'}), label='From')
    end = forms.DateField(required=False, widget=forms.DateInput(attrs={'type':'date'}), label='To')
    def clean(self):
        data = super().clean()
        data['end'] = data.get('end') or timezone.localdate()
        data['start'] = data.get('start') or data['end'].replace(month=1, day=1)
        if data['start'] > data['end']:
            raise forms.ValidationError('Start date must be before the end date.')
        return data
