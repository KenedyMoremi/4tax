from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods
from bookkeeping.forms import BusinessForm
from bookkeeping.models import Business
from .forms import SectorForm, ProfileForms, SECTORS
from .models import SectorProfile
from .services import save_profile


@never_cache
@login_required
@require_http_methods(['GET','POST'])
def select_sector(request):
    profile = SectorProfile.objects.filter(business__owner=request.user).first()
    if profile:
        return redirect('sector_details', sector=profile.sector)
    form = SectorForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        return redirect('sector_details', sector=form.cleaned_data['sector'])
    return render(request, 'business_profiles/sector.html', {'form':form, 'title':'Choose your sector', 'active':'profile'})


@sensitive_post_parameters()
@never_cache
@login_required
@require_http_methods(['GET','POST'])
def details(request, sector):
    if sector not in SECTORS:
        raise Http404
    business = Business.objects.filter(owner=request.user).first()
    profile = SectorProfile.objects.filter(business=business).first() if business else None
    if profile and profile.sector != sector:
        return redirect('sector_details', sector=profile.sector)
    data = request.POST if request.method=='POST' else None
    business_form = BusinessForm(data, prefix='business', instance=business)
    profile_forms = ProfileForms(sector, data, profile)
    if request.method=='POST':
        valid_business = business_form.is_valid()
        valid_profile = profile_forms.is_valid()
        if valid_business and valid_profile:
            try:
                save_profile(owner=request.user, sector=sector, business_form=business_form, profile_forms=profile_forms)
            except ValidationError as error:
                profile_forms.identity.add_error(None, error)
            else:
                messages.success(request, 'Business details saved. Your workspace is ready.')
                return redirect('dashboard')
    return render(request, 'business_profiles/details.html', {
        'title':dict(SectorProfile.Sector.choices)[sector]+' business details',
        'business_form':business_form, 'profile_forms':profile_forms, 'editing':bool(profile), 'active':'profile',
    })
