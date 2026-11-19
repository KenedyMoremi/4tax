from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse


class SinglePasswordSignupTests(TestCase):
    def test_form_has_one_password_input(self):
        response = self.client.get(reverse('signup'))
        self.assertContains(response, 'type="password"', count=1)
        self.assertContains(response, 'name="password1"')
        self.assertNotContains(response, 'name="password2"')

    def test_one_password_creates_authenticated_user(self):
        password = 'Fresh-registration-7294!'
        response = self.client.post(reverse('signup'), {'username': 'new-owner', 'password1': password})
        self.assertRedirects(response, reverse('onboarding'))
        user = get_user_model().objects.get(username='new-owner')
        self.assertTrue(user.check_password(password))
        self.assertNotEqual(user.password, password)
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

    def test_missing_and_weak_passwords_are_rejected(self):
        for password in ['', 'short', '1234567890', 'password', 'new-owner']:
            with self.subTest(password=password):
                response = self.client.post(reverse('signup'), {'username': 'new-owner', 'password1': password})
                self.assertEqual(response.status_code, 200)
                self.assertIn('password1', response.context['form'].errors)
                self.assertFalse(get_user_model().objects.filter(username='new-owner').exists())

    def test_duplicate_username_is_rejected_case_insensitively(self):
        get_user_model().objects.create_user(username='ExistingOwner')
        response = self.client.post(reverse('signup'), {'username': 'existingowner', 'password1': 'Fresh-registration-7294!'})
        self.assertIn('username', response.context['form'].errors)
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_confirmation_from_old_clients_is_not_required_or_used(self):
        response = self.client.post(reverse('signup'), {
            'username': 'old-client', 'password1': 'Fresh-registration-7294!', 'password2': 'ignored',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(get_user_model().objects.get(username='old-client').check_password('Fresh-registration-7294!'))

    def test_csrf_is_still_required(self):
        response = Client(enforce_csrf_checks=True).post(reverse('signup'), {
            'username': 'blocked', 'password1': 'Fresh-registration-7294!',
        })
        self.assertEqual(response.status_code, 403)
        self.assertFalse(get_user_model().objects.exists())
