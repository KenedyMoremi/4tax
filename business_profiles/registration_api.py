import json
import re

from django.db import DatabaseError, transaction
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.debug import sensitive_variables

from .models import USSDRegistration
from .registration_auth import AuthenticationFailure, authenticate_owner
from .registration_forms import validate_registration


def error(status, code, fields=None):
    response = JsonResponse({'code': code, 'message': code.replace('_', ' ').capitalize(),
                             'fields': fields or {}}, status=status)
    if status == 401:
        response['WWW-Authenticate'] = 'Bearer'
    return response


def same_payload(left, right):
    # Keep JSON booleans distinct from numbers, unlike Python dictionary equality.
    return json.dumps(left, sort_keys=True, separators=(',', ':')) == json.dumps(right, sort_keys=True, separators=(',', ':'))


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


@csrf_exempt  # Stateless bearer authentication only; browser sessions are never accepted.
@never_cache
@sensitive_variables()
def register_business(request):
    if request.method != 'POST':
        response = error(405, 'METHOD_NOT_ALLOWED')
        response['Allow'] = 'POST'
        return response
    try:
        issuer, owner = authenticate_owner(request)
    except AuthenticationFailure as failure:
        return error(failure.status, failure.code)
    key = request.headers.get('Idempotency-Key', '')
    if not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}', key):
        return error(400, 'INVALID_IDEMPOTENCY_KEY')
    if request.content_type != 'application/json':
        return error(415, 'UNSUPPORTED_MEDIA_TYPE')
    try:
        # Read at most the contract's bounded payload size, even without Content-Length.
        body = request.read(16385)
        if len(body) > 16384:
            return error(413, 'PAYLOAD_TOO_LARGE')
        payload = json.loads(body, object_pairs_hook=unique_object,
                             parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if not isinstance(payload, dict):
            raise ValueError()
    except (ValueError, UnicodeDecodeError, RecursionError):
        return error(400, 'INVALID_JSON')
    try:
        identity = dict(issuer=issuer, owner_subject=owner, idempotency_key=key)
        existing = USSDRegistration.objects.filter(**identity).first()
        if existing:
            if not same_payload(existing.payload, payload):
                return error(409, 'IDEMPOTENCY_CONFLICT')
            return JsonResponse({'entityId': str(existing.pk), 'reference': existing.reference})
        fields = validate_registration(payload)
        if fields:
            return error(422, 'VALIDATION_ERROR', fields)
        # The unique constraint and get_or_create's savepoint handle concurrent retries.
        with transaction.atomic():
            registration, created = USSDRegistration.objects.get_or_create(
                **identity, defaults={'payload': payload})
            if not same_payload(registration.payload, payload):
                return error(409, 'IDEMPOTENCY_CONFLICT')
        return JsonResponse({'entityId': str(registration.pk), 'reference': registration.reference},
                            status=201 if created else 200)
    except DatabaseError:
        return error(503, 'SERVICE_UNAVAILABLE')


@never_cache
def registration_options(request):
    """Public field metadata contains no identities, saved records or credentials."""
    from django import forms
    from .forms import SECTORS, SectorForm, IdentityForm

    if request.method != 'GET':
        response = error(405, 'METHOD_NOT_ALLOWED')
        response['Allow'] = 'GET'
        return response

    def describe(name, field):
        kind = ('boolean' if isinstance(field, forms.BooleanField) else
                'decimal' if isinstance(field, forms.DecimalField) else
                'integer' if isinstance(field, forms.IntegerField) else
                'multiple_choice' if isinstance(field, forms.MultipleChoiceField) else
                'choice' if isinstance(field, forms.ChoiceField) else
                'time' if isinstance(field, forms.TimeField) else 'string')
        result = {'name': name, 'label': str(field.label or name), 'type': kind, 'required': field.required}
        if hasattr(field, 'choices'):
            result['choices'] = [{'value': value, 'label': str(label)} for value, label in field.choices if value != '']
        for attr in ('min_value', 'max_value', 'max_length', 'decimal_places', 'max_digits'):
            value = getattr(field, attr, None)
            if value is not None:
                result[attr] = str(value)
        return result

    labels = dict(SectorForm.base_fields['sector'].choices)
    sectors = []
    for sector, (main, groups) in SECTORS.items():
        fields = list(main.base_fields.items())
        # Present the business/activity choice before collecting detailed operations.
        fields.sort(key=lambda item: item[0] not in ('business_type', 'service_type', 'goods_type', 'activity'))
        sectors.append({'value': sector, 'label': labels[sector],
                        'fields': [describe(*item) for item in fields],
                        'collections': [{'name': name, 'label': label, 'minimum': minimum, 'maximum': 50,
                                         'actions': ['add_another', 'continue'],
                                         'fields': [describe(*item) for item in row.base_fields.items()]}
                                        for name, label, row, minimum in groups]})
    return JsonResponse({'schemaVersion': 2, 'currency': 'LSL', 'turnoverPeriod': 'monthly',
                         'salaryPeriod': 'monthly', 'ownerFields': [
                             describe('fullNames', IdentityForm.base_fields['owner_full_name']),
                             describe('idNumber', IdentityForm.base_fields['owner_id_number'])],
                         'sectors': sectors})
