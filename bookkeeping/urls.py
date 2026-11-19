from django.urls import path
from . import views, agent_views

urlpatterns = [
    path('agent/records/', agent_views.records, name='agent_records'),
    path('setup/', views.onboarding, name='onboarding'),
    path('', views.dashboard, name='dashboard'),
    path('documents/<str:kind>/', views.documents, name='documents'),
    path('documents/<str:kind>/new/', views.document_create, name='document_create'),
    path('document/<int:pk>/', views.document_detail, name='document_detail'),
    path('document/<int:pk>/edit/', views.document_edit, name='document_edit'),
    path('document/<int:pk>/payment/', views.payment_create, name='payment_create'),
    path('document/<int:pk>/<str:action>/', views.document_action, name='document_action'),
    path('payments/<int:pk>/reverse/', views.payment_reverse, name='payment_reverse'),
    path('contacts/', views.contacts, name='contacts'),
    path('contacts/new/', views.contact_edit, name='contact_create'),
    path('contacts/<int:pk>/edit/', views.contact_edit, name='contact_edit'),
    path('expenses/', views.expenses, name='expenses'),
    path('expenses/new/', views.expense_create, name='expense_create'),
    path('expenses/<int:pk>/void/', views.expense_void, name='expense_void'),
    path('ledger/', views.ledger, name='ledger'),
    path('ledger/<int:pk>/reverse/', views.journal_reverse, name='journal_reverse'),
    path('ledger/new/', views.transfer_create, name='transfer_create'),
    path('reports/', views.reports, name='reports'),
    path('accounts/', views.accounts, name='accounts'),
    path('settings/', views.settings_view, name='settings'),
]
