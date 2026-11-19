from django.urls import path
from . import views

app_name='pos'
urlpatterns=[
    path('pos/',views.terminal,name='terminal'),
    path('pos/products/',views.products,name='products'),
    path('pos/products/<int:pk>/',views.products,name='product_edit'),
    path('pos/products/<int:pk>/stock/',views.stock,name='stock'),
    path('pos/sales/',views.sales,name='sales'),
    path('pos/sales/<int:pk>/',views.receipt,name='receipt'),
    path('pos/sales/<int:pk>/refund/',views.refund,name='refund'),
]
