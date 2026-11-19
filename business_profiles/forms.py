from decimal import Decimal
from django import forms
from django.forms import formset_factory
from django.utils import timezone
from .models import SectorProfile


def text(label, required=True):
    return forms.CharField(label=label, max_length=250, required=required)


def amount(label, required=True, minimum='0'):
    return forms.DecimalField(label=label, max_digits=12, decimal_places=2, min_value=Decimal(minimum), required=required)


def count(label, required=True):
    return forms.IntegerField(label=label, min_value=0, max_value=1000000, required=required)


class SectorForm(forms.Form):
    sector = forms.ChoiceField(choices=SectorProfile.Sector.choices, widget=forms.RadioSelect)


class IdentityForm(forms.Form):
    owner_id_number = forms.CharField(label='Owner’s national ID number', max_length=40)
    version = forms.IntegerField(widget=forms.HiddenInput, min_value=0, initial=0)


class HoursForm(forms.Form):
    working_days = forms.MultipleChoiceField(choices=[(x,x) for x in ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']], widget=forms.CheckboxSelectMultiple)
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


class TransportForm(HoursForm):
    role = forms.ChoiceField(label='Your role', choices=[('owner','Owner'),('driver','Driver'),('both','Owner and driver')])


class EmployeeDetails(forms.Form):
    employee_count = count('Total number of employees (excluding the owner)')


class ServicesForm(HoursForm, EmployeeDetails):
    pass


class EcommerceForm(forms.Form):
    marketing_types = forms.MultipleChoiceField(label='Marketing channels', choices=[(x,x) for x in ['Social media','WhatsApp','Website','Word of mouth','Print','Other','None']], widget=forms.CheckboxSelectMultiple)
    marketing_details = text('Other marketing details', required=False)
    data_provider = text('Data provider and plan name')
    data_allowance = text('Data allowance (for example 20 GB or unlimited)')
    data_cost = amount('Data plan price (M)')
    data_period = forms.ChoiceField(label='Data plan billing period', choices=[('daily','Daily'),('weekly','Weekly'),('monthly','Monthly'),('once','Once-off')])

    def clean(self):
        data = super().clean()
        channels = data.get('marketing_types', [])
        if 'None' in channels and len(channels)>1:
            self.add_error('marketing_types', 'Select None on its own, or choose your marketing channels.')
        if 'Other' in channels and not data.get('marketing_details'):
            self.add_error('marketing_details', 'Describe the other marketing channel.')
        return data


class RetailForm(EmployeeDetails):
    location = text('Shop, stall or trading location')


class AgricultureForm(EmployeeDetails):
    activity = forms.ChoiceField(label='Agricultural activity', choices=[('crops','Crop farming'),('livestock','Livestock farming'),('breeding','Animal breeding'),('mixed','Mixed crops and livestock'),('other','Other')])
    activity_description = text('Describe your specific activity')
    location = text('Farm or operating location')


class RouteForm(forms.Form):
    origin = text('From')
    destination = text('To')
    price = amount('Price per passenger / trip (M)')
    price_basis = forms.ChoiceField(label='Route pricing basis', choices=[('passenger','Per passenger'),('trip','Per trip')])


class VehicleForm(forms.Form):
    registration_number = text('Vehicle registration number')
    vin = text('VIN / chassis number')
    make_model = text('Make and model')
    registered_owner = text('Registered owner')
    registration_details = text('Other registration details', required=False)
    condition = forms.ChoiceField(choices=[('good','Good'),('fair','Fair'),('needs_repair','Needs repair')])
    tank_litres = amount('Tank capacity (litres)', minimum='0.01')
    never_serviced = forms.BooleanField(label='Not serviced yet', required=False)
    last_service = forms.DateField(label='Last service date', required=False, widget=forms.DateInput(attrs={'type':'date'}))
    service_interval_months = forms.IntegerField(label='Service every (months)', min_value=1, max_value=120, required=False)
    service_interval_km = forms.IntegerField(label='Service every (kilometres)', min_value=1, max_value=1000000, required=False)

    def clean(self):
        data = super().clean()
        if bool(data.get('never_serviced')) == bool(data.get('last_service')):
            self.add_error('last_service', 'Enter the last service date, or select Not serviced yet.')
        if data.get('last_service') and data['last_service'] > timezone.localdate():
            self.add_error('last_service', 'The last service cannot be in the future.')
        if not data.get('service_interval_months') and not data.get('service_interval_km'):
            self.add_error('service_interval_months', 'Give the service interval in months, kilometres, or both.')
        return data


class ServiceForm(forms.Form):
    name = text('Service / consultation name')
    price_type = forms.ChoiceField(label='Pricing', choices=[('fixed','Fixed price'),('from','Starting price'),('quote','After consultation / quotation')])
    price = amount('Price (M)', required=False)
    description = text('What is included', required=False)

    def clean(self):
        data = super().clean()
        if data.get('price_type') != 'quote' and data.get('price') is None:
            self.add_error('price', 'Enter a fixed or starting price.')
        if data.get('price_type') == 'quote' and data.get('price') is not None:
            self.add_error('price', 'Leave the price empty when it requires a quotation.')
        return data


class EquipmentForm(forms.Form):
    name = text('Equipment / tool')
    quantity = forms.IntegerField(min_value=1, max_value=1000000)
    status = forms.ChoiceField(label='Stock status', choices=[('owned','Already owned'),('needed','Still needed')])


class EmployeeForm(forms.Form):
    role = text('Employee role / group')
    number = forms.IntegerField(label='Number of employees in this group', min_value=1, max_value=1000000)
    salary = amount('Salary per employee (M)')
    salary_period = forms.ChoiceField(label='Salary period', choices=[('monthly','Monthly'),('weekly','Weekly'),('daily','Daily'),('hourly','Hourly')])


class FarmEmployeeForm(EmployeeForm):
    salary = amount('Salary per employee (M, optional)', required=False)
    salary_period = forms.ChoiceField(label='Salary period', required=False, choices=[('','Not specified'),('monthly','Monthly'),('weekly','Weekly'),('daily','Daily'),('hourly','Hourly')])
    def clean(self):
        data = super().clean()
        if (data.get('salary') is not None) != bool(data.get('salary_period')):
            self.add_error('salary_period', 'Supply both a salary and its period, or leave both empty.')
        return data


class ItemForm(forms.Form):
    name = text('Item name')
    item_type = text('Type / category')
    unit = text('Unit (each, kg, pack, etc.)')
    purchase_price = amount('Purchase price per unit (M)')
    selling_price = amount('Selling price per unit (M)')


class StockForm(ItemForm):
    quantity = amount('Quantity in stock')


class ShippingForm(forms.Form):
    method = text('Shipping / logistics method')
    price = amount('Shipping price (M)')
    basis = text('Charged per (order, kg, trip, etc.)')


class GadgetForm(forms.Form):
    name = text('Gadget / device used')
    quantity = forms.IntegerField(min_value=1, max_value=1000000)


class InputForm(forms.Form):
    name = text('Input (seed, fertiliser, feed, etc.)')
    unit = text('Input unit')
    price = amount('Price per unit (M)')


class OutputForm(forms.Form):
    name = text('Output / product sold')
    unit = text('Output unit')
    selling_price = amount('Selling price per unit (M)')


class LandForm(forms.Form):
    description = text('Plot / farmland description')
    hectares = forms.DecimalField(label='Size (hectares)', max_digits=12, decimal_places=4, min_value=Decimal('0.0001'))


class LivestockForm(forms.Form):
    animal_type = text('Animal type / breed')
    description = text('Animal or group description')
    number = forms.IntegerField(label='Number of animals in this group', min_value=1, max_value=1000000)
    age_months = forms.IntegerField(label='Age (months; use separate groups for different ages)', min_value=0, max_value=2400)
    price = amount('Price per animal (M)')


# Collection definitions: prefix, heading, row form, minimum number of rows.
SECTORS = {
    'transport': (TransportForm, [('routes','Routes and prices',RouteForm,1),('vehicles','Vehicles and servicing',VehicleForm,1)]),
    'services': (ServicesForm, [('services','Services and prices',ServiceForm,1),('equipment','Equipment owned or needed',EquipmentForm,0),('employees','Employees and salaries',EmployeeForm,0)]),
    'ecommerce': (EcommerceForm, [('items','Items and prices',ItemForm,1),('shipping','Shipping and logistics',ShippingForm,1),('gadgets','Gadgets used for operations',GadgetForm,1)]),
    'retail': (RetailForm, [('stock','Stock and unit prices',StockForm,1),('employees','Employees and salaries',EmployeeForm,0)]),
    'agriculture': (AgricultureForm, [('inputs','Agricultural inputs',InputForm,1),('outputs','Outputs and selling prices',OutputForm,1),('land','Farmland (one row per plot)',LandForm,0),('livestock','Livestock and ages',LivestockForm,0),('employees','Employees',FarmEmployeeForm,0)]),
}


class ProfileForms:
    def __init__(self, sector, data=None, profile=None):
        self.sector = sector
        initial = profile.details if profile else {}
        self.identity = IdentityForm(data, prefix='identity', initial={'owner_id_number':profile.owner_id_number if profile else '', 'version':profile.version if profile else 0})
        form_class, groups = SECTORS[sector]
        self.main = form_class(data, prefix='details', initial=initial.get('details', {}))
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
        if 'employee_count' in details:
            total = sum(row['number'] for row in rows['employees'])
            if total != details['employee_count']:
                self.main.add_error('employee_count', 'The employee groups must add up to the total number of employees.')
        activity = details.get('activity')
        if activity in ['crops','mixed'] and not rows['land']:
            self.main.add_error('activity', 'Add at least one farmland plot for crop farming.')
        if activity in ['livestock','breeding','mixed'] and not rows['livestock']:
            self.main.add_error('activity', 'Add at least one livestock group for this activity.')
        return not self.main.errors

    def cleaned_details(self):
        result = {'details':self.main.cleaned_data}
        for group in self.groups:
            result[group['prefix']] = [{k:v for k,v in row.items() if k!='DELETE'} for row in group['formset'].cleaned_data if row and not row.get('DELETE')]
        return result
