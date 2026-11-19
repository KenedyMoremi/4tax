"""Registration for the existing shared user model."""
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin


def register_user_admin():
    admin.site.register(get_user_model(), UserAdmin)
