# 4Tax

Django 5.2 + server-rendered HTML templates + locally compiled Tailwind CSS. An independent bookkeeping application for MSMEs in Lesotho, with orange and charcoal inspired by [Revenue Services Lesotho’s public branding](https://www.rsl.org.ls/). It is not affiliated with RSL and does not use the RSL logo.

## Project organization

```text
bookkeeping/
  models.py, services.py, reporting.py   # financial domain
  forms.py, views.py, urls.py            # bookkeeping request handling
  migrations/                           # existing migration history
  templates/bookkeeping/                # bookkeeping screens and navigation
  static/bookkeeping/js/invoice.js       # invoice-specific browser behavior
  templatetags/, management/, scripts/   # formatting, demo data, concurrency check
  tests.py                              # bookkeeping workflow tests
config/
  settings.py, urls.py, database.py      # shared project configuration
  auth_models.py, authentication.py      # existing shared user/signup behavior
  auth_admin.py, tests/                 # shared user admin and infrastructure tests
templates/                              # shared layout, includes, authentication pages
static/                                 # shared theme and browser utilities
```

Bookkeeping remains in `bookkeeping/`. The configurable Groq/OpenAI interpretation adapter is in `agents/`, and Twilio transport, phone linking and durable messaging are in `whatsapp/`. Independent Java services for PIN authentication, USSD registration and USSD emulation are included alongside this Django application; their contracts and startup instructions live in their respective directories.

The Python app is `bookkeeping`, while `BookkeepingConfig.label` remains **`books`**. This preserves database table names, permissions/content types, migration dependencies and the configured **`books.User`** identity. Existing migration files are unchanged. The shared user model is defined in `config/auth_models.py` and registered under that historical label when bookkeeping models load. The independent Java auth service does not migrate or replace Django identities; integrating those identity systems requires an explicit migration plan.

## Independent USSD services

Each service uses Spring Boot 4.1.2, Java 25 and its own Maven build, Compose file, environment configuration and startup scripts. There is no shared Java module or outer Compose/Maven configuration.

| Service | Purpose | Local address |
| --- | --- | --- |
| [auth](auth/README.md) | Application credentials, client-credentials JWTs and owner PIN authentication | http://localhost:9000 |
| [ussd](ussd/README.md) | Transport, Services, E-Commerce, Retail and Agriculture journeys in English and Sesotho | http://localhost:8080 |
| [ussd-emulator](ussd-emulator/README.md) | Browser handset, Vodacom test identities and callback inspection | http://localhost:8090 |

With Java 25, Maven, Docker/Compose and Python 3 available, start local USSD and the emulator from the repository directory. They use the hosted auth and registration APIs by default:

```sh
./ussd/scripts/dev-up.sh
./ussd-emulator/scripts/dev-up.sh
```

The startup scripts generate private service-local `.env` files automatically. USSD validates its application credentials against the configured auth service and obtains replacements when necessary. The real registration API is **https://4tax.vercel.app**, auth is **https://4tax-auth.vercel.app**, USSD is **https://4tax-ussd.vercel.app**, and the hosted emulator is **https://4tax-ussd-emulator.vercel.app**. The mock has been removed. See [the registration contract and rollout](docs/USSD_REGISTRATION.md). For local auth development, run `./auth/scripts/dev-up.sh` independently; the registration system must trust the same issuer used by USSD. The local emulator's gateway credential is `GATEWAY_KEY` from `ussd/.env`.

Routes and URL names remain unchanged. `config/urls.py` owns the shared authentication/admin routes and includes `bookkeeping/urls.py` for the bookkeeping routes. The folder reorganization requires no data transfer. The optional WhatsApp integration adds its own tables and a bookkeeping proposal table through new migrations.

## Run locally

Requires Python 3.12–3.14 (developed and tested on 3.14), and Node 22+ only when rebuilding CSS.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Open http://127.0.0.1:8000, create an account, and set up your business. The compiled CSS is included, so Node is not required to run Django.

Optional fictional demo workspace:

```sh
python manage.py seed_demo
python manage.py changepassword demo
```

Sign in as `demo` with the password you chose. The command creates six months of fictional books and never changes existing users or workspaces. A password can alternatively be supplied through `DEMO_PASSWORD` in the environment; credentials are never printed. Demo seeding is disabled with `DEBUG=False`.

For administration:

```sh
python manage.py createsuperuser
```

Financial records are read-only in the Django admin; use the application workflows to modify the books.

## Included workflows

- Account registration, login, logout, password changes, and one private business workspace per user.
- Business profile, ten Lesotho districts, TIN and VAT registration preferences, Maloti (LSL), and Africa/Maseru time.
- Customer and supplier records with search and pagination.
- Multi-line sales invoices and purchase bills, sequential business-specific numbers, editable drafts, posting, due dates, overdue status, configurable VAT, immutable amounts and party snapshots, and printable documents (browser Print → Save as PDF).
- Partial and full payments recorded against cash, bank, M-Pesa or EcoCash accounts. Payment reversals retain the original record. These are bookkeeping records, not payment-provider integrations.
- Paid expenses by category, supplier and payment account; reversals preserve the audit trail.
- Double-entry ledger, chart of accounts, opening cash/owner contributions, drawings, account transfers and two-sided manual journals with reversals.
- Dashboard showing monthly revenue, expenses, profit, receivables, payables, cash balances and six months of recorded cash movement.
- Date-filtered profit and loss, balance sheet, trial balance, VAT movement summary, CSV export and printable reports.
- Responsive mobile navigation, keyboard focus states, CSRF-protected writes, server validation and owner-scoped access.

## Typical workflow

1. Create your workspace and confirm VAT settings. The default is **not registered, 0%**; no statutory rate is assumed.
2. Record initial funding using **General ledger → Journal entry**: debit Bank and credit Owner's capital. For drawings, debit Owner's drawings and credit the payment account. For a transfer, debit the destination and credit the source.
3. Add customers and suppliers.
4. Create an invoice or purchase bill, review the draft, and select **Post to books**.
5. Record actual payments as they happen; partial payments leave a balance due.
6. Record already-paid purchases as expenses. Do not also enter the same purchase as a bill.
7. Review the ledger and reports. Void an unpaid incorrect document and create a replacement. Reverse an incorrect payment first if necessary; reversals do not move money or issue refunds.

## Accounting behavior

Amounts use `Decimal`, with `ROUND_HALF_UP` to cents per line and on each line's tax. Invoices debit accounts receivable and credit sales/output VAT; bills debit purchases/input VAT and credit accounts payable. Payments settle the relevant control account. Expenses debit their category/input VAT and credit the payment account.

Only posted transactions appear in reports. Drafts do not affect balances. Transactions cannot be posted in the future. Reversals are dated today so earlier periods retain their historical figures. Profit and loss is accrual-based. The balance sheet includes cumulative earnings; the trial balance uses closing net balances. The dashboard cash chart shows gross movements (including funding and internal transfers), not a statutory statement of cash flows or a bank feed.

VAT summaries show what was entered, not eligibility for recovery or a filing-ready liability. Rates and recovery treatment must be verified for the business. The app does not submit returns to RSL.

All ledger writes pass through `bookkeeping/services.py`, which validates tenant ownership and balance inside an atomic transaction. Database constraints protect source idempotency, document numbering, payment limits and positive debit/credit sides. Payments, expense submissions, posting and reversals are retry-safe. Posted data has no edit/delete interface. Application/database operators must not bypass the service layer: cross-row balanced-journal invariants cannot be expressed as a simple database check constraint.

Set `DATABASE_URL` in the environment or the ignored local `.env` to use PostgreSQL/Neon. The supplied URL’s SSL and channel-binding options are preserved. Connections use a 10-second timeout, no Django persistent connections, and no server-side cursors for compatibility with Neon’s transaction pooler. PostgreSQL writes lock the business row before reading balances. Never commit connection credentials.

Without `DATABASE_URL`, SQLite remains available using `IMMEDIATE` transactions to serialize writes. Use a single application instance and durable local disk with SQLite; do not put SQLite on a network filesystem. Use SQLite’s backup API rather than copying a database during writes. With Neon, configure provider backups and restore testing.

## Development and checks

```sh
npm ci --ignore-scripts
npm run build:css
# During template changes:
npm run watch:css

python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
python bookkeeping/scripts/check_concurrency.py
```

Tests cover posting, balancing, payment and expense retries/reversals, rounding, period reporting, snapshots, CSRF, cross-business reads/writes, form validation, authentication/onboarding, and template rendering. `python manage.py test` selects `config.test_settings`, uses a disposable SQLite database, and makes no external calls even when `.env` points to Neon. The concurrency script explicitly disables `DATABASE_URL`. Use a separate disposable PostgreSQL database for PostgreSQL integration testing; never point the test runner at the application database. A separate file-backed SQLite check verifies that concurrent full-payment attempts cannot overpay a document. CI runs Django checks, migration drift checks, tests, the concurrency check, and the Tailwind build.

## Deployment

For GitHub → Vercel deployment, see [the Vercel deployment guide](docs/VERCEL.md). The project includes the Django preset, Tailwind build, secure proxy settings and secret exclusions.

This is a Python/Django server application. Sites static/Cloudflare Worker hosting cannot run it. Deploy to a Python-capable host, using Neon/PostgreSQL or persistent local storage for SQLite; no live deployment is included.

1. Install the pinned Python requirements and a supported WSGI process server for your hosting platform. Serve `config.wsgi:application`.
2. Set `DJANGO_DEBUG=0`, a long random `DJANGO_SECRET_KEY`, and `DJANGO_ALLOWED_HOSTS` to your actual hostnames. Set `DJANGO_CSRF_TRUSTED_ORIGINS` to your HTTPS origins if needed. Copy `.env.example` to `.env` for local configuration; `.env` is automatically loaded without overriding existing environment variables. Production secrets should be supplied by the host’s environment.
3. Set `DATABASE_URL` for PostgreSQL, or `DJANGO_DB_PATH` for SQLite on private durable storage. Inspect `python manage.py migrate --plan` before applying migrations to an existing database, then create a superuser if needed. Do not seed demo data in production.
4. Run `python manage.py collectstatic --noinput` and serve `staticfiles/` at `/static/` with your web server. Never serve the database or project directory.
5. Terminate HTTPS at a trusted server, and configure the WSGI HTTPS environment correctly. No proxy header is trusted automatically. Secure cookies, SSL redirects and HSTS are enabled when debug is off.
6. Run `python manage.py check --deploy` with the production environment, configure backups and restore testing, logging, monitoring and login rate limiting at the proxy, then verify the site over HTTPS.

Scope: this release covers core bookkeeping for one owner per business. It does not include staff invitations, bank-feed imports/reconciliation, automated email/SMS delivery, inventory valuation, payroll, foreign currency, statutory tax filing, or period locking. The account chart is predefined; purchase bills post to purchases/materials. Opening receivables/payables should be represented by individual historical documents, not manual control-account adjustments. For opening inventory/assets or advanced accounting adjustments, extend the chart and workflows before using them.

## WhatsApp bookkeeping agent

Groq (default), optional OpenAI, and Twilio Sandbox integration is implemented, disabled by default. Owners verify their phone, send a text transaction and confirm the validated preview before posting. See [setup, worker operation and limitations](docs/WHATSAPP.md). Provider credentials, the new migrations and a running worker are required for activation.

## Sector-specific web registration

New owners sign up with a username and password, choose one of five sectors, then enter their business details. **Business profile** also lets existing owners add and edit their information. Registration lives in `business_profiles/`; saving operational details does not post financial transactions. See [sector fields, validation and migration notes](docs/SECTOR_ONBOARDING.md). The same five-sector fields now power USSD menus and authenticated registration endpoints; see [USSD registration](docs/USSD_REGISTRATION.md).

## Service-sector bookings

The separate `bookings/` app provides service and staff catalogs, appointment availability, owner scheduling and shareable customer booking pages. Working hours default to **08:00–17:00, Monday–Friday**, with editable working days. Slots are protected against double booking; online requests await owner confirmation, and customers receive private confirmation/cancellation links. See [setup, workflow and deployment notes](docs/BOOKINGS.md).

### Point of sale

Transport, Services, E-Commerce, Retail and Agriculture businesses have an owner-only POS at
`/pos/`, with a catalogue, stock quantities, cash/bank/mobile-money payment records,
printable receipts and full refunds linked to the bookkeeping ledger. See
[POS setup and deployment](docs/POS.md).

### Install as an app

The main workspace and independently hosted USSD emulator support PWA installation.
Use **Install app** at the bottom of either site. Business operations still require
an internet connection; private records are not cached offline.
See [PWA installation and update behaviour](docs/PWA.md).

### Business recommendations

Open **Recommendations** for a practical action plan based on your own recent
business records. The agent uses a separate Groq key and sends only aggregate
metrics after owner consent. See [configuration and data handling](docs/RECOMMENDATIONS.md).


Checkout screenshots can be reviewed and imported into stock through **POS →
Import screenshots**. **Stock table & resale** lets owners tick sold items and
enter selling prices while preserving receipts, stock history and bookkeeping.
