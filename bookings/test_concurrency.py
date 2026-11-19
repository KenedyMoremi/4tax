import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest import skipUnless
from django.contrib.auth import get_user_model
from django.db import connection, connections
from django.test import Client, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from bookkeeping.models import Business
from business_profiles.models import SectorProfile
from .models import Calendar, Service, Staff, Appointment, ReservedSlot


@skipUnless(connection.vendor=='postgresql','Requires an explicitly configured disposable PostgreSQL database')
class BookingConcurrencyTests(TransactionTestCase):
    def setUp(self):
        owner=get_user_model().objects.create_user(username='booking-concurrency')
        business=Business.objects.create(owner=owner,name='Test service business')
        SectorProfile.objects.create(business=business,sector='services',owner_id_number='000001')
        calendar=Calendar.objects.create(business=business,enabled=True)
        service=Service.objects.create(business=business,name='Test service',duration_minutes=60)
        staff=Staff.objects.create(business=business,name='Test provider')
        date=timezone.localdate()+timedelta(days=1)
        while date.weekday()>4:date+=timedelta(days=1)
        self.url=reverse('bookings:public',args=[calendar.public_id])
        self.data={'service':str(service.pk),'staff':str(staff.pk),'date':date.isoformat(),'time':'08:00',
                   'customer_name':'Test Customer','customer_phone':'+26658000000','customer_email':'','notes':''}

    def race(self, payloads):
        barrier=Barrier(2)
        def submit(payload):
            try:
                barrier.wait(timeout=10)
                response=Client().post(self.url,payload)
                return response.status_code,response.headers.get('Location')
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(submit,payloads))

    def test_overlapping_requests_cannot_double_book(self):
        results=self.race([self.data | {'request_key':str(uuid.uuid4())},
                           self.data | {'time':'08:30','request_key':str(uuid.uuid4())}])
        self.assertEqual(sorted(code for code,_ in results),[200,302])
        self.assertEqual(Appointment.objects.count(),1)
        self.assertEqual(ReservedSlot.objects.count(),4)

    def test_identical_retries_return_one_appointment(self):
        payload=self.data | {'request_key':str(uuid.uuid4())}
        results=self.race([payload,payload])
        self.assertEqual([code for code,_ in results],[302,302])
        self.assertEqual(results[0][1],results[1][1])
        self.assertEqual(Appointment.objects.count(),1)
        self.assertEqual(ReservedSlot.objects.count(),4)
