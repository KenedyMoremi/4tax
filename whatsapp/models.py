import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class WhatsAppLink(models.Model):
    business = models.OneToOneField('books.Business', on_delete=models.CASCADE)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    phone = models.CharField(max_length=16, unique=True)
    generation = models.UUIDField(default=uuid.uuid4)
    active = models.BooleanField(default=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    consent_at = models.DateTimeField(default=timezone.now)
    code_digest = models.CharField(max_length=64, blank=True)
    code_expires_at = models.DateTimeField(null=True, blank=True)
    failed_attempts = models.PositiveSmallIntegerField(default=0)


class InboundMessage(models.Model):
    class Status(models.TextChoices):
        QUEUED = 'queued', 'Queued'
        PROCESSING = 'processing', 'Processing'
        DONE = 'done', 'Processed'
        FAILED = 'failed', 'Needs review'
    sid = models.CharField(max_length=34, unique=True)
    link = models.ForeignKey(WhatsAppLink, on_delete=models.CASCADE)
    generation = models.UUIDField()
    body = models.TextField(max_length=4000)
    media_count = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.QUEUED)
    attempts = models.PositiveSmallIntegerField(default=0)
    available_at = models.DateTimeField(default=timezone.now)
    lease_until = models.DateTimeField(null=True, blank=True)
    claim_token = models.UUIDField(null=True, blank=True)
    error_code = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        indexes = [models.Index(fields=['status', 'available_at']), models.Index(fields=['link', 'created_at'])]
        ordering = ['pk']


class OutboundMessage(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SENDING = 'sending', 'Sending'
        SENT = 'sent', 'Accepted by Twilio'
        UNCERTAIN = 'uncertain', 'Delivery uncertain'
        FAILED = 'failed', 'Failed'
        EXPIRED = 'expired', 'Reply window expired'
        CANCELLED = 'cancelled', 'Cancelled'
    inbound = models.OneToOneField(InboundMessage, on_delete=models.CASCADE)
    body = models.TextField(max_length=1500)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    sid = models.CharField(max_length=34, blank=True)
    error_code = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    attempted_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        ordering = ['pk']
        indexes = [models.Index(fields=['status', 'created_at'])]
