# Installable apps

The main HTTPS site, https://4tax.vercel.app, installs as **4Tax** and includes
bookkeeping, web registration, bookings and POS. The independently hosted emulator
at https://4tax-ussd-emulator.vercel.app installs as **4Tax USSD**. Each origin has
its own manifest and root-scoped service worker. Auth and USSD are backend APIs;
they do not need separate app installations.

Use **Install app** at the bottom of the page or the browser's install menu.
On iPhone/iPad use Share → Add to Home Screen. On supported macOS Safari versions,
use File → Add to Dock. Installed apps open in standalone windows and use the
existing authentication and permissions.

An internet connection is required for all business operations. The worker caches
only a public, self-contained reconnect screen. It never stores business pages,
API results, credentials or POST requests, and never queues/replays writes.
If a save loses its response, check the record after reconnecting before retrying.
Existing POS retry protection remains unchanged. The emulator key remains in tab
memory and must be re-entered after reload.

Workers update using normal browser lifecycle rules; no forced activation or
automatic reload interrupts open forms. Close all app tabs/windows and reopen to
activate a waiting update. The worker script is registered with updateViaCache:
none. Increment the offline cache version when changing the fallback page.
Only caches owned by this worker are cleaned up.

The shared Django layouts include installation metadata for login, owner screens
and public bookings. The Django worker is served at /sw.js with no-cache and
Service-Worker-Allowed: /. Other PWA assets are public static files. The emulator
ships its own asset copies so its build remains independent.

Validation:
- python manage.py test config.tests.test_pwa
- node --test scripts/test_pwa.cjs
- Chrome manifest/installability and offline cache checks on an isolated server.

No database migrations, new dependencies or secrets are required.
