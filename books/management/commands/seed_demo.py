"""Create a separate, fictional business with balanced sample books."""
import os
import uuid
from datetime import timedelta
from decimal import Decimal
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from books import services
from books.models import Account, Contact

class Command(BaseCommand):
    help = 'Create a fictional demo workspace (development only). Set DEMO_PASSWORD or use changepassword after creation.'

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError('Demo data is disabled when DEBUG is false.')
        User = get_user_model()
        if User.objects.filter(username='demo').exists():
            self.stdout.write('Demo workspace already exists; no data changed.')
            return
        password = os.environ.get('DEMO_PASSWORD')
        user = User.objects.create_user(username='demo', email='lerato@example.invalid', first_name='Lerato', last_name='Mokoena', password=password)
        business = services.setup_business(owner=user, name='Lerato Creative Studio', district='Maseru', address='Demo workspace · Maseru', email='studio@example.invalid', vat_registered=False)
        accounts = {a.code:a for a in Account.objects.filter(business=business)}
        customers = [Contact.objects.create(business=business,name=name,email=f'customer{i}@example.invalid') for i,name in enumerate(['Maluti Mountain Lodge (demo)','Thaba Design Co. (demo)','Maseru Coffee House (demo)','Leribe Craft Collective (demo)','Berea Guest House (demo)'])]
        supplier = Contact.objects.create(business=business,name='Office Supplies (demo)',kind='supplier',email='supplier@example.invalid')
        today = timezone.localdate()
        start = today.replace(day=1)
        months = [start]
        for _ in range(5):
            months.append((months[-1]-timedelta(days=1)).replace(day=1))
        services.record_transfer(business=business,user=user,debit_account=accounts['1010'],credit_account=accounts['3000'],amount=Decimal('15000'),date=months[-1],description='Opening owner contribution',token=uuid.uuid4())
        for index, month in enumerate(reversed(months)):
            for j in range(3):
                date = min(month+timedelta(days=3+j*5),today)
                amount = Decimal(2200+index*480+j*350)
                doc = services.create_document(business=business,user=user,kind='invoice',data={'contact':customers[(index+j)%len(customers)],'issue_date':date,'due_date':date+timedelta(days=14),'notes':'Fictional sample document. Thank you for supporting local business.'},lines=[{'description':['Brand identity & design','Monthly social media package','Website design'][j],'quantity':Decimal('1'),'unit_price':amount,'tax_rate':Decimal('0')}])
                services.post_document(document=doc,user=user)
                if index < 5 or j == 0:
                    services.record_payment(document=doc,user=user,account=accounts[['1010','1020','1030'][j]],amount=amount,date=min(date+timedelta(days=2),today),reference='Demo receipt',token=uuid.uuid4())
                elif j == 1:
                    services.record_payment(document=doc,user=user,account=accounts['1010'],amount=Decimal('1500'),date=today,reference='Demo deposit',token=uuid.uuid4())
            for code, amount, label in [('5100','1800','Studio rent'),('5200','450','Local deliveries'),('5400','650','Office supplies')]:
                services.record_expense(business=business,user=user,data={'description':label,'supplier':supplier,'date':min(month+timedelta(days=5),today),'category':accounts[code],'paid_from':accounts['1010'],'amount':Decimal(amount)+Decimal(index*25),'tax_rate':Decimal('0'),'token':uuid.uuid4()})
        # An overdue invoice and an unpaid supplier bill make follow-up workflows visible.
        overdue_date = today-timedelta(days=24)
        doc = services.create_document(business=business,user=user,kind='invoice',data={'contact':customers[0],'issue_date':overdue_date,'due_date':today-timedelta(days=10),'notes':'Fictional overdue sample.'},lines=[{'description':'Photography package','quantity':Decimal('1'),'unit_price':Decimal('2800'),'tax_rate':Decimal('0')}])
        services.post_document(document=doc,user=user)
        bill = services.create_document(business=business,user=user,kind='bill',data={'contact':supplier,'issue_date':today,'due_date':today+timedelta(days=15),'notes':'Fictional supplier bill.'},lines=[{'description':'Printing & production','quantity':Decimal('1'),'unit_price':Decimal('1250'),'tax_rate':Decimal('0')}])
        services.post_document(document=bill,user=user)
        self.stdout.write(self.style.SUCCESS('Demo workspace created. Username: demo'))
        if not os.environ.get('DEMO_PASSWORD'):
            self.stdout.write('Set a password with: python manage.py changepassword demo')
        else:
            self.stdout.write('Password: the value supplied in DEMO_PASSWORD.')
