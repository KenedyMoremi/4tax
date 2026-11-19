"""Existing shared signup behavior; no separate authentication service."""
from django import forms
from django.contrib.auth import get_user_model, login
from django.contrib.auth.forms import UserCreationForm
from django.shortcuts import redirect, render


class SignUpForm(UserCreationForm):
    email = forms.EmailField()
    class Meta:
        model = get_user_model()
        fields = ['first_name','last_name','username','email']

def signup(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    form = SignUpForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect('onboarding')
    return render(request, 'registration/signup.html', {'form':form})


