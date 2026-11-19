from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.http import require_GET


@require_GET
def service_worker(request):
    # Serve at the origin root so all business modules share one installation.
    source = (Path(settings.BASE_DIR) / 'static/pwa/sw.js').read_text()
    response = HttpResponse(source, content_type='application/javascript')
    response['Cache-Control'] = 'no-cache'
    response['Service-Worker-Allowed'] = '/'
    return response
