from datetime import timedelta
import uuid
import re
from django import forms
from django.utils import timezone
from .models import Calendar, Service, Staff, Appointment

DAYS = [(str(i), name) for i, name in enumerate(['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'])]


class CalendarForm(forms.ModelForm):
    weekdays = forms.TypedMultipleChoiceField(choices=DAYS, coerce=int, widget=forms.CheckboxSelectMultiple)

    class Meta:
        model = Calendar
        fields = ['enabled','welcome','weekdays','opens_at','closes_at']
        widgets = {'opens_at':forms.TimeInput(attrs={'type':'time','step':'900'}), 'closes_at':forms.TimeInput(attrs={'type':'time','step':'900'})}
        labels = {'opens_at':'Opening time', 'closes_at':'Closing time'}
        help_texts = {'enabled':'Publish your business in the service directory and let customers request appointments.'}


class ServiceForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = ['name','description','duration_minutes','price','active']
        widgets = {'duration_minutes':forms.NumberInput(attrs={'step':15}), 'description':forms.Textarea(attrs={'rows':2})}


class StaffForm(forms.ModelForm):
    class Meta:
        model = Staff
        fields = ['name','active']


class AvailabilityForm(forms.Form):
    service = forms.ModelChoiceField(queryset=Service.objects.none(), empty_label='Choose a service')
    staff = forms.ModelChoiceField(queryset=Staff.objects.none(), empty_label='Choose a staff member')
    date = forms.DateField(widget=forms.DateInput(attrs={'type':'date'}))

    def __init__(self, *args, business, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['service'].queryset = Service.objects.filter(business=business, active=True)
        self.fields['staff'].queryset = Staff.objects.filter(business=business, active=True)
        today = timezone.localdate()
        self.fields['date'].widget.attrs.update(min=today.isoformat(), max=(today+timedelta(days=90)).isoformat())
        self.fields['date'].initial = today

    def clean_date(self):
        date = self.cleaned_data['date']
        if not timezone.localdate() <= date <= timezone.localdate() + timedelta(days=90):
            raise forms.ValidationError('Choose a date within the next 90 days.')
        return date


class AppointmentForm(AvailabilityForm):
    time = forms.TimeField(widget=forms.TimeInput(attrs={'type':'time','step':900}))
    customer_name = forms.CharField(max_length=120, label='Your name')
    customer_phone = forms.RegexField(r'^\+?[0-9 ()-]{8,25}$', max_length=30, label='Phone number')
    customer_email = forms.EmailField(required=False, label='Email (optional)')
    notes = forms.CharField(max_length=500, required=False, widget=forms.Textarea(attrs={'rows':3}), label='Anything we should know?')
    request_key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)

    def clean_customer_phone(self):
        value = re.sub(r'[ ()-]', '', self.cleaned_data['customer_phone'])
        if not re.fullmatch(r'\+?[0-9]{8,15}', value):
            raise forms.ValidationError('Enter a valid phone number with 8–15 digits.')
        return value


class RescheduleForm(AvailabilityForm):
    version = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    time = forms.TimeField(widget=forms.TimeInput(attrs={'type':'time','step':900}))


class StatusForm(forms.Form):
    status = forms.ChoiceField(choices=Appointment.Status.choices)
