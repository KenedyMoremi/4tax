import json
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase
from django.urls import reverse


class PwaTests(SimpleTestCase):
    def test_worker_is_public_root_scoped_and_revalidated(self):
        response = self.client.get(reverse('service_worker'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/javascript')
        self.assertEqual(response['Service-Worker-Allowed'], '/')
        self.assertEqual(response['Cache-Control'], 'no-cache')
        self.assertEqual(self.client.post(reverse('service_worker')).status_code, 405)

    def test_manifest_and_icons_cover_both_frontends(self):
        for directory, prefix in [
            ('static/pwa', '/static/pwa/'),
            ('ussd-emulator/src/main/resources/static', '/'),
        ]:
            root = Path(settings.BASE_DIR) / directory
            manifest = json.loads((root / 'manifest.webmanifest').read_text())
            self.assertEqual(manifest['scope'], '/')
            self.assertEqual(manifest['start_url'], '/')
            self.assertEqual(manifest['display'], 'standalone')
            self.assertEqual({i['sizes'] for i in manifest['icons']}, {'192x192', '512x512'})
            for icon in manifest['icons']:
                content = (root / icon['src'].removeprefix(prefix)).read_bytes()
                self.assertEqual(content[:8], b'\x89PNG\r\n\x1a\n')
