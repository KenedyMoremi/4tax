from django.contrib import admin
from django.contrib.auth import views as auth
from django.urls import include, path
from . import authentication

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/login/', auth.LoginView.as_view(), name='login'),
    path('accounts/logout/', auth.LogoutView.as_view(), name='logout'),
    path('accounts/signup/', authentication.signup, name='signup'),
    path('accounts/password/', auth.PasswordChangeView.as_view(template_name='registration/password.html', success_url='/'), name='password_change'),
    path('', include('whatsapp.urls')),
    path('', include('business_profiles.urls')),
    path('', include('bookings.urls')),
    path('', include('bookkeeping.urls')),
]
