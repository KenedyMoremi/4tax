"""Opt-in disposable PostgreSQL tests; never use the application's DATABASE_URL."""
import os
from .test_settings import *  # noqa: F403
from .database import database_config

DATABASES = {'default': database_config(os.environ['REGISTRATION_TEST_DATABASE_URL'], ':memory:')}
