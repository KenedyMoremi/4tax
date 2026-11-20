from decimal import Decimal
from django import forms
from django.forms import formset_factory, BaseFormSet
from .models import Product
from .images import prepare_images


class MultipleFiles(forms.ClearableFileInput):
    allow_multiple_selected = True


class ScreenshotsField(forms.FileField):
    widget = MultipleFiles(attrs={'accept': 'image/png,image/jpeg,image/webp'})
    def clean(self, data, initial=None):
        files = data if isinstance(data, (list, tuple)) else [data]
        files = [super(ScreenshotsField, self).clean(item, initial) for item in files]
        return prepare_images(files)


class UploadForm(forms.Form):
    screenshots = ScreenshotsField(help_text='1–3 PNG, JPEG or WebP images; 3 MB combined. Crop to the items and quantities.')
    consent = forms.BooleanField(label='Send these screenshots to Groq for item extraction',
        help_text='Remove addresses, contact and payment details first. Images are processed privately and are not saved by 4Tax.')


class ImportRow(forms.Form):
    include = forms.BooleanField(required=False, initial=True, label='Add to stock')
    name = forms.CharField(max_length=120, label='Item and variant')
    sku = forms.CharField(max_length=64, required=False, label='SKU (optional)')
    quantity = forms.DecimalField(max_digits=9, decimal_places=2, min_value=Decimal('0.01'), label='Quantity received')
    product = forms.ModelChoiceField(queryset=Product.objects.none(), required=False,
                                    empty_label='Create a new stock item', label='Match existing item')
    def __init__(self, *args, business, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product'].queryset = Product.objects.filter(business=business, track_stock=True, active=True)
        if self.is_bound and not self.data.get(self.add_prefix('include')):
            self.fields['name'].required = False
            self.fields['quantity'].required = False


ImportRows = formset_factory(ImportRow, extra=0, min_num=1, validate_min=True, max_num=30, validate_max=True, absolute_max=30)


class ConfirmImport(forms.Form):
    received = forms.BooleanField(label='These goods have arrived and these quantities are available to resell')
    reviewed = forms.BooleanField(label='I checked the items, variants, quantities and any duplicate rows')


class StockSaleRow(forms.Form):
    selected = forms.BooleanField(required=False)
    product = forms.ModelChoiceField(queryset=Product.objects.none(), widget=forms.HiddenInput)
    version = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    quantity = forms.DecimalField(max_digits=9, decimal_places=2, min_value=Decimal('0.01'), required=False, initial=1)
    selling_price = forms.DecimalField(max_digits=11, decimal_places=2, min_value=Decimal('0.01'), required=False, label='Unit selling price before VAT (M)')
    def __init__(self, *args, business, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product'].queryset = Product.objects.filter(business=business, track_stock=True)
    def clean(self):
        data = super().clean()
        if data.get('selected'):
            for key in ['quantity', 'selling_price']:
                if data.get(key) is None:
                    self.add_error(key, 'Enter a value for this selected item.')
        return data


class StockSaleForms(BaseFormSet):
    def clean(self):
        if any(self.errors):
            return
        selected = [row.cleaned_data for row in self.forms if row.cleaned_data.get('selected')]
        if not selected:
            raise forms.ValidationError('Tick at least one item to record a sale.')
        ids = [row['product'].pk for row in selected]
        if len(ids) != len(set(ids)):
            raise forms.ValidationError('Each stock item must appear only once.')


StockSaleRows = formset_factory(StockSaleRow, formset=StockSaleForms, extra=0, max_num=25, validate_max=True, absolute_max=25)
