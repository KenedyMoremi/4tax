"""Durable inbound processing and an outbox; no background work in web requests."""
import re
import uuid
from datetime import timedelta
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Exists, OuterRef
from django.utils import timezone
from twilio.rest import Client
from twilio.http.http_client import TwilioHttpClient
from agents.bookkeeping import interpret, AgentUnavailable, RecordIntent
from bookkeeping import agent_actions
from bookkeeping.models import Business
from .linking import verify
from .models import InboundMessage, OutboundMessage, WhatsAppLink

HELP = ('Send one complete record, for example: Paid M250 for transport from M-Pesa today. '
        'You can record paid expenses, paid sales, unpaid invoices/bills and payments against document numbers. '
        'Specify the account, amount and description; unpaid documents also need a party and due date. '
        'State the VAT rate and inclusive/exclusive amount when applicable. '
        'Review the preview, then CONFIRM <code> or CANCEL <code>. SUMMARY shows this month. '
        'Text only for now. To correct a preview, cancel it and resend the complete record.')


def valid_link(link, message):
    return (link.active and link.generation == message.generation and link.owner.is_active
            and link.business.owner_id == link.owner_id)


@transaction.atomic
def claim():
    now = timezone.now()
    older = InboundMessage.objects.filter(link_id=OuterRef('link_id'), pk__lt=OuterRef('pk'), status__in=['queued', 'processing'])
    candidate = (InboundMessage.objects.annotate(has_older=Exists(older)).filter(has_older=False)
                 .filter(Q(status='queued', available_at__lte=now) | Q(status='processing', lease_until__lt=now))
                 .order_by('pk').first())
    if not candidate:
        return None
    token = uuid.uuid4()
    changed = InboundMessage.objects.filter(pk=candidate.pk, status=candidate.status, claim_token=candidate.claim_token).update(
        status='processing', claim_token=token, lease_until=now+timedelta(minutes=2), attempts=candidate.attempts+1)
    return InboundMessage.objects.select_related('link__business', 'link__owner').get(pk=candidate.pk) if changed else None


def process_one():
    message = claim()
    if not message:
        return False
    try:
        return process_message(message)
    except Exception:
        # Keep a poison message from blocking this owner's queue indefinitely.
        # The posting transaction has rolled back before this handler runs.
        with transaction.atomic():
            current = InboundMessage.objects.select_for_update().get(pk=message.pk)
            if current.status == 'processing' and current.claim_token == message.claim_token:
                current.status = 'failed' if current.attempts >= 3 else 'queued'
                current.available_at = timezone.now()+timedelta(seconds=30*current.attempts)
                current.error_code = 'processing_failed'
                current.save(update_fields=['status', 'available_at', 'error_code'])
        return True


def process_message(message):
    link = message.link
    text = message.body.strip()
    command = re.fullmatch(r'(CONFIRM|CANCEL)\s+([A-F0-9]{12})', text.upper())
    intent = None
    error = None
    if valid_link(link, message) and link.verified_at and not message.media_count and text.upper() not in ['HELP', 'SUMMARY'] and not command:
        if text.upper().startswith(('CONFIRM', 'CANCEL', 'LINK')) or text.upper() in ['YES', 'NO']:
            error = 'Use CONFIRM followed by the preview code, or CANCEL followed by the code.'
        elif message.created_at < timezone.now()-timedelta(hours=23):
            error = 'This message is too old. Please resend the complete record.'
        elif message.attempts > 3:
            error = 'This message could not be processed. Please resend the complete record.'
        else:
            try:
                intent = RecordIntent.model_validate(interpret(text, context=agent_actions.context_for(link.business, timezone.localdate(message.created_at)))).model_dump()
            except (AgentUnavailable, ValueError):
                if message.attempts < 3:
                    InboundMessage.objects.filter(pk=message.pk, claim_token=message.claim_token, status='processing').update(
                        status='queued', available_at=timezone.now()+timedelta(seconds=30*message.attempts), error_code='ai_unavailable')
                    return True
                error = 'The AI service is unavailable. No entry was posted. Please try again later or use the app.'
    with transaction.atomic():
        Business.objects.select_for_update().get(pk=link.business_id)
        link = WhatsAppLink.objects.select_for_update().select_related('business', 'owner').get(pk=link.pk)
        current = InboundMessage.objects.select_for_update().get(pk=message.pk)
        if current.claim_token != message.claim_token or current.status != 'processing':
            return True
        reply = None
        if valid_link(link, current):
            try:
                if not link.verified_at:
                    reply = verify(link, text[5:].strip()) if text.upper().startswith('LINK ') else 'Send LINK followed by the code shown in your signed-in WhatsApp settings.'
                elif message.media_count:
                    reply = 'Please type the record as text. Images, documents and voice notes are not processed yet.'
                elif error:
                    reply = error
                elif text.upper() == 'HELP':
                    reply = HELP
                elif text.upper() == 'SUMMARY':
                    reply = agent_actions.summary(link.business)
                elif command:
                    reply = agent_actions.resolve_proposal(business=link.business, owner=link.owner, reference=command[2], confirm=command[1]=='CONFIRM')
                elif intent and intent['action'] == 'clarify':
                    reply = (intent['question'] or 'Please provide the amount, description and payment account.')[:1000] + '\nResend the complete instruction. No record has been posted.'
                elif intent:
                    proposal = agent_actions.propose(business=link.business, owner=link.owner, source_key='whatsapp:'+message.sid, data=intent)
                    reply = proposal.summary + f'\n\nReview carefully. Reply CONFIRM {proposal.reference} or CANCEL {proposal.reference}. Expires in 30 minutes. Nothing has been posted yet.'
                else:
                    reply = HELP
            except ValidationError as exc:
                reply = ' '.join(exc.messages)
        if reply:
            OutboundMessage.objects.get_or_create(inbound=current, defaults={'body': reply[:1500]})
        current.status = 'done'
        current.processed_at = timezone.now()
        current.error_code = ''
        current.save(update_fields=['status', 'processed_at', 'error_code'])
    return True


def send_one():
    now = timezone.now()
    # A crash/timeout may occur after Twilio accepts a send. Never blindly resend.
    OutboundMessage.objects.filter(status='sending', attempted_at__lt=now-timedelta(minutes=2)).update(status='uncertain', error_code='interrupted_send')
    if OutboundMessage.objects.filter(attempted_at__gt=now-timedelta(seconds=settings.WHATSAPP_SEND_INTERVAL_SECONDS)).exists():
        return False
    with transaction.atomic():
        item = OutboundMessage.objects.filter(status='pending').select_related('inbound__link__owner', 'inbound__link__business').first()
        if not item:
            return False
        if not OutboundMessage.objects.filter(pk=item.pk, status='pending').update(status='sending', attempted_at=now):
            return True
        if not valid_link(item.inbound.link, item.inbound):
            OutboundMessage.objects.filter(pk=item.pk).update(status='cancelled')
            return True
        if item.inbound.created_at < now-timedelta(hours=23):
            OutboundMessage.objects.filter(pk=item.pk).update(status='expired')
            return True
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN,
                        http_client=TwilioHttpClient(timeout=10, max_retries=0))
        result = client.messages.create(to='whatsapp:'+item.inbound.link.phone, from_=settings.TWILIO_WHATSAPP_FROM, body=item.body)
    except Exception:
        # No provider text, message content, phone number or credentials in logs.
        OutboundMessage.objects.filter(pk=item.pk, status='sending').update(status='uncertain', error_code='send_unconfirmed')
    else:
        OutboundMessage.objects.filter(pk=item.pk, status='sending').update(status='sent', sid=result.sid, sent_at=timezone.now())
    return True
