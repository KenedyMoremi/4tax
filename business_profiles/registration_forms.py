"""Adapt bounded JSON registrations to the same forms used by web registration."""
from django.http import QueryDict
from .forms import ProfileForms, SECTORS


def validate_registration(payload):
    allowed = {'sector', 'owner', 'businessName', 'details', 'employees', 'routes', 'livestock', 'source'}
    errors = {}
    sector = payload.get('sector')
    if not isinstance(sector, str) or sector not in SECTORS:
        return {'sector': 'Choose transport, services, ecommerce, retail or agriculture.'}
    owner, details, source = (payload.get(key) for key in ('owner', 'details', 'source'))
    if 'owner' in payload and (not isinstance(owner, dict) or set(owner) != {'fullNames', 'idNumber'}):
        errors['owner'] = 'Supply fullNames and idNumber.'
    if not isinstance(details, dict):
        errors['details'] = 'Expected an object.'
    if not isinstance(source, dict) or set(source) != {'channel', 'language'} or source.get('channel') != 'USSD' or source.get('language') not in ('en', 'st'):
        errors['source'] = 'Supply channel USSD and language en or st.'
    name = payload.get('businessName')
    if name is not None and (not isinstance(name, str) or not name.strip() or len(name) > 250):
        errors['businessName'] = 'Use a non-empty name of at most 250 characters.'
    if set(payload) - allowed:
        errors['__all__'] = 'Unknown fields are not accepted.'
    if errors:
        return errors
    data = QueryDict('', mutable=True)
    def put(key, value):
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            data.setlist(key, value)
        elif isinstance(value, (str, int, bool)) and not isinstance(value, float):
            data[key] = 'on' if value is True else '' if value is False else str(value)
        else:
            errors[key] = 'Use strings, integers, booleans or a list of choices; decimal amounts must be strings.'
    for source_key, field in [('fullNames', 'owner_full_name'), ('idNumber', 'owner_id_number')]:
        if owner is None:
            continue
        if not isinstance(owner.get(source_key), str):
            errors['owner.' + source_key] = 'Expected a string.'
        else:
            put('identity-' + field, owner[source_key])
    data['identity-version'] = '0'
    main, collections = SECTORS[sector]
    if set(details) - set(main.base_fields):
        errors['details'] = 'Unknown fields for this sector.'
    for key, value in details.items():
        put('details-' + key, value)
    prefixes = {group[0] for group in collections}
    if (set(payload) & {'employees', 'routes', 'livestock'}) - prefixes:
        errors['__all__'] = 'Collection does not apply to this sector.'
    for prefix, _, form, _ in collections:
        rows = payload.get(prefix)
        if not isinstance(rows, list) or len(rows) > 50:
            errors[prefix] = 'Supply an array with at most 50 entries; use [] when none.'
            continue
        data[prefix + '-TOTAL_FORMS'] = str(len(rows))
        data[prefix + '-INITIAL_FORMS'] = '0'
        for index, row in enumerate(rows):
            if not isinstance(row, dict) or set(row) != set(form.base_fields):
                errors[f'{prefix}.{index}'] = 'Supply all row fields and no unknown fields.'
                continue
            for key, value in row.items():
                put(f'{prefix}-{index}-{key}', value)
    if errors:
        return errors
    forms = ProfileForms(sector, data)
    if 'owner' not in payload:
        # The bearer endpoint already derives ownership from the verified issuer/subject.
        # Keep validating supplied identity data, but do not collect it again after login.
        for field in ('owner_full_name', 'owner_id_number'):
            forms.identity.fields[field].required = False
    if not forms.is_valid():
        for prefix, form in [('owner', forms.identity), ('details', forms.main)]:
            for field, messages in form.errors.items():
                errors[f'{prefix}.{field}'] = str(messages[0])
        for group in forms.groups:
            for index, row in enumerate(group['formset'].errors):
                for field, messages in row.items():
                    errors[f"{group['prefix']}.{index}.{field}"] = str(messages[0])
            if group['formset'].non_form_errors():
                errors[group['prefix']] = str(group['formset'].non_form_errors()[0])
    return errors
