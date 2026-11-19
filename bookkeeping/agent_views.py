from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import render, redirect
from .agent_actions import resolve_proposal
from .models import RecordProposal
from .views import business_required, paginate


class DecisionForm(forms.Form):
    reference = forms.RegexField(r'^[A-F0-9]{12}$')
    action = forms.ChoiceField(choices=[('confirm', 'Confirm'), ('cancel', 'Cancel')])


@business_required
def records(request):
    if request.method == 'POST':
        form = DecisionForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Choose a valid proposal and action.')
        else:
            try:
                result = resolve_proposal(business=request.business, owner=request.user, reference=form.cleaned_data['reference'], confirm=form.cleaned_data['action']=='confirm')
                messages.success(request, result)
            except ValidationError as exc:
                messages.error(request, ' '.join(exc.messages))
        return redirect('agent_records')
    records = RecordProposal.objects.filter(business=request.business, owner=request.user)
    return render(request, 'bookkeeping/agent_records.html', {'records':paginate(request, records), 'title':'Agent records', 'active':'agent'})
