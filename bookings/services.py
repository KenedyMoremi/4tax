from datetime import datetime, timedelta
from hashlib import sha256
import json

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from bookkeeping.models import Business
from .models import Calendar, Service, Staff, Appointment, ReservedSlot

STEP = timedelta(minutes=15)
ACTIVE = [Appointment.Status.PENDING, Appointment.Status.CONFIRMED]


def service_business(business_id, *, lock=False):
    qs = Business.objects.filter(pk=business_id, sector_profile__sector='services')
    if lock:
        qs = qs.select_for_update(of=('self',))
    business = qs.first()
    if not business:
        raise ValidationError('Bookings are available to registered service-sector businesses.')
    return business


def bounds(calendar, date):
    zone = timezone.get_default_timezone()
    return (timezone.make_aware(datetime.combine(date, calendar.opens_at), zone),
            timezone.make_aware(datetime.combine(date, calendar.closes_at), zone))


def blocks(start, end):
    cursor = start
    while cursor < end:
        yield cursor
        cursor += STEP


def available_slots(calendar, service, staff, date, *, exclude=None):
    if service.business_id != calendar.business_id or staff.business_id != calendar.business_id or not service.active or not staff.active:
        return []
    today = timezone.localdate()
    if not today <= date <= today + timedelta(days=90) or date.weekday() not in calendar.weekdays:
        return []
    opening, closing = bounds(calendar, date)
    occupied = ReservedSlot.objects.filter(staff=staff, starts_at__gte=opening, starts_at__lt=closing)
    if exclude:
        occupied = occupied.exclude(appointment_id=exclude)
    reserved = set(occupied.values_list('starts_at', flat=True))
    duration = timedelta(minutes=service.duration_minutes)
    earliest = timezone.now() + timedelta(minutes=30)
    return [start for start in blocks(opening, closing) if start >= earliest and start + duration <= closing
            and not any(block in reserved for block in blocks(start, start + duration))]


def _selection(business, data, *, public, exclude=None):
    calendar = Calendar.objects.filter(business=business).first()
    if not calendar or (public and not calendar.enabled):
        raise ValidationError('This business is not accepting online bookings.')
    service = Service.objects.filter(pk=data['service'].pk, business=business, active=True).first()
    staff = Staff.objects.filter(pk=data['staff'].pk, business=business, active=True).first()
    if not service or not staff:
        raise ValidationError('Choose an active service and staff member from this business.')
    start = timezone.make_aware(datetime.combine(data['date'], data['time']), timezone.get_default_timezone())
    if start not in available_slots(calendar, service, staff, data['date'], exclude=exclude):
        raise ValidationError('That time is no longer available. Choose another available time.')
    return service, staff, start, start + timedelta(minutes=service.duration_minutes)


def _reserve(appointment):
    try:
        with transaction.atomic():
            ReservedSlot.objects.bulk_create([ReservedSlot(appointment=appointment, staff=appointment.staff, starts_at=start)
                                             for start in blocks(appointment.starts_at, appointment.ends_at)])
    except IntegrityError:
        raise ValidationError('That time was just booked. Please choose another time.') from None


@transaction.atomic
def create_appointment(business_id, data, *, public=True):
    business = service_business(business_id, lock=True)
    normalized = {key: str(value.pk if key in ('service','staff') else value) for key, value in data.items() if key != 'request_key'}
    fingerprint = sha256(json.dumps(normalized, sort_keys=True).encode()).hexdigest()
    previous = Appointment.objects.filter(business=business, request_key=data['request_key']).first()
    if previous:
        if previous.request_fingerprint != fingerprint:
            raise ValidationError('This booking request was already used. Reload the page for a new booking.')
        return previous
    service, staff, start, end = _selection(business, data, public=public)
    appointment = Appointment.objects.create(business=business, service=service, staff=staff,
        request_key=data['request_key'], request_fingerprint=fingerprint,
        customer_name=data['customer_name'], customer_phone=data['customer_phone'],
        customer_email=data.get('customer_email', ''), notes=data.get('notes',''),
        service_name=service.name, price=service.price, starts_at=start, ends_at=end,
        status=Appointment.Status.PENDING if public else Appointment.Status.CONFIRMED)
    _reserve(appointment)
    return appointment


@transaction.atomic
def change_status(business_id, appointment_id, status, *, public_token=None):
    service_business(business_id, lock=True)
    qs = Appointment.objects.filter(business_id=business_id, pk=appointment_id)
    if public_token is not None:
        qs = qs.filter(access_token=public_token)
    appointment = qs.get()
    if public_token is not None and (status != Appointment.Status.CANCELLED or appointment.starts_at <= timezone.now()):
        raise ValidationError('Contact the business to change this appointment.')
    if status == appointment.status:
        return appointment
    allowed = {'pending': {'confirmed','cancelled'}, 'confirmed': {'completed','no_show','cancelled'}}
    if status not in allowed.get(appointment.status, set()):
        raise ValidationError('This appointment cannot make that status change.')
    if status in ('completed','no_show') and appointment.starts_at > timezone.now():
        raise ValidationError('Wait until the appointment starts before completing it or marking a no-show.')
    appointment.status = status
    appointment.version += 1
    appointment.save(update_fields=['status','version'])
    if status == Appointment.Status.CANCELLED:
        appointment.reserved_slots.all().delete()
    return appointment


@transaction.atomic
def reschedule(business_id, appointment_id, data):
    business = service_business(business_id, lock=True)
    appointment = Appointment.objects.get(business=business, pk=appointment_id)
    if appointment.status not in ACTIVE or appointment.starts_at <= timezone.now():
        raise ValidationError('Only upcoming active appointments can be rescheduled.')
    if appointment.version != data['version']:
        raise ValidationError('This appointment changed in another tab. Reload it before editing.')
    service, staff, start, end = _selection(business, data, public=False, exclude=appointment.pk)
    if service.pk != appointment.service_id:
        raise ValidationError('To change the service, cancel this appointment and create a new booking.')
    appointment.reserved_slots.all().delete()
    appointment.staff = staff
    appointment.starts_at, appointment.ends_at = start, end
    appointment.version += 1
    appointment.save(update_fields=['staff','starts_at','ends_at','version'])
    _reserve(appointment)
    return appointment


@transaction.atomic
def save_calendar(owner, form):
    business = Business.objects.get(owner=owner)
    service_business(business.pk, lock=True)
    if not form.is_valid():
        raise ValidationError('Correct the highlighted fields.')
    existing = Calendar.objects.filter(business=business).first()
    if existing and form.instance.pk != existing.pk:
        raise ValidationError('Calendar settings already exist. Reload the page.')
    calendar = form.save(commit=False)
    calendar.business = business
    if calendar.enabled and (not Service.objects.filter(business=business, active=True).exists() or not Staff.objects.filter(business=business, active=True).exists()):
        raise ValidationError('Add at least one active service and staff member before enabling online bookings.')
    for appointment in Appointment.objects.filter(business=business, status__in=ACTIVE, ends_at__gt=timezone.now()).iterator():
        local = timezone.localtime(appointment.starts_at)
        opening, closing = bounds(calendar, local.date())
        if local.weekday() not in calendar.weekdays or appointment.starts_at < opening or appointment.ends_at > closing:
            raise ValidationError('These hours exclude an existing appointment. Reschedule or cancel it first.')
    calendar.full_clean()
    calendar.save()
    return calendar


@transaction.atomic
def save_catalog(owner, form):
    business = Business.objects.get(owner=owner)
    service_business(business.pk, lock=True)
    if not form.is_valid():
        raise ValidationError('Correct the highlighted fields.')
    item = form.save(commit=False)
    if item.pk and item.business_id != business.pk:
        raise ValidationError('This item belongs to another business.')
    item.business = business
    item.full_clean()
    item.save()
    return item
