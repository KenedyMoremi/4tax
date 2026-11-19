from django.contrib import admin
from .models import Business, Contact, Account, Document, DocumentLine, JournalEntry, JournalLine, Payment, Expense

from config.auth_admin import register_user_admin

register_user_admin()

class AuditAdmin(admin.ModelAdmin):
    """Financial data is viewed here; mutations go through validated application workflows."""
    def has_add_permission(self, request):
        return False
    def has_change_permission(self, request, obj=None):
        return False
    def has_delete_permission(self, request, obj=None):
        return False

for model in [Business, Contact, Account, Document, DocumentLine, JournalEntry, JournalLine, Payment, Expense]:
    admin.site.register(model, AuditAdmin)
admin.site.site_header = 'Khumo Books administration'
