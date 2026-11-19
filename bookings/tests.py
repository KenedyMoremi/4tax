import uuid
from datetime import time, timedelta
from decimal import Decimal
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from bookkeeping.models import Business, JournalEntry
from business_profiles.models import SectorProfile
from .models import Calendar, Service, Staff, Appointment, ReservedSlot
from .forms import CalendarForm, AppointmentForm
from . import services


class BookingTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(username='booking-owner',password='test-pass')
        self.other = get_user_model().objects.create_user(username='other-owner',password='test-pass')
        self.business = Business.objects.create(owner=self.owner,name='Example Salon')
        self.foreign = Business.objects.create(owner=self.other,name='Other Salon')
        for business in [self.business,self.foreign]:
            SectorProfile.objects.create(business=business,sector='services',owner_id_number='000001')
        self.calendar = Calendar.objects.create(business=self.business,enabled=True)
        self.service = Service.objects.create(business=self.business,name='Haircut',duration_minutes=60,price='150.00')
        self.staff = Staff.objects.create(business=self.business,name='Example Stylist')
        self.date = timezone.localdate() + timedelta(days=1)
        while self.date.weekday() > 4:
            self.date += timedelta(days=1)
        self.url = reverse('bookings:public',args=[self.calendar.public_id])

    def payload(self, **changes):
        return {'service':str(self.service.pk),'staff':str(self.staff.pk),'date':self.date.isoformat(),
                'time':'08:00','customer_name':'Example Customer','customer_phone':'+26658000000',
                'customer_email':'','notes':'','request_key':str(uuid.uuid4())} | changes

    def book(self, **changes):
        response = self.client.post(self.url,self.payload(**changes))
        self.assertEqual(response.status_code,302,response.content.decode()[:2000])
        return Appointment.objects.latest('pk')

    def test_defaults_and_owner_pages(self):
        self.assertEqual(self.calendar.opens_at,time(8))
        self.assertEqual(self.calendar.closes_at,time(17))
        self.client.force_login(self.owner)
        for path in ['bookings:dashboard','bookings:settings','bookings:new']:
            self.assertEqual(self.client.get(reverse(path)).status_code,200)
        for kind in ['services','staff']:
            self.assertEqual(self.client.get(reverse('bookings:catalog',args=[kind])).status_code,200)
        self.assertContains(self.client.get(reverse('bookings:dashboard')),'08:00–17:00')

    def test_public_selection_and_booking_are_csrf_protected(self):
        response = self.client.get(self.url,{'service':self.service.pk,'staff':self.staff.pk,'date':self.date.isoformat()})
        self.assertContains(response,'value="08:00"')
        self.assertContains(response,'value="16:00"')
        self.assertNotContains(response,'value="16:15"')
        self.assertNotContains(response,'value="17:00"')
        csrf = Client(enforce_csrf_checks=True)
        self.assertEqual(csrf.post(self.url,self.payload()).status_code,403)
        csrf.get(self.url,{'service':self.service.pk,'staff':self.staff.pk,'date':self.date.isoformat()})
        response = csrf.post(self.url,self.payload(),HTTP_X_CSRFTOKEN=csrf.cookies['csrftoken'].value)
        self.assertEqual(response.status_code,302)
        appointment = Appointment.objects.get()
        self.assertEqual(appointment.status,'pending')
        self.assertEqual(appointment.reserved_slots.count(),4)
        self.assertFalse(JournalEntry.objects.exists())
        self.assertIn('no-store',self.client.get(response.url).headers['Cache-Control'])
        self.assertEqual(self.client.get(response.url).headers['Referrer-Policy'],'no-referrer')

    def test_overlap_rejected_but_adjacent_and_other_staff_allowed(self):
        self.book()
        for at in ['08:00','08:15','08:30','08:45']:
            response = self.client.post(self.url,self.payload(time=at))
            self.assertContains(response,'no longer available')
        self.book(time='09:00')
        colleague = Staff.objects.create(business=self.business,name='Second Stylist')
        self.book(staff=str(colleague.pk))
        self.assertEqual(Appointment.objects.count(),3)

    def test_retries_are_idempotent_and_conflicting_payload_rejected(self):
        data = self.payload()
        first = self.client.post(self.url,data)
        second = self.client.post(self.url,data)
        self.assertEqual(first.url,second.url)
        response = self.client.post(self.url,data | {'customer_name':'Changed Customer'})
        self.assertContains(response,'already used')
        self.assertEqual(Appointment.objects.count(),1)
        self.assertEqual(ReservedSlot.objects.count(),4)

    def test_closed_days_invalid_times_past_dates_and_horizon(self):
        sunday = self.date
        while sunday.weekday()!=6:
            sunday += timedelta(days=1)
        for changes in [{'time':'07:45'},{'time':'16:15'},{'time':'08:01'}, {'date':sunday.isoformat()},
                        {'date':(timezone.localdate()-timedelta(days=1)).isoformat()},
                        {'date':(timezone.localdate()+timedelta(days=91)).isoformat()}]:
            self.assertEqual(self.client.post(self.url,self.payload(**changes)).status_code,200)
        self.assertFalse(Appointment.objects.exists())

    def test_cross_tenant_services_staff_and_owner_actions(self):
        service = Service.objects.create(business=self.foreign,name='Foreign service')
        staff = Staff.objects.create(business=self.foreign,name='Foreign staff')
        for changes in [{'service':str(service.pk)}, {'staff':str(staff.pk)}]:
            self.assertEqual(self.client.post(self.url,self.payload(**changes)).status_code,200)
        self.assertFalse(Appointment.objects.exists())
        appointment = self.book()
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse('bookings:detail',args=[appointment.pk])).status_code,404)
        self.assertEqual(self.client.post(reverse('bookings:status',args=[appointment.pk]),{'status':'cancelled'}).status_code,404)
        self.assertEqual(self.client.get(reverse('bookings:reschedule',args=[appointment.pk])).status_code,404)
        self.assertEqual(self.client.get(reverse('bookings:catalog_edit',args=['services',self.service.pk])).status_code,404)

    def test_receipt_cancellation_frees_slots_and_unknown_link_is_private(self):
        appointment = self.book()
        url = reverse('bookings:receipt',args=[appointment.access_token])
        self.assertEqual(self.client.get(reverse('bookings:receipt',args=[uuid.uuid4()])).status_code,404)
        self.assertEqual(self.client.post(url).status_code,302)
        self.assertEqual(self.client.post(url).status_code,302)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status,'cancelled')
        self.assertEqual(appointment.reserved_slots.count(),0)
        self.book()

    def test_owner_confirm_complete_and_terminal_status_rules(self):
        appointment = self.book()
        self.client.force_login(self.owner)
        url = reverse('bookings:status',args=[appointment.pk])
        self.client.post(url,{'status':'confirmed'})
        appointment.refresh_from_db();self.assertEqual(appointment.status,'confirmed')
        self.client.post(url,{'status':'completed'})
        appointment.refresh_from_db();self.assertEqual(appointment.status,'confirmed')
        with patch('bookings.services.timezone.now',return_value=appointment.ends_at+timedelta(minutes=1)):
            self.client.post(url,{'status':'completed'})
        appointment.refresh_from_db();self.assertEqual(appointment.status,'completed')
        self.client.post(url,{'status':'confirmed'})
        appointment.refresh_from_db();self.assertEqual(appointment.status,'completed')

    def test_owner_booking_is_confirmed_and_prices_are_snapshots(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse('bookings:new'),self.payload())
        self.assertEqual(response.status_code,302)
        appointment = Appointment.objects.get()
        self.assertEqual(appointment.status,'confirmed')
        self.service.price=Decimal('200');self.service.name='New name';self.service.save()
        appointment.refresh_from_db()
        self.assertEqual(appointment.price,Decimal('150'))
        self.assertEqual(appointment.service_name,'Haircut')
        self.assertFalse(JournalEntry.objects.exists())

    def test_reschedule_is_atomic_conflict_safe_and_versioned(self):
        first=self.book();second=self.book(time='10:00')
        self.client.force_login(self.owner)
        url=reverse('bookings:reschedule',args=[first.pk])
        data={'service':self.service.pk,'staff':self.staff.pk,'date':self.date.isoformat(),'time':'10:00','version':1}
        self.assertContains(self.client.post(url,data),'no longer available')
        self.assertEqual(first.reserved_slots.count(),4)
        data['time']='11:00'
        self.assertEqual(self.client.post(url,data).status_code,302)
        first.refresh_from_db()
        self.assertEqual(timezone.localtime(first.starts_at).time(),time(11))
        self.assertEqual(first.reserved_slots.count(),4)
        data['time']='12:00'
        self.assertContains(self.client.post(url,data),'another tab')
        first.refresh_from_db();self.assertEqual(timezone.localtime(first.starts_at).time(),time(11))

    def test_calendar_hours_cannot_exclude_existing_appointments(self):
        self.book()
        self.client.force_login(self.owner)
        response=self.client.post(reverse('bookings:settings'),{'enabled':'on','weekdays':['0','1','2','3','4'],'opens_at':'09:00','closes_at':'17:00'})
        self.assertContains(response,'exclude an existing appointment')
        self.calendar.refresh_from_db();self.assertEqual(self.calendar.opens_at,time(8))
        for values in [('17:00','08:00'),('08:01','17:00')]:
            form=CalendarForm({'weekdays':['0'],'opens_at':values[0],'closes_at':values[1]},instance=self.calendar)
            self.assertFalse(form.is_valid())

    def test_disabled_or_non_service_business_is_not_publicly_bookable(self):
        self.calendar.enabled=False;self.calendar.save()
        self.assertEqual(self.client.get(self.url).status_code,404)
        self.assertEqual(self.client.post(self.url,self.payload()).status_code,404)
        SectorProfile.objects.filter(business=self.business).update(sector='retail')
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse('bookings:dashboard')).status_code,403)
        self.assertEqual(self.client.post(reverse('bookings:catalog',args=['services']),{'name':'Nope','duration_minutes':60,'price':0}).status_code,403)

    def test_service_and_staff_setup_and_no_get_side_effects(self):
        self.client.force_login(self.other)
        self.client.get(reverse('bookings:settings'))
        self.assertFalse(Calendar.objects.filter(business=self.foreign).exists())
        settings={'enabled':'on','weekdays':['0','1','2','3','4'],'opens_at':'08:00','closes_at':'17:00'}
        self.assertContains(self.client.post(reverse('bookings:settings'),settings),'Add at least one')
        self.assertEqual(self.client.post(reverse('bookings:catalog',args=['services']),{'name':'Consultation','duration_minutes':45,'price':'100.00','active':'on'}).status_code,302)
        self.assertEqual(self.client.post(reverse('bookings:catalog',args=['staff']),{'name':'Owner','active':'on'}).status_code,302)
        self.assertEqual(self.client.post(reverse('bookings:settings'),settings).status_code,302)
        self.assertTrue(Calendar.objects.get(business=self.foreign).enabled)

    def test_directory_search_only_exposes_published_service_businesses(self):
        url=reverse('bookings:directory')
        self.assertContains(self.client.get(url),'Example Salon')
        self.assertContains(self.client.get(url,{'q':'Haircut'}),'Example Salon')
        self.assertContains(self.client.get(url,{'q':'not-a-match'}),'No matching businesses')
        self.calendar.enabled=False;self.calendar.save()
        self.assertNotContains(self.client.get(url),'Example Salon')
        self.calendar.enabled=True;self.calendar.save()
        self.staff.active=False;self.staff.save()
        self.assertNotContains(self.client.get(url),'Example Salon')

    def test_slot_conflict_rolls_back_appointment_creation(self):
        from django.db import IntegrityError
        with patch('bookings.services.ReservedSlot.objects.bulk_create',side_effect=IntegrityError('conflict')):
            response=self.client.post(self.url,self.payload())
        self.assertContains(response,'just booked')
        self.assertFalse(Appointment.objects.exists())
        self.assertFalse(ReservedSlot.objects.exists())

    def test_inactive_catalog_invalid_durations_and_phone_are_rejected(self):
        self.service.active=False;self.service.save()
        self.assertEqual(self.client.post(self.url,self.payload()).status_code,200)
        self.assertFalse(Appointment.objects.exists())
        self.service.active=True;self.service.save()
        self.assertEqual(self.client.post(self.url,self.payload(customer_phone='--------')).status_code,200)
        self.assertFalse(Appointment.objects.exists())
        self.client.force_login(self.owner)
        for duration,price in [(17,'100'),(0,'100'),(600,'100'),(60,'-1')]:
            self.assertEqual(self.client.post(reverse('bookings:catalog',args=['services']),{'name':'Invalid','duration_minutes':duration,'price':price}).status_code,200)
        self.assertEqual(Service.objects.filter(business=self.business).count(),1)

    def test_public_cannot_cancel_after_start_and_all_future_requests_are_visible_to_owner(self):
        appointment=self.book()
        self.client.force_login(self.owner)
        response=self.client.get(reverse('bookings:dashboard'),{'view':'requests'})
        self.assertContains(response,'Example Customer')
        self.client.logout()
        with patch('bookings.services.timezone.now',return_value=appointment.starts_at+timedelta(minutes=1)):
            self.client.post(reverse('bookings:receipt',args=[appointment.access_token]))
        appointment.refresh_from_db();self.assertEqual(appointment.status,'pending')
        self.assertEqual(appointment.reserved_slots.count(),4)
