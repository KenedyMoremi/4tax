"""Authenticated USSD adapter at the existing webhook; shares AI/ledger operations with WhatsApp."""
import json
import re
import uuid
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables

from agents.bookkeeping import AgentUnavailable, RecordIntent, interpret
from bookkeeping import agent_actions, services
from bookkeeping.models import Business, money
from .models import USSDLedger, USSDRegistration, USSDTransaction
from .registration_api import error, same_payload, unique_object
from .registration_auth import AuthenticationFailure, authenticate_owner

SECTOR_FIELDS = {'transport': ['route', 'passengers', 'fareCost'],
                 'services': ['service', 'serviceCost'],
                 'ecommerce': ['goods', 'totalValue'], 'retail': ['goods', 'totalValue'],
                 'agriculture': ['goods', 'totalValue']}


def ledger_for(registration):
    # Caller holds the registration row lock. Each entity gets its own books, including for multi-business owners.
    link = USSDLedger.objects.select_related('business__owner').filter(registration=registration).first()
    if link:
        return link.business
    owner = get_user_model().objects.create_user(username='ussd_' + uuid.uuid4().hex, password=None)
    business = services.setup_business(owner=owner, name=(registration.payload.get('businessName') or registration.reference)[:150],
                                      district='', address=registration.payload.get('details', {}).get('location', '')[:250])
    USSDLedger.objects.create(registration=registration, business=business)
    return business


def snapshot(item):
    item.refresh_from_db()
    proposal = item.proposal
    if item.status == 'processing':
        return error(409, 'TRANSACTION_BUSY')
    if item.status == 'clarify':
        return error(422, 'CLARIFICATION_REQUIRED')
    if item.status == 'failed':
        return error(503, 'AI_UNAVAILABLE')
    if not proposal:
        return error(503, 'SERVICE_UNAVAILABLE')
    data = proposal.payload
    amount, rate = Decimal(data['amount']), Decimal(data['tax_rate'])
    net = money(amount/(1+rate/100)) if data['amount_basis'] == 'inclusive' else amount
    tax = money(net*rate/100)
    return JsonResponse({'transactionId': str(item.pk), 'status': item.status,
                         'reference': proposal.reference, 'summary': proposal.summary,
                         'result': proposal.result, 'preview': {'action': data['action'], 'description': data['description'],
                         'date': data['date'], 'net': str(net), 'tax': str(tax), 'total': str(net+tax),
                         'buyer': data['contact_name'], 'paymentAccount': data['payment_account'], 'dueDate': data['due_date']}})


def clean_payload(payload, registration):
    if set(payload) != {'channel', 'action', 'entityId', 'sector', 'fields', 'language'}:
        return None
    sector = registration.payload['sector']
    fields = payload.get('fields')
    names = SECTOR_FIELDS.get(sector, []) + ['paymentDetails', 'buyer']
    if payload.get('sector') != sector or payload.get('language') not in ['en', 'st'] or not isinstance(fields, dict) or set(fields) != set(names):
        return None
    if any(not isinstance(value, str) or not value.strip() or len(value) > 256
           or any(ord(c) < 32 or ord(c) == 127 for c in value) for value in fields.values()):
        return None
    return payload


@sensitive_variables()
def ussd_webhook(request):
    try:
        issuer, subject = authenticate_owner(request, 'transactions:create')
    except AuthenticationFailure as failure:
        return error(failure.status, failure.code)
    key = request.headers.get('Idempotency-Key', '')
    if not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}', key):
        return error(400, 'INVALID_IDEMPOTENCY_KEY')
    if request.content_type != 'application/json':
        return error(415, 'UNSUPPORTED_MEDIA_TYPE')
    try:
        body = request.read(8193)
        if len(body) > 8192:
            return error(413, 'PAYLOAD_TOO_LARGE')
        payload = json.loads(body, object_pairs_hook=unique_object,
                             parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if not isinstance(payload, dict) or payload.get('channel') != 'USSD':
            raise ValueError()
        entity_id = uuid.UUID(payload.get('entityId', ''))
        action = payload.get('action')
    except (ValueError, TypeError, AttributeError, UnicodeDecodeError, RecursionError):
        return error(400, 'INVALID_REQUEST')
    try:
        with transaction.atomic():
            registration = USSDRegistration.objects.select_for_update().filter(pk=entity_id, issuer=issuer, owner_subject=subject).first()
            if not registration:
                return error(404, 'BUSINESS_NOT_FOUND')
            if action in ['confirm', 'cancel']:
                return resolve(registration, payload, key, action)
            if action != 'propose' or not clean_payload(payload, registration):
                return error(422, 'VALIDATION_ERROR')
            item = USSDTransaction.objects.filter(registration=registration, idempotency_key=key).first()
            if item and not same_payload(item.payload, payload):
                return error(409, 'IDEMPOTENCY_CONFLICT')
            if item and item.status not in ['processing', 'failed']:
                return snapshot(item)
            if item and item.status == 'processing' and item.lease_until > timezone.now():
                return error(409, 'TRANSACTION_BUSY')
            business = ledger_for(registration)
            if not item:
                item = USSDTransaction(registration=registration, idempotency_key=key, payload=payload)
            item.status = 'processing'; item.claim_token = uuid.uuid4()
            item.lease_until = timezone.now() + timedelta(seconds=90)
            item.save()
            claim = item.claim_token
        # No database lock is held while waiting on the AI provider. A lease bounds recovery after a lost worker.
        message = ('Prepare ONE sale or unpaid sales invoice from these USSD fields. Do not post it. '
                   'For transport, fareCost must specify per passenger or total; ask for clarification if ambiguous. '
                   'Do not infer payment status or account. Buyer N/A is permitted for a paid sale, not an unpaid invoice.\n'
                   'Keep the description in the selected language (en=English, st=Sesotho).\n'
                   + json.dumps({'sector': payload['sector'], 'fields': payload['fields'], 'language': payload['language']}, ensure_ascii=False))
        try:
            intent = RecordIntent.model_validate(interpret(message, context=agent_actions.context_for(business, timezone.localdate(item.created_at)))).model_dump()
        except (AgentUnavailable, ValueError):
            USSDTransaction.objects.filter(pk=item.pk, claim_token=claim, status='processing').update(status='failed')
            return error(503, 'AI_UNAVAILABLE')
        with transaction.atomic():
            USSDRegistration.objects.select_for_update().get(pk=registration.pk)
            Business.objects.select_for_update().get(pk=business.pk)
            item = USSDTransaction.objects.select_for_update().get(pk=item.pk)
            if item.claim_token != claim or item.status != 'processing':
                return snapshot(item)
            if intent['action'] not in ['sale', 'invoice'] or (intent['action'] == 'invoice' and payload['fields']['buyer'].strip().lower() == 'n/a'):
                item.status = 'clarify'; item.save(update_fields=['status'])
                return error(422, 'CLARIFICATION_REQUIRED')
            if payload['fields']['buyer'].strip().lower() == 'n/a':
                intent['contact_name'] = 'N/A'
            try:
                proposal = agent_actions.propose(business=business, owner=business.owner, source_key='ussd:' + item.id.hex, data=intent)
            except ValidationError:
                item.status = 'clarify'; item.save(update_fields=['status'])
                return error(422, 'CLARIFICATION_REQUIRED')
            item.proposal = proposal; item.status = 'pending'; item.save(update_fields=['proposal', 'status'])
            return snapshot(item)
    except DatabaseError:
        return error(503, 'SERVICE_UNAVAILABLE')


def resolve(registration, payload, key, action):
    if set(payload) != {'channel', 'action', 'entityId', 'transactionId'}:
        return error(422, 'VALIDATION_ERROR')
    try:
        transaction_id = uuid.UUID(payload.get('transactionId', ''))
    except (ValueError, TypeError, AttributeError):
        return error(400, 'INVALID_REQUEST')
    item = USSDTransaction.objects.select_related('proposal__business__owner').filter(
        pk=transaction_id, registration=registration, idempotency_key=key).first()
    if not item or not item.proposal:
        return error(404, 'TRANSACTION_NOT_FOUND')
    if item.status == 'posted':
        return snapshot(item) if action == 'confirm' else error(409, 'ALREADY_POSTED')
    if item.status == 'cancelled':
        return snapshot(item) if action == 'cancel' else error(409, 'TRANSACTION_CANCELLED')
    try:
        proposal = item.proposal
        agent_actions.resolve_proposal(business=proposal.business, owner=proposal.owner,
                                       reference=proposal.reference, confirm=action == 'confirm', channel='USSD')
    except ValidationError:
        return error(422, 'PROPOSAL_EXPIRED_OR_CHANGED')
    proposal.refresh_from_db()
    item.status = proposal.status; item.save(update_fields=['status'])
    return snapshot(item)
