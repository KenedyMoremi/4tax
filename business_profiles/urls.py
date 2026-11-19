from django.urls import path
from . import views
from .registration_api import register_business, registration_options
from .transactions import transaction_health

urlpatterns = [
    path('api/v1/transactions/health', transaction_health, name='ussd_transaction_health'),
    path('api/v1/registration/options', registration_options, name='registration_options'),
    path('api/v1/registration/options/', registration_options),
    path('api/v1/businesses', register_business, name='ussd_registration'),
    path('api/v1/businesses/', register_business),
    path('setup/', views.select_sector, name='onboarding'),
    path('setup/<str:sector>/', views.details, name='sector_details'),
]
