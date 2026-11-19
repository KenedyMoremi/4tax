from datetime import timedelta
from functools import wraps
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Exists, OuterRef, Q, Subquery
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods, require_POST

from bookkeeping.models import Business
from . import services
from .forms import CalendarForm, ServiceForm, StaffForm, AvailabilityForm, AppointmentForm, RescheduleForm, StatusForm
from .models import Calendar, Service, Staff, Appointment


def owner_required(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        business = Business.objects.filter(owner=request.user).first()
        if not business:
            return redirect('onboarding')
        if not Business.objects.filter(pk=business.pk, sector_profile__sector='services').exists():
            return render(request, 'bookings/ineligible.html', {'active':'bookings'}, status=403)
        request.booking_business = business
        return view(request, *args, **kwargs)
    return never_cache(wrapped)


def errors(form, error):
    for message in error.messages:
        form.add_error(None, message)


@owner_required
@require_http_methods(['GET'])
def dashboard(request):
    business = request.booking_business
    date_field = forms.DateField(required=False)
    try:
        date = date_field.clean(request.GET.get('date')) or timezone.localdate()
    except ValidationError:
        date = timezone.localdate()
    if date.year < 1900 or date.year > 2100:
        date = timezone.localdate()
    qs = Appointment.objects.filter(business=business, starts_at__date=date).select_related('staff')
    requests_view = request.GET.get('view') == 'requests'
    if requests_view:
        qs = Appointment.objects.filter(business=business,status='pending',ends_at__gt=timezone.now()).select_related('staff')
    status = request.GET.get('status','')
    if status in Appointment.Status.values:
        qs = qs.filter(status=status)
    all_rows = Appointment.objects.filter(business=business)
    calendar = Calendar.objects.filter(business=business).first()
    return render(request, 'bookings/dashboard.html', {'active':'bookings', 'calendar':calendar,
        'page':Paginator(qs,20).get_page(request.GET.get('page')), 'date':date, 'previous_date':date-timedelta(days=1),
        'requests_view':requests_view, 'next_date':date+timedelta(days=1), 'status':status, 'statuses':Appointment.Status.choices,
        'today_count':all_rows.filter(starts_at__date=timezone.localdate()).exclude(status='cancelled').count(),
        'pending_count':all_rows.filter(status='pending', ends_at__gt=timezone.now()).count(),
        'public_url':request.build_absolute_uri(reverse('bookings:public',args=[calendar.public_id])) if calendar else '',
        'services_count':Service.objects.filter(business=business,active=True).count(),
        'staff_count':Staff.objects.filter(business=business,active=True).count()})


@owner_required
@require_http_methods(['GET','POST'])
def settings(request):
    business = request.booking_business
    calendar = Calendar.objects.filter(business=business).first() or Calendar(business=business)
    form = CalendarForm(request.POST if request.method=='POST' else None, instance=calendar)
    if request.method=='POST' and form.is_valid():
        try:
            services.save_calendar(request.user, form)
        except ValidationError as error:
            errors(form,error)
        else:
            messages.success(request,'Booking hours and online availability saved.')
            return redirect('bookings:dashboard')
    return render(request,'bookings/form.html',{'active':'bookings','form':form,'title':'Booking hours & availability',
        'description':'New calendars start Monday–Friday, 08:00–17:00. All times are in Lesotho time. Add a service and staff member before enabling your public page.'})


@owner_required
@require_http_methods(['GET','POST'])
def catalog(request, kind, pk=None):
    if kind not in ('services','staff'):
        raise Http404
    model, form_type = (Service,ServiceForm) if kind=='services' else (Staff,StaffForm)
    item = get_object_or_404(model, pk=pk, business=request.booking_business) if pk else model(business=request.booking_business)
    form = form_type(request.POST if request.method=='POST' else None, instance=item)
    if request.method=='POST' and form.is_valid():
        try:
            services.save_catalog(request.user,form)
        except ValidationError as error:
            errors(form,error)
        else:
            messages.success(request,'Service saved.' if kind=='services' else 'Staff member saved.')
            return redirect('bookings:catalog',kind=kind)
    return render(request,'bookings/catalog.html',{'active':'bookings','form':form,'kind':kind,'editing':bool(pk),
        'page':Paginator(model.objects.filter(business=request.booking_business),20).get_page(request.GET.get('page'))})


def booking_form(request, business, calendar, *, public):
    data = request.POST if request.method=='POST' else None
    selection = AvailabilityForm(request.GET or None,business=business)
    form = AppointmentForm(data,business=business,initial=request.GET.dict())
    if not public:
        form.fields['customer_name'].label = 'Customer name'
        form.fields['notes'].label = 'Appointment notes'
    slots = []
    if request.method=='POST':
        if form.is_valid():
            try:
                appointment = services.create_appointment(business.pk,form.cleaned_data,public=public)
            except ValidationError as error:
                errors(form,error)
            else:
                return redirect('bookings:receipt' if public else 'bookings:detail', **({'token':appointment.access_token} if public else {'pk':appointment.pk}))
        selection = AvailabilityForm(request.POST,business=business)
    if selection.is_bound and selection.is_valid() and calendar:
        slots = services.available_slots(calendar,selection.cleaned_data['service'],selection.cleaned_data['staff'],selection.cleaned_data['date'])
    for name, field in selection.fields.items():
        field.widget.attrs['id'] = 'selection-' + name
    context = {'active':'bookings','business':business,'calendar':calendar,'selection':selection,'form':form,
               'location':business.address or business.sector_profile.details.get('details',{}).get('location') or business.district,
               'working_days':', '.join(['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][day] for day in calendar.weekdays) if calendar else '',
               'slots':slots,'selection_ready':selection.is_bound and not selection.errors,
               'offers':Service.objects.filter(business=business,active=True)[:50], 'public':public}
    return render(request,'bookings/public.html' if public else 'bookings/new.html',context)


@sensitive_post_parameters()
@owner_required
@require_http_methods(['GET','POST'])
def new(request):
    calendar = Calendar.objects.filter(business=request.booking_business).first()
    if not calendar:
        messages.info(request,'Save your booking hours before adding appointments.')
        return redirect('bookings:settings')
    return booking_form(request,request.booking_business,calendar,public=False)


@sensitive_post_parameters()
@never_cache
@require_http_methods(['GET','POST'])
def public(request, public_id):
    calendar = get_object_or_404(Calendar.objects.select_related('business'),public_id=public_id,enabled=True,business__sector_profile__sector='services')
    return booking_form(request,calendar.business,calendar,public=True)


@owner_required
@require_http_methods(['GET'])
def detail(request, pk):
    appointment = get_object_or_404(Appointment.objects.select_related('staff'),pk=pk,business=request.booking_business)
    return render(request,'bookings/detail.html',{'active':'bookings','appointment':appointment,
        'can_finish':appointment.starts_at <= timezone.now(), 'can_change':appointment.status in services.ACTIVE,'can_reschedule':appointment.status in services.ACTIVE and appointment.starts_at > timezone.now()})


@owner_required
@require_POST
def status(request, pk):
    appointment = get_object_or_404(Appointment,pk=pk,business=request.booking_business)
    form = StatusForm(request.POST)
    if form.is_valid():
        try:
            services.change_status(request.booking_business.pk,appointment.pk,form.cleaned_data['status'])
        except ValidationError as error:
            messages.error(request,' '.join(error.messages))
        else:
            messages.success(request,'Appointment status updated.')
    else:
        messages.error(request,'Choose a valid appointment status.')
    return redirect('bookings:detail',pk=pk)


@sensitive_post_parameters()
@owner_required
@require_http_methods(['GET','POST'])
def reschedule(request, pk):
    appointment = get_object_or_404(Appointment,pk=pk,business=request.booking_business)
    local = timezone.localtime(appointment.starts_at)
    form = RescheduleForm(request.POST if request.method=='POST' else None, business=request.booking_business,
        initial={'service':appointment.service_id,'staff':appointment.staff_id,'date':local.date(),'time':local.time(),'version':appointment.version})
    if request.method=='POST' and form.is_valid():
        try:
            services.reschedule(request.booking_business.pk,pk,form.cleaned_data)
        except ValidationError as error:
            errors(form,error)
        else:
            messages.success(request,'Appointment rescheduled. The customer’s confirmation link remains valid.')
            return redirect('bookings:detail',pk=pk)
    return render(request,'bookings/form.html',{'active':'bookings','form':form,'title':'Reschedule appointment',
        'description':'Choose an available time in 15-minute increments. The service and agreed price stay the same.'})


@never_cache
@require_http_methods(['GET','POST'])
def receipt(request, token):
    appointment = get_object_or_404(Appointment.objects.select_related('business','staff'),access_token=token)
    if request.method=='POST':
        try:
            services.change_status(appointment.business_id,appointment.pk,'cancelled',public_token=token)
        except ValidationError as error:
            messages.error(request,' '.join(error.messages))
        else:
            messages.success(request,'Your appointment has been cancelled.')
        return redirect('bookings:receipt',token=token)
    response = render(request,'bookings/receipt.html',{'appointment':appointment,'business':appointment.business,
        'can_cancel':appointment.status in services.ACTIVE and appointment.starts_at > timezone.now()})
    response['Referrer-Policy'] = 'no-referrer'
    response['X-Robots-Tag'] = 'noindex, nofollow'
    return response


@require_http_methods(['GET'])
def directory(request):
    query = request.GET.get('q','').strip()[:100]
    offers = Service.objects.filter(business_id=OuterRef('business_id'),active=True)
    staff = Staff.objects.filter(business_id=OuterRef('business_id'),active=True)
    calendars = Calendar.objects.filter(enabled=True,business__sector_profile__sector='services').select_related('business').annotate(
        has_services=Exists(offers),has_staff=Exists(staff),
        starting_price=Subquery(offers.order_by('price').values('price')[:1])).filter(has_services=True,has_staff=True)
    if query:
        calendars = calendars.annotate(matching_service=Exists(offers.filter(name__icontains=query))).filter(
            Q(business__name__icontains=query) | Q(business__district__icontains=query) | Q(matching_service=True)
            | Q(business__sector_profile__details__details__service_type__icontains=query))
    calendars = calendars.order_by('business__name','pk')
    return render(request,'bookings/directory.html',{'query':query,'page':Paginator(calendars,12).get_page(request.GET.get('page'))})
