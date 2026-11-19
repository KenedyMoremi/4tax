"""Existing user model, kept outside bookkeeping business logic.

Its historical books.User identity is retained to preserve deployed migrations,
foreign keys, permissions, and sessions. This does not create a new auth service.
"""
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    class Meta(AbstractUser.Meta):
        abstract = False
        app_label = 'books'
