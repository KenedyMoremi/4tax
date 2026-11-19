from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from bookkeeping.models import Business
from bookkeeping.services import setup_business
from .models import SectorProfile


@transaction.atomic
def save_profile(*, owner, sector, business_form, profile_forms):
    if sector != profile_forms.sector:
        raise ValidationError('The selected sector does not match the submitted form.')
    # Revalidate at the operation boundary; callers cannot submit raw JSON details.
    if not business_form.is_valid() or not profile_forms.is_valid():
        raise ValidationError('Please correct the highlighted fields.')
    get_user_model().objects.select_for_update(no_key=True).get(pk=owner.pk, is_active=True)
    business = Business.objects.select_for_update().filter(owner=owner).first()
    profile = SectorProfile.objects.select_for_update().filter(business=business).first() if business else None
    expected = profile_forms.identity.cleaned_data['version']
    if expected != (profile.version if profile else 0):
        raise ValidationError('These details were saved in another tab. Reload the page before editing again.')
    if profile and profile.sector != sector:
        raise ValidationError('Edit the sector already selected for this business.')
    if business:
        for name, value in business_form.cleaned_data.items():
            setattr(business, name, value)
        business.full_clean()
        business.save()
    else:
        business = setup_business(owner=owner, **business_form.cleaned_data)
    if not profile:
        profile = SectorProfile(business=business, sector=sector, version=0)
    profile.owner_id_number = profile_forms.identity.cleaned_data['owner_id_number']
    updated_details = profile_forms.cleaned_details()
    if profile.details and profile.details.get('schema_version') != 2:
        updated_details['previous_registration_details'] = profile.details
    elif 'previous_registration_details' in profile.details:
        updated_details['previous_registration_details'] = profile.details['previous_registration_details']
    profile.details = updated_details
    profile.version += 1
    profile.full_clean()
    profile.save()
    return profile
