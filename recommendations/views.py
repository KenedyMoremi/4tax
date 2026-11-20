from django.conf import settings
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from bookkeeping.views import business_required
from agents.bookkeeping import AgentUnavailable
from agents.recommendations import recommend
from .context import snapshot
from .forms import RecommendationForm


@never_cache
@business_required
@require_http_methods(['GET', 'POST'])
def overview(request):
    context = snapshot(request.business)
    form = RecommendationForm(request.POST if request.method == 'POST' else None)
    plan = None
    if request.method == 'POST' and form.is_valid():
        if int(context['metrics']['entries']['value']) == 0:
            form.add_error(None, 'Record your recent sales and expenses first so the agent can base its recommendations on your business activity.')
        else:
            try:
                plan = recommend(context)
            except AgentUnavailable:
                form.add_error(None, 'Recommendations are unavailable right now. Your records have not changed. Please try again later.')
    if plan:
        plan = plan | {'recommendations': [
            item | {'evidence': [context['metrics'][key] for key in item['evidence_keys']]}
            for item in plan['recommendations']
        ]}
    return render(request, 'recommendations/overview.html', {
        'active': 'recommendations', 'form': form, 'plan': plan, 'snapshot': context,
        'metrics': context['metrics'].values(), 'configured': bool(settings.GROQ_RECOMMENDATIONS_API_KEY),
    })
