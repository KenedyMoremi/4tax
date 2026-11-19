import json
from pathlib import Path
from django.core.management.base import BaseCommand
from django.test import RequestFactory
from business_profiles.registration_api import registration_options


class Command(BaseCommand):
    help = 'Export shared registration menu definitions for the Java USSD client.'

    def add_arguments(self, parser):
        parser.add_argument('--check', action='store_true')

    def handle(self, *args, **options):
        from django.conf import settings
        path = Path(settings.BASE_DIR) / 'ussd/src/main/resources/registration-schema.json'
        schema = json.loads(registration_options(RequestFactory().get('/')).content)
        content = json.dumps(schema, indent=2, ensure_ascii=False) + '\n'
        if options['check']:
            if path.read_text() != content:
                from django.core.management.base import CommandError
                raise CommandError('USSD schema is stale. Run export_registration_schema.')
        else:
            path.write_text(content)
        self.stdout.write('Registration schema is up to date.')
