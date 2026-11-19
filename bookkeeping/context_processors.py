from django.db.models import Exists, OuterRef
from business_profiles.models import SectorProfile
from .models import Business


def workspace(request):
    business = None
    if request.user.is_authenticated:
        profiles = SectorProfile.objects.filter(business_id=OuterRef('pk'))
        business = Business.objects.annotate(has_sector_profile=Exists(profiles), is_service_business=Exists(profiles.filter(sector='services')), has_pos=Exists(profiles.filter(sector__in=['transport','ecommerce','retail','agriculture']))).filter(owner=request.user).first()
    return {'workspace':business, 'needs_sector_profile':bool(business and not business.has_sector_profile)}
