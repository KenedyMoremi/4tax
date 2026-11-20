from django.urls import path
from . import views, import_views

app_name='pos'
urlpatterns=[
    path('pos/inventory/',import_views.inventory,name='inventory'),
    path('pos/import/',import_views.upload,name='import_upload'),
    path('pos/import/<uuid:pk>/',import_views.review,name='import_review'),
    path('pos/',views.terminal,name='terminal'),
    path('pos/products/',views.products,name='products'),
    path('pos/products/<int:pk>/',views.products,name='product_edit'),
    path('pos/products/<int:pk>/stock/',views.stock,name='stock'),
    path('pos/sales/',views.sales,name='sales'),
    path('pos/sales/<int:pk>/',views.receipt,name='receipt'),
    path('pos/sales/<int:pk>/refund/',views.refund,name='refund'),
]
