import io
import os
from concurrent.futures import ThreadPoolExecutor
from unittest import skipUnless
from unittest.mock import patch

from django.core.management import call_command, CommandError
from django.db import connection, close_old_connections, DatabaseError
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.test import TransactionTestCase

from .management.commands.apply_ussd_schema import TARGET


@skipUnless(connection.vendor == 'postgresql', 'Release DDL/lock tests require disposable PostgreSQL')
class ReleaseSchemaTests(TransactionTestCase):
    def setUp(self):
        self.restore_targets = MigrationExecutor(connection).loader.graph.leaf_nodes()
        self.environment = patch.dict(os.environ, {'VERCEL': '1', 'VERCEL_ENV': 'production'})
        self.environment.start(); self.addCleanup(self.environment.stop)

    def tearDown(self):
        MigrationExecutor(connection).migrate(self.restore_targets)
        super().tearDown()

    def unapplied(self):
        # Only the test database is reversed; the production command never performs a backwards plan.
        self.assertTrue(connection.settings_dict['NAME'].startswith('test_'))
        MigrationExecutor(connection).migrate([('business_profiles', '0002_ussdregistration')])

    def run_release(self):
        close_old_connections()
        try:
            output = io.StringIO(); call_command('apply_ussd_schema', stdout=output); return output.getvalue()
        finally:
            close_old_connections()

    def test_first_apply_creates_schema_and_repeat_is_noop(self):
        self.unapplied()
        output=io.StringIO(); call_command('apply_ussd_schema', stdout=output)
        self.assertIn('USSD release schema applied', output.getvalue())
        self.assertIn('business_profiles_ussdtransaction', connection.introspection.table_names())
        with patch('business_profiles.management.commands.apply_ussd_schema.call_command') as migrate:
            call_command('apply_ussd_schema', stdout=io.StringIO()); migrate.assert_not_called()
        self.assertTrue(MigrationRecorder(connection).migration_qs.filter(app=TARGET[0],name=TARGET[1]).exists())

    def test_only_known_additive_prerequisites_are_applied_for_an_older_website(self):
        self.assertTrue(connection.settings_dict['NAME'].startswith('test_'))
        MigrationExecutor(connection).migrate([('books', '0002_document_business_snapshot_document_contact_snapshot_and_more')])
        call_command('apply_ussd_schema',stdout=io.StringIO())
        tables=connection.introspection.table_names()
        self.assertIn('books_recordproposal',tables)
        self.assertIn('business_profiles_ussdregistration',tables)
        self.assertIn('business_profiles_ussdtransaction',tables)

    def test_concurrent_production_builds_apply_exactly_once(self):
        self.unapplied()
        with ThreadPoolExecutor(max_workers=2) as pool:
            outputs=list(pool.map(lambda _:self.run_release(),range(2)))
        self.assertEqual(sum('already applied' in output for output in outputs),1)
        self.assertEqual(MigrationRecorder(connection).migration_qs.filter(app=TARGET[0],name=TARGET[1]).count(),1)

    def test_failure_rolls_back_and_never_records_an_applied_release(self):
        self.unapplied()
        def interrupted(*args, **kwargs):
            with connection.cursor() as cursor:
                cursor.execute('CREATE TABLE ussd_release_rollback_probe (id integer)')
            raise DatabaseError('private connection detail')
        with patch('business_profiles.management.commands.apply_ussd_schema.call_command', side_effect=interrupted):
            with self.assertRaisesMessage(CommandError, 'this release was not published'):
                call_command('apply_ussd_schema',stdout=io.StringIO())
        self.assertFalse(MigrationRecorder(connection).migration_qs.filter(app=TARGET[0],name=TARGET[1]).exists())
        self.assertNotIn('ussd_release_rollback_probe',connection.introspection.table_names())
