from decimal import Decimal
from django import forms
from django.forms import formset_factory
from .models import SectorProfile


def text(label, required=True):
    return forms.CharField(label=label, max_length=250, required=required)


def amount(label, required=True, minimum='0'):
    return forms.DecimalField(label=label, max_digits=12, decimal_places=2, min_value=Decimal(minimum), required=required)


def count(label, required=True):
    return forms.IntegerField(label=label, min_value=0, max_value=1000000, required=required)


class SectorForm(forms.Form):
    sector = forms.ChoiceField(choices=SectorProfile.Sector.choices, widget=forms.RadioSelect)


# Stable values are shared by web forms and the registration API.
PRICE_RANGES = [('below_100', 'Below M100'), ('100_499', 'M100–499'), ('500_999', 'M500–999'),
                ('1000_9999', 'M1,000–9,999'), ('10000_49999', 'M10,000–49,999'),
                ('50000_plus', 'M50,000 and above')]
SALARY_RANGES = [('below_500', 'Below M500'), ('500_999', 'M500–999'), ('1000_9999', 'M1,000–9,999'),
                 ('10000_19999', 'M10,000–19,999'), ('20000_plus', 'M20,000 and above')]


def choices(label, values):
    return forms.ChoiceField(label=label, choices=[('', 'Choose an option')] + values)


def price_range(label):
    return choices(label, PRICE_RANGES)


class IdentityForm(forms.Form):
    owner_full_name = text('Business owner’s full names')
    owner_id_number = forms.CharField(label='Owner’s national identity number', max_length=40)
    version = forms.IntegerField(widget=forms.HiddenInput, min_value=0, initial=0)


class HoursForm(forms.Form):
    working_days = forms.MultipleChoiceField(label='Working days', choices=[(x,x) for x in ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']], widget=forms.CheckboxSelectMultiple)
    opens_at = forms.TimeField(label='Work starts', widget=forms.TimeInput(attrs={'type':'time'}))
    closes_at = forms.TimeField(label='Work ends', widget=forms.TimeInput(attrs={'type':'time'}))
    overnight = forms.BooleanField(label='Work ends on the following day (including a 24-hour shift)', required=False)

    def clean(self):
        data = super().clean()
        if data.get('opens_at') is not None and data.get('closes_at') is not None:
            if data['closes_at'] <= data['opens_at'] and not data.get('overnight'):
                self.add_error('closes_at', 'Choose a later time or mark this as an overnight shift.')
            elif data['closes_at'] > data['opens_at'] and data.get('overnight'):
                self.add_error('overnight', 'An overnight shift must end at or before its start time.')
        return data


class CommonForm(forms.Form):
    location = text('Business location')
    turnover_range = price_range('Monthly turnover (M)')


class TransportForm(CommonForm, HoursForm):
    business_type = choices('Type of transport', [('taxi','Taxi'),('cab','Cab'),('catch_a_ride','Catch-a-ride')])
    vin = text('VIN / chassis number')
    license_plate = text('License plate number')


class ServicesForm(CommonForm, HoursForm):
    service_type = choices('Type of service', [(x,x.title()) for x in ['salon','mechanic','plumber','electrician','bricklayer']])
    service_price_range = price_range('Price per service (M)')


class OtherTypeForm(CommonForm):
    other_description = text('Describe Other (if selected)', required=False)

    def clean(self):
        data = super().clean()
        if 'other' in (data.get('service_type'), data.get('goods_type'), data.get('activity')) and not data.get('other_description'):
            self.add_error('other_description', 'Describe the other type.')
        return data


class EcommerceForm(OtherTypeForm):
    service_type = choices('Type of service', [('shein_runner','Shein runner'),('takealot','Takealot'),('other','Other')])
    purchase_price_range = price_range('Item purchase price (M)')
    selling_price_range = price_range('Item selling price (M)')
    shipping_price_range = price_range('Shipping / logistics price (M)')


class RetailForm(OtherTypeForm):
    goods_type = choices('Type of goods', [(x,x.title()) for x in ['clothing','fruits','food','all','other']])
    purchase_price_range = price_range('Item purchase price (M)')
    selling_price_range = price_range('Item selling price (M)')


class AgricultureForm(OtherTypeForm):
    activity = choices('Agricultural activity', [('farming','Farming'),('livestock','Livestock'),('other','Other')])
    selling_price_range = price_range('Selling price of output (M)')
    farmland_count = count('Number of farmland plots (0 if none)')
    farmland_size = forms.DecimalField(label='Total farmland size', max_digits=12, decimal_places=4, min_value=0)
    farmland_unit = choices('Farmland size unit', [('hectares','Hectares'),('acres','Acres'),('square_metres','Square metres')])
    farmland_unit.required = False

    def clean(self):
        data = super().clean()
        number, size = data.get('farmland_count'), data.get('farmland_size')
        if number is not None and size is not None and bool(number) != bool(size):
            self.add_error('farmland_size', 'Number of plots and total size must both be positive, or both zero.')
        if data.get('activity') == 'farming' and not number:
            self.add_error('farmland_count', 'Enter at least one plot for farming.')
        if number and not data.get('farmland_unit'):
            self.add_error('farmland_unit', 'Choose a unit for the farmland size.')
        return data


class RouteForm(forms.Form):
    origin = text('Route starts at')
    destination = text('Route ends at')
    price = amount('Price per route (M)')


class EmployeeForm(forms.Form):
    name = text('Employee’s full names')
    salary_range = choices('Monthly salary (M)', SALARY_RANGES)


class LivestockForm(forms.Form):
    animal_type = text('Type of livestock')
    number = forms.IntegerField(label='Number of animals', min_value=1, max_value=1000000)


EMPLOYEES = ('employees', 'Employees and monthly salaries', EmployeeForm, 0)
SECTORS = {
    'transport': (TransportForm, [('routes','Routes and prices',RouteForm,1), EMPLOYEES]),
    'services': (ServicesForm, [EMPLOYEES]),
    'ecommerce': (EcommerceForm, [EMPLOYEES]),
    'retail': (RetailForm, [EMPLOYEES]),
    'agriculture': (AgricultureForm, [('livestock','Livestock types and numbers',LivestockForm,0), EMPLOYEES]),
}


class ProfileForms:
    def __init__(self, sector, data=None, profile=None):
        self.sector = sector
        initial = profile.details if profile else {}
        self.identity = IdentityForm(data, prefix='identity', initial={'owner_full_name':initial.get('owner_full_name', ''), 'owner_id_number':profile.owner_id_number if profile else '', 'version':profile.version if profile else 0})
        form_class, groups = SECTORS[sector]
        self.main = form_class(data, prefix='details', initial=initial.get('details', {}))
        self.main.order_fields(sorted(self.main.fields, key=lambda key: key not in ('business_type', 'service_type', 'goods_type', 'activity')))
        category = next(key for key in self.main.fields if key in ('business_type', 'service_type', 'goods_type', 'activity'))
        self.category_fields = [self.main[category]]
        self.operation_fields = [field for field in self.main if field.name != category]
        self.groups = []
        for prefix, label, row_form, minimum in groups:
            factory = formset_factory(row_form, extra=1, min_num=minimum, validate_min=True, max_num=50, validate_max=True, absolute_max=60, can_delete=True)
            rows = initial.get(prefix, [])
            self.groups.append({'prefix':prefix, 'label':label, 'formset':factory(data, prefix=prefix, initial=rows), 'minimum':minimum})

    def is_valid(self):
        outcomes = [self.identity.is_valid(), self.main.is_valid()]
        outcomes += [group['formset'].is_valid() for group in self.groups]
        if not all(outcomes):
            return False
        rows = self.cleaned_details()
        details = rows['details']
        if details.get('activity') == 'livestock' and not rows['livestock']:
            self.main.add_error('activity', 'Add at least one livestock type and number.')
        return not self.main.errors

    def cleaned_details(self):
        result = {'schema_version':2, 'owner_full_name':self.identity.cleaned_data['owner_full_name'], 'details':self.main.cleaned_data}
        for group in self.groups:
            result[group['prefix']] = [{k:v for k,v in row.items() if k!='DELETE'} for row in group['formset'].cleaned_data if row and not row.get('DELETE')]
        return result
