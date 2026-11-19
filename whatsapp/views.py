from datetime import timedelta
from django import forms
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse
from bookkeeping.models import Business
from agents.bookkeeping import provider_name
from bookkeeping.views import business_required
from .linking import LinkForm, change_link
from .models import WhatsAppLink, InboundMessage


def twiml(body=None):
    response = MessagingResponse()
    if body:
        response.message(body)
    return HttpResponse(str(response), content_type='text/xml')


class WebhookForm(forms.Form):
    MessageSid = forms.RegexField(r'^(SM|MM)[a-fA-F0-9]{32}$')
    From = forms.RegexField(r'^whatsapp:\+[1-9][0-9]{7,14}$')
    Body = forms.CharField(max_length=4000, required=False)
    NumMedia = forms.IntegerField(min_value=0, max_value=10)


@csrf_exempt
@require_POST
def webhook(request):
    if request.content_type == 'application/json' or request.headers.get('Authorization', '').lower().startswith('bearer '):
        from business_profiles.transactions import ussd_webhook
        response = ussd_webhook(request)
        response['Cache-Control'] = 'no-store'
        return response
    if not settings.WHATSAPP_ENABLED or not all([settings.TWILIO_AUTH_TOKEN, settings.TWILIO_ACCOUNT_SID, settings.TWILIO_WHATSAPP_FROM, settings.TWILIO_WEBHOOK_URL]):
        return HttpResponse(status=503)
    if len(request.body) > 32768:
        return HttpResponse(status=413)
    if request.build_absolute_uri() != settings.TWILIO_WEBHOOK_URL:
        return HttpResponse(status=403)
    if not RequestValidator(settings.TWILIO_AUTH_TOKEN).validate(settings.TWILIO_WEBHOOK_URL, request.POST, request.headers.get('X-Twilio-Signature', '')):
        return HttpResponse(status=403)
    if request.POST.get('AccountSid') != settings.TWILIO_ACCOUNT_SID or request.POST.get('To') != settings.TWILIO_WHATSAPP_FROM:
        return HttpResponse(status=403)
    form = WebhookForm(request.POST)
    if not form.is_valid():
        return HttpResponse(status=400)
    data = form.cleaned_data
    with transaction.atomic():
        # Lock ordering is business -> link throughout callbacks, worker and web UI.
        candidate = WhatsAppLink.objects.filter(phone=data['From'][9:], active=True, owner__is_active=True).first()
        if not candidate:
            return twiml('Sign in to Khumo Books and open WhatsApp to link your number first.')
        business = Business.objects.select_for_update().get(pk=candidate.business_id)
        link = WhatsAppLink.objects.select_for_update().get(pk=candidate.pk)
        if not link.active or link.phone != data['From'][9:] or business.owner_id != link.owner_id:
            return twiml()
        if link.ai_provider != settings.BOOKKEEPING_AI_PROVIDER:
            return twiml('The AI provider has changed. Open WhatsApp settings in the app and link your number again to consent.')
        if InboundMessage.objects.filter(sid=data['MessageSid']).exists():
            return twiml()
        if InboundMessage.objects.filter(link=link, created_at__gte=timezone.now()-timedelta(hours=1)).count() >= settings.WHATSAPP_HOURLY_LIMIT:
            return twiml('The hourly message limit has been reached. Please try again later or use the app.')
        InboundMessage.objects.get_or_create(sid=data['MessageSid'], defaults=dict(link=link, generation=link.generation, body=data['Body'], media_count=data['NumMedia']))
    return twiml()


@never_cache
@business_required
def setup(request):
    code = None
    form = LinkForm(request.POST or None)
    if request.method == 'POST':
        if request.POST.get('action') == 'disconnect':
            change_link(request.business, request.user)
            messages.success(request, 'WhatsApp disconnected. Pending proposals were cancelled.')
            return redirect('whatsapp_setup')
        if form.is_valid():
            try:
                code = change_link(request.business, request.user, form.cleaned_data['phone'])
            except ValidationError as exc:
                form.add_error(None, exc)
    link = WhatsAppLink.objects.filter(business=request.business, owner=request.user).first()
    recent = InboundMessage.objects.filter(link=link).select_related('outboundmessage').order_by('-created_at')[:20] if link else []
    return render(request, 'whatsapp/setup.html', dict(ai_provider=provider_name(), provider_changed=bool(link and link.ai_provider != settings.BOOKKEEPING_AI_PROVIDER), form=form, link=link, code=code, recent=recent, enabled=settings.WHATSAPP_ENABLED, active='whatsapp', title='WhatsApp bookkeeping'))
