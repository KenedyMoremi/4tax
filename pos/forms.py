import uuid
from decimal import Decimal
from django import forms
from django.forms import formset_factory
from bookkeeping.models import Account
from .models import Product


class ProductForm(forms.ModelForm):
    version = forms.IntegerField(min_value=0,widget=forms.HiddenInput,initial=0)

    class Meta:
        model = Product
        fields = ['name','sku','category','unit','price','tax_rate','track_stock','active']
        help_texts = {'track_stock':'Leave off for fares, digital items or other uncounted sales. Add opening quantities using Adjust stock.',
                      'tax_rate':'Use only the VAT rate configured for your registered business. Prices entered here exclude VAT.'}


class CheckoutForm(forms.Form):
    token = forms.UUIDField(widget=forms.HiddenInput,initial=uuid.uuid4)
    customer_name = forms.CharField(max_length=120,required=False,label='Customer name (optional)')
    account = forms.ModelChoiceField(queryset=Account.objects.none(),label='Payment received into')
    reference = forms.CharField(max_length=100,required=False,label='Payment reference (optional)')
    tendered = forms.DecimalField(max_digits=14,decimal_places=2,min_value=Decimal('0.01'),label='Amount received (M)')
    received = forms.BooleanField(label='I have received this payment')

    def __init__(self,*args,business,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['account'].queryset = Account.objects.filter(business=business,is_cash=True,code__in=['1000','1010','1020','1030'])


class CartLineForm(forms.Form):
    product = forms.ModelChoiceField(queryset=Product.objects.none(),widget=forms.HiddenInput)
    quantity = forms.DecimalField(max_digits=9,decimal_places=2,min_value=Decimal('0.01'),initial=1)
    version = forms.IntegerField(min_value=1,widget=forms.HiddenInput)

    def __init__(self,*args,business,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['product'].queryset=Product.objects.filter(business=business)


CartFormSet = formset_factory(CartLineForm,extra=0,min_num=1,validate_min=True,max_num=50,validate_max=True,absolute_max=60)


class StockForm(forms.Form):
    token = forms.UUIDField(widget=forms.HiddenInput,initial=uuid.uuid4)
    quantity = forms.DecimalField(max_digits=12,decimal_places=2,label='Quantity to add or remove',help_text='Use a negative quantity for losses or corrections.')
    reason = forms.CharField(max_length=300)

    def clean_quantity(self):
        value=self.cleaned_data['quantity']
        if not value:
            raise forms.ValidationError('Enter a non-zero quantity.')
        return value


class RefundForm(forms.Form):
    reason = forms.CharField(max_length=300,widget=forms.Textarea(attrs={'rows':3}))
    restock = forms.BooleanField(required=False,initial=True,label='Return tracked quantities to stock')
    paid = forms.BooleanField(label='I have returned the full amount to the customer through the original payment method')
