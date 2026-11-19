from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from bookkeeping.models import Business, Account, JournalEntry
from bookkeeping.services import setup_business
from .models import SectorProfile
from .forms import SECTORS


class ProfileTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='profile-owner', password='Fresh-password-5261')
        self.other = get_user_model().objects.create_user(username='other-profile-owner', password='Fresh-password-5261')
        self.client.force_login(self.user)

    def payload(self, sector):
        common = {'business-name':'Test business', 'business-district':'Maseru', 'business-default_tax_rate':'0', 'identity-owner_full_name':'Test Owner', 'identity-owner_id_number':'0000123456','identity-version':'0'}
        hours = {'working_days':['Monday','Friday'], 'opens_at':'08:00','closes_at':'17:00'}
        staff = {'name':'Test Employee','salary_range':'1000_9999'}
        base = {'location':'Maseru', 'turnover_range':'1000_9999'}
        samples = {
            'transport': (base | hours | {'business_type':'taxi','vin':'TESTVIN','license_plate':'TEST001'}, {
                'routes':[{'origin':'Maseru','destination':'Roma','price':'25.50'}], 'employees':[staff]}),
            'services': (base | hours | {'service_type':'salon','service_price_range':'100_499'}, {'employees':[staff]}),
            'ecommerce': (base | {'service_type':'shein_runner','purchase_price_range':'100_499','selling_price_range':'500_999','shipping_price_range':'100_499'}, {'employees':[staff]}),
            'retail': (base | {'goods_type':'clothing','purchase_price_range':'100_499','selling_price_range':'500_999'}, {'employees':[staff]}),
            'agriculture': (base | {'activity':'livestock','selling_price_range':'1000_9999','farmland_count':'1','farmland_size':'1.25','farmland_unit':'hectares'}, {
                'livestock':[{'animal_type':'Sheep','number':'5'}], 'employees':[staff]}),
        }
        main, rows = samples[sector]
        common.update({'details-'+k:v for k,v in main.items()})
        for prefix, _, _, _ in SECTORS[sector][1]:
            values = rows[prefix]
            common.update({prefix+'-TOTAL_FORMS':str(len(values)),prefix+'-INITIAL_FORMS':'0',prefix+'-MIN_NUM_FORMS':'0',prefix+'-MAX_NUM_FORMS':'50'})
            for index, row in enumerate(values):
                common.update({f'{prefix}-{index}-{k}':v for k,v in row.items()})
        return common

    def submit(self, sector, data=None):
        return self.client.post(reverse('sector_details',args=[sector]), data or self.payload(sector))

    def test_signup_only_requires_username_password_and_sector_next(self):
        self.client.logout()
        response = self.client.post(reverse('signup'), {'username':'simple-owner','password1':'Fresh-password-5261','password2':'Fresh-password-5261'})
        self.assertRedirects(response, reverse('onboarding'))
        user = get_user_model().objects.get(username='simple-owner')
        self.assertFalse(Business.objects.filter(owner=user).exists())
        self.assertNotContains(self.client.get(reverse('onboarding')), 'owner_id_number')

    def test_all_sectors_save_typed_details_and_chart_without_ledger_entries(self):
        for sector in SECTORS:
            with self.subTest(sector=sector):
                user = get_user_model().objects.create_user(username='sector-'+sector)
                self.client.force_login(user)
                response = self.submit(sector)
                self.assertEqual(response.status_code,302, str(response.context['profile_forms'].main.errors) if response.status_code!=302 else '')
                profile = SectorProfile.objects.get(business__owner=user)
                self.assertEqual(profile.sector,sector)
                self.assertEqual(profile.owner_id_number,'0000123456')
                self.assertEqual(Account.objects.filter(business=profile.business).count(),17)
                self.assertFalse(JournalEntry.objects.filter(business=profile.business).exists())
                self.assertContains(self.client.get(reverse('sector_details',args=[sector])),'0000123456')
                self.assertEqual(profile.details['owner_full_name'], 'Test Owner')
                self.assertEqual(profile.details['employees'][0]['salary_range'], '1000_9999')

    def test_each_page_has_only_its_sector_fields(self):
        for sector in SECTORS:
            response = self.client.get(reverse('sector_details',args=[sector]))
            self.assertEqual(response.status_code,200)
            for prefix,_,_,_ in SECTORS[sector][1]:
                self.assertContains(response, f'name="{prefix}-TOTAL_FORMS"')
        self.assertNotContains(self.client.get(reverse('sector_details',args=['retail'])),'name="vehicles-TOTAL_FORMS"')
        self.assertEqual(self.client.get(reverse('sector_details',args=['invented'])).status_code,404)
        self.assertEqual(self.client.post(reverse('onboarding'),{'sector':'invented'}).status_code,200)

    def test_missing_management_data_and_negative_prices_do_not_create_business(self):
        data = self.payload('retail');data['details-selling_price_range']='-1'
        response=self.submit('retail',data)
        self.assertEqual(response.status_code,200)
        self.assertFalse(Business.objects.filter(owner=self.user).exists())
        data=self.payload('transport');del data['routes-TOTAL_FORMS']
        self.assertEqual(self.submit('transport',data).status_code,200)
        self.assertFalse(Business.objects.filter(owner=self.user).exists())

    def test_ranges_hours_and_required_vehicle_fields_are_validated(self):
        cases=[('services',{'employees-0-salary_range':'50000_plus'}),('transport',{'details-closes_at':'07:00'}),('transport',{'details-vin':''}),('transport',{'details-license_plate':''}),('retail',{'details-turnover_range':'123'})]
        for sector, changes in cases:
            with self.subTest(changes=changes):
                self.assertEqual(self.submit(sector,self.payload(sector)|changes).status_code,200)
        self.assertFalse(Business.objects.filter(owner=self.user).exists())
        data=self.payload('transport')|{'details-closes_at':'05:00','details-opens_at':'20:00','details-overnight':'on'}
        self.assertEqual(self.submit('transport',data).status_code,302)

    def test_agriculture_requires_land_and_animals_only_when_applicable(self):
        data=self.payload('agriculture')|{'details-activity':'farming','details-farmland_count':'0'}
        self.assertEqual(self.submit('agriculture',data).status_code,200)
        data=self.payload('agriculture')|{'livestock-0-DELETE':'on'}
        self.assertEqual(self.submit('agriculture',data).status_code,200)
        data=self.payload('agriculture')|{'details-activity':'farming','livestock-0-DELETE':'on'}
        self.assertEqual(self.submit('agriculture',data).status_code,302)
        self.assertEqual(SectorProfile.objects.get().details['livestock'],[])

    def test_zero_employees_and_multiple_named_employees(self):
        data=self.payload('services')|{'employees-0-DELETE':'on'}
        self.assertEqual(self.submit('services',data).status_code,302)
        self.assertEqual(SectorProfile.objects.get().details['employees'],[])
        self.client.force_login(self.other)
        data=self.payload('transport')|{'employees-TOTAL_FORMS':'2','employees-1-name':'Second Employee','employees-1-salary_range':'20000_plus'}
        self.assertEqual(self.submit('transport',data).status_code,302)
        self.assertEqual(len(SectorProfile.objects.get(business__owner=self.other).details['employees']),2)

    def test_repeat_submission_and_stale_edit_cannot_overwrite(self):
        data=self.payload('retail')
        self.assertEqual(self.submit('retail',data).status_code,302)
        self.assertContains(self.submit('retail',data),'saved in another tab')
        data['identity-version']='1';data['business-name']='Updated shop'
        self.assertEqual(self.submit('retail',data).status_code,302)
        data['business-name']='Stale shop'
        self.assertContains(self.submit('retail',data),'saved in another tab')
        self.assertEqual(Business.objects.get(owner=self.user).name,'Updated shop')
        self.assertEqual(SectorProfile.objects.count(),1)
        self.assertEqual(Account.objects.filter(business__owner=self.user).count(),17)

    def test_owner_scope_and_sector_switch_cannot_overwrite_existing_profile(self):
        self.submit('retail')
        profile=SectorProfile.objects.get()
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(reverse('sector_details',args=['retail'])),'0000123456')
        data=self.payload('retail')|{'business-owner':str(self.user.pk),'business-id':str(profile.business_id)}
        self.assertEqual(self.submit('retail',data).status_code,302)
        self.assertEqual(SectorProfile.objects.count(),2)
        self.client.force_login(self.user)
        self.assertRedirects(self.submit('transport'),reverse('sector_details',args=['retail']))
        profile.refresh_from_db();self.assertEqual(profile.sector,'retail')

    def test_existing_business_preserves_chart_and_can_add_profile(self):
        business=setup_business(owner=self.user,name='Existing shop')
        ids=list(business.account_set.values_list('pk',flat=True))
        self.assertContains(self.client.get('/'),'Complete business profile')
        self.assertEqual(self.submit('retail').status_code,302)
        self.assertEqual(list(business.account_set.values_list('pk',flat=True)),ids)
        self.assertNotContains(self.client.get('/'),'Complete business profile')

    def test_csrf_authentication_and_private_response(self):
        csrf=Client(enforce_csrf_checks=True);csrf.force_login(self.user)
        self.assertEqual(csrf.post(reverse('sector_details',args=['retail']),self.payload('retail')).status_code,403)
        self.assertIn('no-store',self.client.get(reverse('sector_details',args=['retail'])).headers['Cache-Control'])
        self.client.logout()
        self.assertEqual(self.client.get(reverse('onboarding')).status_code,302)
        self.assertEqual(self.submit('retail').status_code,302)
        self.assertFalse(SectorProfile.objects.exists())

    def test_atomic_setup_rolls_back_when_profile_save_fails(self):
        with patch('business_profiles.models.SectorProfile.save',side_effect=ValidationError('Simulated failure')):
            self.assertContains(self.submit('retail'),'Simulated failure')
        self.assertFalse(Business.objects.filter(owner=self.user).exists())
        self.assertFalse(Account.objects.filter(business__owner=self.user).exists())

    def test_formset_maximum_and_required_rows_cannot_be_bypassed(self):
        for changes in [{'employees-TOTAL_FORMS':'1000000'}, {'employees-0-name':''}]:
            self.assertEqual(self.submit('retail',self.payload('retail')|changes).status_code,200)
        self.assertFalse(SectorProfile.objects.exists())

    def test_legacy_profile_details_survive_upgrade(self):
        business = setup_business(owner=self.user, name='Existing business')
        old = {'details': {'employee_count': 2}, 'stock': [{'name':'Old item','selling_price':'40.75'}]}
        profile = SectorProfile.objects.create(business=business, sector='retail', owner_id_number='0000123456', details=old)
        response = self.submit('retail', self.payload('retail') | {'identity-version':'1'})
        self.assertEqual(response.status_code, 302)
        profile.refresh_from_db()
        self.assertEqual(profile.details['previous_registration_details'], old)
        self.assertEqual(profile.details['schema_version'], 2)
