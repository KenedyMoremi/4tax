"""Existing shared signup behavior; no separate authentication service."""
from django.contrib.auth import get_user_model, login
from django.contrib.auth.forms import UserCreationForm
from django.shortcuts import redirect, render
from django.views.decorators.debug import sensitive_post_parameters


class SignUpForm(UserCreationForm):
    password2 = None

    def validate_password_for_user(self, user, password_field_name="password1"):
        # Django normally validates password2; validate the single input instead.
        super().validate_password_for_user(user, password_field_name)

    class Meta:
        model = get_user_model()
        fields = ['username']

@sensitive_post_parameters('password1', 'password2')
def signup(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    form = SignUpForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect('onboarding')
    return render(request, 'registration/signup.html', {'form':form})


