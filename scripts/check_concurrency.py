"""Exercise simultaneous payments against a disposable, file-backed SQLite database."""
import os
import sys
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from threading import Barrier

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
with tempfile.TemporaryDirectory(prefix='khumo-concurrency-') as temporary:
    os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
    os.environ['DATABASE_URL'] = ''  # Never use the application's remote database.
    os.environ['DJANGO_DB_PATH'] = str(Path(temporary) / 'test.sqlite3')
    os.environ['DJANGO_DEBUG'] = '1'
    import django
    django.setup()
    from django.contrib.auth import get_user_model
    from django.core.exceptions import ValidationError
    from django.core.management import call_command
    from django.db import connections
    from django.utils import timezone
    from books import services
    from books.models import Account, Contact, Document, Payment

    call_command('migrate', verbosity=0)
    owner = get_user_model().objects.create_user(username='concurrency-test')
    business = services.setup_business(owner=owner, name='Disposable concurrency test')
    contact = Contact.objects.create(business=business, name='Test customer')
    today = timezone.localdate()
    document = services.create_document(business=business,user=owner,kind='invoice',data={'contact':contact,'issue_date':today,'due_date':today,'notes':''},lines=[{'description':'Test','quantity':Decimal('1'),'unit_price':Decimal('100'),'tax_rate':Decimal('0')}])
    services.post_document(document=document,user=owner)
    account = Account.objects.get(business=business,code='1010')
    barrier = Barrier(2)

    def pay():
        try:
            barrier.wait(timeout=10)
            services.record_payment(document=document,user=owner,account=account,amount=Decimal('100'),date=today,reference='Concurrent payment test',token=uuid.uuid4())
            return 'accepted'
        except ValidationError:
            return 'rejected'
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: pay(), range(2)))
    document.refresh_from_db()
    assert sorted(results) == ['accepted','rejected'], results
    assert document.paid == Decimal('100')
    assert Payment.objects.count() == 1
    connections.close_all()
    print('Concurrent payments: one accepted, one rejected; no overpayment or duplicate ledger posting.')
