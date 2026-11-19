# Service-sector bookings

The Django `bookings/` app adds appointments alongside bookkeeping. Only owners of a `services` sector profile can manage a calendar. Financial data, ledger entries and tax settings are not modified by bookings.

## Getting started

Open **Bookings** in the workspace navigation, or `/bookings/`.

1. Add services with names, descriptions, prices in Maloti and durations in 15-minute increments (15 minutes to eight hours).
2. Add yourself and any staff members. Each staff member has a separate appointment calendar. All active staff currently offer all active services and share the business's working hours.
3. Save working days and hours, then enable **Accept online bookings**. Defaults are Monday–Friday, **08:00–17:00**, in Africa/Maseru time. Calendar hours are independent of registration answers and are editable here. Opening and closing times use 15-minute increments; overnight calendars are not supported.
4. Share the public link shown on the dashboard. Online booking is disabled until the owner enables it, and requires an active service and staff member.

The customer directory at `/book/` lists only enabled service-sector businesses with active services and staff. Customers can search by business, service, sector activity or district. Enabling online bookings also makes the business visible in this directory.

Customer booking pages use `/book/<calendar UUID>/`. Customers choose a service, staff member and date, then select a free time and enter their name and phone number. Email and notes are optional. Bookings are available up to 90 days ahead with at least 30 minutes' notice. The entire appointment must fit inside working hours. Availability is rechecked on submission.

Online requests initially await confirmation and reserve the selected time. The dashboard's **Upcoming requests to confirm** link shows requests across all future dates. Owners can confirm or cancel requests; owner-entered appointments are confirmed immediately. Confirmed appointments can be completed or marked no-show after their start time. Cancelled, completed and no-show appointments cannot be reopened. Upcoming active appointments can be rescheduled by the owner; stale edits are rejected.

A customer receives a private confirmation link in the browser. Anyone holding that link can view the appointment and cancel it before it starts. Treat it as a credential. Confirmation pages are non-cacheable, no-index and use no-referrer. Customer contact details/notes are not exposed in public availability pages. All state-changing browser requests use CSRF protection. Owners can access only their own business's appointments, catalog and staff.

No automatic email, SMS or WhatsApp messages are sent. Customers should save their confirmation link; owners should contact customers to confirm or discuss changes. No payment is collected, invoice created or revenue posted. Existing WhatsApp bookkeeping and USSD registration services remain separate.

## Scheduling and consistency

Appointments snapshot service name and price so later catalog changes do not rewrite agreed details. Inactive services/staff disappear from new bookings while existing appointments remain visible. Working-hour changes that would exclude an existing active appointment are rejected until it is rescheduled/cancelled.

Each appointment reserves 15-minute blocks in `ReservedSlot`. A database unique constraint on `(staff, starts_at)` prevents simultaneous occupancy. Business-row locks serialize bookings, cancellations, rescheduling and catalog/hour changes; slot updates happen atomically. Cancellation releases slots. Request UUIDs and payload fingerprints make duplicate submissions retry-safe. Concurrent changed requests cannot reuse a key to create a second appointment. Rescheduling retains the original service and price, uses the service's current duration, and increments an optimistic version.

Shared staff working hours, all-staff/all-services eligibility and manual customer communication are deliberate initial limits. There are no deposits, per-staff shifts, external calendar sync, appointment reminders or automated financial postings.

## Migration and validation

`bookings.0001_initial` adds Calendar, Service, Staff, Appointment and ReservedSlot plus constraints and indexes. It does not backfill existing businesses or enable public booking pages. Production migration requires approval under repository AGENTS.md.

Run:

```sh
python manage.py check
python manage.py makemigrations --check --dry-run --settings=config.test_settings
python manage.py test
npm run build:css
```

CI also runs `bookings` against a disposable PostgreSQL service using `config.registration_postgres_test_settings`. Its concurrency tests race overlapping and identical requests through real HTTP views and verify one appointment/one set of reserved slots. Never set its test database URL to the production application database.
