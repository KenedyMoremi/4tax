import time
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from agents.bookkeeping import provider_key
from whatsapp.worker import process_one, send_one


class Command(BaseCommand):
    help = 'Process the durable WhatsApp inbox and send replies. Run outside Vercel.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true')
        parser.add_argument('--limit', type=int, default=10)
        parser.add_argument('--poll-seconds', type=int, default=2)

    def handle(self, *args, **options):
        if not settings.WHATSAPP_ENABLED or not all([settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN, settings.TWILIO_WHATSAPP_FROM, provider_key()]):
            raise CommandError('Enable WhatsApp and configure the Twilio and AI provider environment variables first.')
        if not 1 <= options['limit'] <= 100 or not 1 <= options['poll_seconds'] <= 30:
            raise CommandError('Limit must be 1–100 and poll-seconds 1–30.')
        try:
            while True:
                processed = sent = 0
                for _ in range(options['limit']):
                    processed += bool(process_one())
                    sent += bool(send_one())
                if processed or sent or options['once']:
                    self.stdout.write(f'Processed {processed} messages; handled {sent} replies.')
                if options['once']:
                    return
                time.sleep(options['poll_seconds'])
        except KeyboardInterrupt:
            return
