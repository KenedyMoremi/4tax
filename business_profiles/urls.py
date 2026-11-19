from django.urls import path
from . import views

urlpatterns = [
    path('setup/', views.select_sector, name='onboarding'),
    path('setup/<str:sector>/', views.details, name='sector_details'),
]
