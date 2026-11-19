import uuid
from datetime import time
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models


def working_days():
    return [0, 1, 2, 3, 4]


def validate_days(value):
    if not isinstance(value, list) or not value or any(type(day) is not int or day not in range(7) for day in value) or len(value) != len(set(value)):
        raise ValidationError('Choose at least one working day, without duplicates.')


def validate_duration(value):
    if value % 15:
        raise ValidationError('Use a duration in 15-minute increments.')


class Calendar(models.Model):
    business = models.OneToOneField('books.Business', on_delete=models.CASCADE, related_name='booking_calendar')
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    enabled = models.BooleanField('Accept online bookings', default=False)
    opens_at = models.TimeField(default=time(8))
    closes_at = models.TimeField(default=time(17))
    weekdays = models.JSONField(default=working_days, validators=[validate_days])
    welcome = models.CharField('Customer welcome message', max_length=300, blank=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(closes_at__gt=models.F('opens_at')), name='booking_hours_ordered')]

    def clean(self):
        super().clean()
        for value in [self.opens_at, self.closes_at]:
            if value and (value.minute % 15 or value.second or value.microsecond):
                raise ValidationError('Working hours must use 15-minute increments.')


class Service(models.Model):
    business = models.ForeignKey('books.Business', on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=300, blank=True)
    duration_minutes = models.PositiveSmallIntegerField(default=60, validators=[MinValueValidator(15), MaxValueValidator(480), validate_duration])
    price = models.DecimalField('Price (M)', max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name', 'pk']
        constraints = [models.CheckConstraint(condition=models.Q(duration_minutes__gte=15, duration_minutes__lte=480), name='booking_duration_limits'),
                       models.CheckConstraint(condition=models.Q(price__gte=0), name='booking_price_nonnegative')]

    def __str__(self):
        return self.name


class Staff(models.Model):
    business = models.ForeignKey('books.Business', on_delete=models.CASCADE)
    name = models.CharField('Staff member’s name', max_length=100)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name', 'pk']

    def __str__(self):
        return self.name


class Appointment(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Awaiting confirmation'
        CONFIRMED = 'confirmed', 'Confirmed'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'
        NO_SHOW = 'no_show', 'No-show'

    business = models.ForeignKey('books.Business', on_delete=models.PROTECT)
    service = models.ForeignKey(Service, on_delete=models.PROTECT)
    staff = models.ForeignKey(Staff, on_delete=models.PROTECT)
    request_key = models.UUIDField(default=uuid.uuid4)
    request_fingerprint = models.CharField(max_length=64)
    access_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    customer_name = models.CharField(max_length=120)
    customer_phone = models.CharField(max_length=30)
    customer_email = models.EmailField(blank=True)
    notes = models.CharField(max_length=500, blank=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    service_name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['starts_at', 'pk']
        constraints = [models.UniqueConstraint(fields=['business','request_key'], name='booking_request_idempotency'),
                       models.CheckConstraint(condition=models.Q(ends_at__gt=models.F('starts_at')), name='booking_ends_after_start'),
                       models.CheckConstraint(condition=models.Q(status__in=['pending','confirmed','completed','cancelled','no_show']), name='booking_valid_status'),
                       models.CheckConstraint(condition=models.Q(price__gte=0), name='booking_snapshot_nonnegative')]
        indexes = [models.Index(fields=['business','starts_at']), models.Index(fields=['business','status','starts_at'])]

    @property
    def reference(self):
        return f'BK-{self.pk:06d}'


class ReservedSlot(models.Model):
    """15-minute occupancy blocks enforce overlap protection in PostgreSQL and SQLite."""
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name='reserved_slots')
    staff = models.ForeignKey(Staff, on_delete=models.PROTECT)
    starts_at = models.DateTimeField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=['staff','starts_at'], name='booking_staff_slot_unique')]
