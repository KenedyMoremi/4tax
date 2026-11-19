"""Apply the approved additive USSD release schema inside the production Vercel build."""
import os

from django.core.management import BaseCommand, CommandError, call_command
from django.db import connection, transaction, DatabaseError
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder

TARGET = ('business_profiles', '0003_ussd_transactions')
# The website may not yet have enabled its existing AI-proposal feature.
ALLOWED = {TARGET, ('books', '0003_recordproposal'),
           ('business_profiles', '0001_initial'), ('business_profiles', '0002_ussdregistration')}
LOCK_ID = 47003930120261119


class Command(BaseCommand):
    help = 'Apply only the approved USSD schema in a production Vercel build; never previews.'

    def handle(self, *args, **options):
        if os.environ.get('VERCEL') != '1' or os.environ.get('VERCEL_ENV') != 'production':
            raise CommandError('USSD release migration requires a production Vercel build.')
        if connection.vendor != 'postgresql':
            raise CommandError('USSD release migration requires the configured PostgreSQL database.')
        try:
            # Transaction-scoped locks also work through Neon's transaction pooler. DDL and
            # migration-history writes commit together; concurrent builds recheck after locking.
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL lock_timeout = '60s'")
                    cursor.execute("SELECT pg_advisory_xact_lock(%s)", [LOCK_ID])
                if MigrationRecorder(connection).migration_qs.filter(app=TARGET[0], name=TARGET[1]).exists():
                    self.stdout.write('USSD release schema already applied; no changes.')
                    return
                executor = MigrationExecutor(connection)
                executor.loader.check_consistent_history(connection)
                plan = executor.migration_plan([TARGET])
                if any(backwards or (migration.app_label, migration.name) not in ALLOWED for migration, backwards in plan):
                    raise CommandError('Unrelated unapplied migrations require the normal database rollout; release stopped.')
                self.stdout.write('Applying approved USSD release schema:')
                for migration, _ in plan:
                    self.stdout.write(f'  {migration.app_label}.{migration.name}')
                call_command('migrate', TARGET[0], TARGET[1], interactive=False, verbosity=1, stdout=self.stdout)
        except DatabaseError:
            # Do not print connection strings, driver internals or provider configuration into build logs.
            raise CommandError('USSD schema migration failed; this release was not published.') from None
        self.stdout.write(self.style.SUCCESS('USSD release schema applied.'))
