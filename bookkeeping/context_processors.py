from .models import Business

def workspace(request):
    business = None
    if request.user.is_authenticated:
        business = Business.objects.filter(owner=request.user).first()
    return {'workspace':business}
