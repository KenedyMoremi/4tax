from django.urls import path
from . import views

app_name = 'bookings'
urlpatterns = [
    path('book/',views.directory,name='directory'),
    path('bookings/',views.dashboard,name='dashboard'),
    path('bookings/settings/',views.settings,name='settings'),
    path('bookings/new/',views.new,name='new'),
    path('bookings/catalog/<str:kind>/',views.catalog,name='catalog'),
    path('bookings/catalog/<str:kind>/<int:pk>/',views.catalog,name='catalog_edit'),
    path('bookings/appointments/<int:pk>/',views.detail,name='detail'),
    path('bookings/appointments/<int:pk>/status/',views.status,name='status'),
    path('bookings/appointments/<int:pk>/reschedule/',views.reschedule,name='reschedule'),
    path('book/<uuid:public_id>/',views.public,name='public'),
    path('book/confirmation/<uuid:token>/',views.receipt,name='receipt'),
]
