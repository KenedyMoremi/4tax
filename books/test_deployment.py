import importlib.util
import os
from pathlib import Path
from unittest.mock import patch
from django.core.exceptions import ImproperlyConfigured
from django.test import Client, SimpleTestCase, override_settings


class VercelSettingsTests(SimpleTestCase):
    def load_settings(self, **overrides):
        environment = {
            'VERCEL': '1',
            'VERCEL_URL': 'khumo-preview.example.vercel.app',
            'VERCEL_PROJECT_PRODUCTION_URL': 'khumo.example.vercel.app',
            'DJANGO_SECRET_KEY': 'test-only-' + 'x' * 60,
            'DATABASE_URL': 'postgresql://test:test@db.example.invalid/test?sslmode=require&channel_binding=require',
        } | overrides
        spec = importlib.util.spec_from_file_location('config._deployment_test', Path(__file__).resolve().parent.parent / 'config/settings.py')
        module = importlib.util.module_from_spec(spec)
        with patch.dict(os.environ, environment, clear=True):
            spec.loader.exec_module(module)
        return module

    def test_vercel_disables_debug_and_uses_exact_hosts(self):
        config = self.load_settings(DJANGO_DEBUG='1')
        self.assertFalse(config.DEBUG)
        self.assertEqual(config.ALLOWED_HOSTS, ['khumo-preview.example.vercel.app', 'khumo.example.vercel.app'])
        self.assertEqual(config.SECURE_PROXY_SSL_HEADER, ('HTTP_X_FORWARDED_PROTO', 'https'))
        self.assertTrue(config.SESSION_COOKIE_SECURE)
        self.assertTrue(config.CSRF_COOKIE_SECURE)
        self.assertEqual(config.DATABASES['default']['ENGINE'], 'django.db.backends.postgresql')

    def test_vercel_requires_database_not_local_env_fallback(self):
        with self.assertRaisesMessage(ImproperlyConfigured, 'Set DATABASE_URL'):
            self.load_settings(DATABASE_URL='')

    def test_vercel_requires_a_secret(self):
        with self.assertRaisesMessage(ImproperlyConfigured, 'Set DJANGO_SECRET_KEY'):
            self.load_settings(DJANGO_SECRET_KEY='')

    def test_custom_domains_remain_supported(self):
        config = self.load_settings(DJANGO_ALLOWED_HOSTS='books.example.com', DJANGO_CSRF_TRUSTED_ORIGINS='https://books.example.com')
        self.assertIn('books.example.com',config.ALLOWED_HOSTS)
        self.assertIn('https://books.example.com',config.CSRF_TRUSTED_ORIGINS)
        self.assertIn('https://khumo.example.vercel.app',config.CSRF_TRUSTED_ORIGINS)

    def test_proxy_https_login_and_csrf(self):
        config = self.load_settings()
        with override_settings(ALLOWED_HOSTS=config.ALLOWED_HOSTS, SECURE_PROXY_SSL_HEADER=config.SECURE_PROXY_SSL_HEADER, SECURE_SSL_REDIRECT=True, CSRF_TRUSTED_ORIGINS=config.CSRF_TRUSTED_ORIGINS):
            client = Client(enforce_csrf_checks=True)
            headers = {'HTTP_HOST':'khumo.example.vercel.app', 'HTTP_X_FORWARDED_PROTO':'https'}
            response = client.get('/accounts/login/',**headers)
            self.assertEqual(response.status_code,200)
            token=client.cookies['csrftoken'].value
            response=client.post('/accounts/login/',{'csrfmiddlewaretoken':token},HTTP_ORIGIN='https://khumo.example.vercel.app',**headers)
            self.assertEqual(response.status_code,200)
            response=client.post('/accounts/login/',{'csrfmiddlewaretoken':token},HTTP_ORIGIN='https://untrusted.example',**headers)
            self.assertEqual(response.status_code,403)
