"""Default automated tests must never connect to the configured application database."""
from .settings import *  # noqa: F403

DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:',
                         'OPTIONS': {'transaction_mode': 'IMMEDIATE'}}}
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
