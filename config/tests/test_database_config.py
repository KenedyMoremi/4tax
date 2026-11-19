from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase
from config.database import database_config

class DatabaseConfigTests(SimpleTestCase):
    def test_sqlite_fallback(self):
        config = database_config('', '/tmp/local.sqlite3')
        self.assertEqual(config['ENGINE'], 'django.db.backends.sqlite3')
        self.assertEqual(config['OPTIONS']['transaction_mode'], 'IMMEDIATE')

    def test_postgres_url_preserves_security_and_encoded_password(self):
        config = database_config('postgresql://owner:example%40password@db.example.invalid/books?sslmode=require&channel_binding=require', '')
        self.assertEqual(config['PASSWORD'], 'example@password')
        self.assertEqual(config['NAME'], 'books')
        self.assertEqual(config['OPTIONS']['sslmode'], 'require')
        self.assertEqual(config['OPTIONS']['channel_binding'], 'require')
        self.assertTrue(config['DISABLE_SERVER_SIDE_CURSORS'])
        self.assertNotIn('transaction_mode', config['OPTIONS'])

    def test_invalid_url_does_not_expose_credentials(self):
        with self.assertRaises(ImproperlyConfigured) as error:
            database_config('postgresql://owner:private-value@host/db?invalid_option=yes', '')
        self.assertNotIn('private-value', str(error.exception))

    def test_test_runner_is_isolated_from_remote_database(self):
        from django.conf import settings
        self.assertEqual(settings.DATABASES['default']['ENGINE'], 'django.db.backends.sqlite3')
