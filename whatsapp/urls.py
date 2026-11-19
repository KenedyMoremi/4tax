from django.urls import path
from . import views
urlpatterns = [path('whatsapp/', views.setup, name='whatsapp_setup'), path('webhooks/twilio/whatsapp/', views.webhook, name='twilio_whatsapp')]
