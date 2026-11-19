from pathlib import Path
from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.template.loader import get_template
from django.test import SimpleTestCase
from django.urls import resolve, reverse
from .models import Business


class BookkeepingStructureTests(SimpleTestCase):
    def test_model_identity_remains_compatible_with_deployed_tables(self):
        self.assertEqual(apps.get_app_config('books').name, 'bookkeeping')
        self.assertEqual(Business._meta.db_table, 'books_business')
        self.assertEqual(get_user_model()._meta.label, 'books.User')
        self.assertEqual(get_user_model()._meta.db_table, 'books_user')
        self.assertEqual(get_user_model().__module__, 'config.auth_models')

    def test_migrations_keep_the_existing_graph_keys(self):
        loader = MigrationLoader(connection, load=False)
        loader.load_disk()
        self.assertIn(('books','0001_initial'), loader.disk_migrations)
        self.assertFalse(any(label == 'bookkeeping' for label, name in loader.disk_migrations))

    def test_bookkeeping_routes_keep_their_public_paths(self):
        self.assertEqual(reverse('dashboard'), '/')
        self.assertEqual(reverse('document_create', args=['invoice']), '/documents/invoice/new/')
        self.assertEqual(resolve('/reports/').func.__module__, 'bookkeeping.views')
        self.assertEqual(resolve('/accounts/signup/').func.__module__, 'config.authentication')

    def test_bookkeeping_assets_and_templates_are_app_owned(self):
        root = Path(__file__).resolve().parent
        template_path = Path(get_template('bookkeeping/document_form.html').origin.name)
        self.assertTrue(template_path.is_relative_to(root / 'templates'))
        self.assertEqual(Path(finders.find('bookkeeping/js/invoice.js')), root / 'static/bookkeeping/js/invoice.js')
        self.assertFalse((root / 'templates/registration').exists())
