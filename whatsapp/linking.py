import secrets
import uuid
from datetime import timedelta
from django import forms
from django.conf import settings
from agents.bookkeeping import provider_name
from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from django.utils import timezone
from django.utils.crypto import salted_hmac, constant_time_compare
from bookkeeping.models import Business, RecordProposal
from .models import WhatsAppLink


class LinkForm(forms.Form):
    phone = forms.RegexField(r'^\+[1-9][0-9]{7,14}$', max_length=16, label='WhatsApp number', help_text='International format, for example +266 followed by your number.')
    consent = forms.BooleanField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['consent'].label = f'I agree to send my bookkeeping messages to Twilio and {provider_name()} for processing.'


def digest(code):
    return salted_hmac('whatsapp-link', code, secret=settings.WHATSAPP_LINK_SECRET, algorithm='sha256').hexdigest()


@transaction.atomic
def change_link(business, owner, phone=None):
    Business.objects.select_for_update().get(pk=business.pk, owner=owner)
    link = WhatsAppLink.objects.select_for_update().filter(business=business).first()
    RecordProposal.objects.filter(business=business, owner=owner, status='pending', source_key__startswith='whatsapp:').update(status='cancelled')
    if phone is None:
        if link:
            link.active = False
            link.generation = uuid.uuid4()
            link.code_digest = ''
            link.verified_at = None
            link.save()
        return None
    if WhatsAppLink.objects.exclude(business=business).filter(phone=phone).exists():
        raise ValidationError('That number is already linked to another workspace.')
    code = secrets.token_hex(8).upper()
    values = dict(ai_provider=settings.BOOKKEEPING_AI_PROVIDER, owner=owner, phone=phone, active=True, generation=uuid.uuid4(), verified_at=None,
                  consent_at=timezone.now(), code_digest=digest(code),
                  code_expires_at=timezone.now()+timedelta(minutes=10), failed_attempts=0)
    try:
        with transaction.atomic():
            WhatsAppLink.objects.update_or_create(business=business, defaults=values)
    except IntegrityError:
        raise ValidationError('That number is already linked to another workspace.') from None
    return code


def verify(link, code):
    if not link.code_digest or link.failed_attempts >= 5 or link.code_expires_at <= timezone.now():
        return 'Generate a new linking code in the app. The code has expired or reached its attempt limit.'
    if not constant_time_compare(digest(code.upper()), link.code_digest):
        link.failed_attempts += 1
        link.save(update_fields=['failed_attempts'])
        return 'Incorrect linking code. Check the code shown in your signed-in workspace.'
    link.verified_at = timezone.now()
    link.code_digest = ''
    link.save(update_fields=['verified_at', 'code_digest'])
    return 'Your number is linked. Send HELP for examples. Every financial entry requires your confirmation.'
