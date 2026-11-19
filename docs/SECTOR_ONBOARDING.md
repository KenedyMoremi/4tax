# Web sector onboarding

Web signup requires a username and password (with confirmation). A new user then chooses Transport, Services, E-Commerce, Retail or Agriculture, and completes that sector's business form before a bookkeeping workspace is created.

The general registration code lives in `business_profiles/`; financial models, posting and reporting remain in `bookkeeping/`. This release does not alter the separate Java auth/PIN service, USSD journeys or registration API contract.

## Captured information

Every sector records the owner's national ID as text, preserving leading zeros, together with the existing business name, district, contact and tax settings. ID collection is not identity verification.

| Sector | Additional information |
| --- | --- |
| Transport | Owner/driver/both; working days and start/end times; multiple routes with per-passenger or per-trip prices; multiple vehicles with registration number, VIN, make/model, registered owner, registration notes, condition, tank capacity, last service or not-yet-serviced status, and service intervals in months/km. |
| Services | Working hours; service/consultation catalogue with fixed, starting or quoted prices; equipment quantities owned or needed; employee totals and grouped roles, counts and per-person salaries with explicit salary periods. |
| E-Commerce | Item types, units and purchase/selling prices; shipping methods, charges and charge basis; marketing channels; devices and quantities; data provider/plan, allowance, cost and billing period. |
| Retail | Location; stock quantities and units, purchase and selling prices per item; employee groups, counts, salaries and periods. |
| Agriculture | Activity and location; inputs and their unit prices; outputs and selling prices; employees; farmland plots and hectares; livestock types, descriptions, counts, prices per animal and ages in months. Separate livestock rows represent different age groups. |

Collections support up to 50 rows each. Salaries are optional for agriculture, where the requested employee information does not specify pay. Crop activities require farmland; livestock/breeding activities require livestock; mixed farming requires both. Working hours apply to the selected weekdays and support overnight/24-hour shifts. Equipment and employee rows can be left empty where not applicable, with employee count zero.

## Behavior and storage

`SectorProfile` is a one-to-one extension of the existing business. Typed Django forms validate all fields and collection rows before saving sector-specific JSON. Monetary values are decimal strings with two-place input precision. These are operating details and catalogue prices; saving a profile does not create expenses, sales, stock movements or payroll entries.

The owner can edit the saved details through **Business profile**. The sector is fixed once saved so changing a URL cannot discard another sector's details. Existing businesses retain their accounts and financial records and receive a dashboard link to complete their profile. No sector or ID is invented for existing users.

Business creation, the initial account chart and the profile commit atomically. An owner-row lock serializes initial setup, and a version field rejects repeated/stale submissions rather than silently overwriting another tab's changes. Queries are scoped to the authenticated owner. Profile responses use no-store cache headers; all browser writes require CSRF tokens. Profile POST parameters are marked sensitive for Django error reporting. No ID or profile data is sent to the AI provider by this feature.

## Migration and deployment

`business_profiles.0001_initial` adds a new table and sector constraint only. Existing tables and historical migrations are unchanged. Apply this migration before deploying the new templates/context processor, which query the new relation. Obtain production database approval according to the repository's AGENTS.md before applying it to Neon. No backfill is required. Rolling back the migration would delete saved sector profiles; do not reverse it on populated production data.

Checks include all five save/edit paths, username-only signup, ownership isolation, CSRF, required fields and collection limits, prices, employee totals, dates and working hours, conditional agriculture rows, rollback on save failure, stale submissions, and preservation of existing accounts. Isolated browser checks cover mobile/desktop layouts and adding/removing collection rows.
