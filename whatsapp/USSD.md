# USSD sales through the WhatsApp webhook

`POST /webhooks/twilio/whatsapp/` supports two independent adapters:

- Existing Twilio form requests keep their signature, account, destination, linked-number, consent, queue and worker checks.
- USSD JSON requests require a signed owner JWT (configured issuer, audience `registration-api`, kind `owner`, scope `transactions:create`). They never impersonate Twilio, send WhatsApp replies, or infer ownership from a phone number/national ID. JSON without valid bearer authentication is rejected even when WhatsApp is disabled.

The authoritative USSD contract is [ussd-api.yaml](ussd-api.yaml). Every operation uses an `entityId` from `GET /api/v1/businesses` (scope `businesses:read`) and is scoped to the JWT issuer and subject. The lookup includes only that owner's registrations and returns five at a time. A text instruction such as “record these transactions under my business” is **not required**: `agents.bookkeeping.interpret` already interprets one bookkeeping record. Business selection and authorization come from entity ID/JWT, not natural-language instructions.

## Free-text behavior

New USSD clients send three text fields: `summary`, `paymentDetails`, and `buyer`. The summary contains the full sale, including quantity and unit price or a total; older sector-specific payloads remain accepted and are adapted for interpretation without changing their stored payload or operation key. The AI extracts explicit `quantity`/`unit_price`; the application multiplies with Decimal arithmetic. Conflicting totals or incomplete unit prices require clarification. A bare account on the paid-account screen selects a paid sale; unpaid sales explicitly include a due date.

The existing AI interpreter extracts one proposed sale or unpaid sales invoice. Multiple or ambiguous transactions require clarification. Paid sales require a payment account; unpaid invoices require a buyer and due date. The USSD adapter permits buyer `N/A` for a paid sale. For transport, fare text must distinguish per-passenger pricing from a total. No account, payment status, buyer or due date is guessed by the adapter.

The endpoint shares `interpret`, `agent_actions.propose`, `validate_intent` and `resolve_proposal` with the WhatsApp workflow. Creating a preview posts nothing. A separate authenticated `confirm` action posts through the existing validated ledger services; paid sales create the invoice and payment, while unpaid sales create an outstanding invoice. `cancel` never posts. Proposal expiry and changed account details require a fresh reviewed preview.

The USSD entity remains separate from web identities. On its first proposal, an explicit `USSDLedger` mapping provisions a separate bookkeeping business, chart and noninteractive internal user with an unusable password. Each entity has its own ledger, including several entities owned by one auth subject. No existing web account is linked by matching phone, name or national ID. District is left blank, rather than inferred from free-text location. Registration itself still creates no books or financial entries.

## Retries and concurrency

`USSDTransaction` retains the original bounded input, operation key, AI-processing claim/lease and proposal mapping. Identical retries recover the same proposal; changed input with the same key returns `IDEMPOTENCY_CONFLICT`. AI runs outside database locks. An overlapping request returns `TRANSACTION_BUSY`; expired processing leases can be recovered. Confirmation reuses the operation key and locks the registration/business/proposal, so a lost reply or concurrent callbacks cannot double-post. No credentials, PINs, bearer tokens or input payloads are logged. API errors contain stable codes, not provider exception text.

## Database rollout

The additive migration is `business_profiles/migrations/0003_ussd_transactions.py`. It creates only `USSDLedger` and `USSDTransaction` and their constraints/relations. It does not transform existing registrations, web users or posted records. Apply it with the production Django database configured before enabling Add transaction:

```sh
python manage.py migrate business_profiles 0003_ussd_transactions --plan
python manage.py migrate business_profiles 0003_ussd_transactions
```

The approved release now applies this target through the website’s existing `scripts/vercel_build.py` on `VERCEL=1` / `VERCEL_ENV=production` only. The `apply_ussd_schema` command uses Vercel’s existing database configuration, transaction-scoped advisory locking and an allowlisted forward plan. Known additive prerequisites can be applied if absent. It skips an already-applied target and never downgrades future schema versions. Failure stops publication. Preview builds and local tests never mutate production. This production step was authorized by the user for this release. If the new tables are absent, USSD transaction requests return `SERVICE_UNAVAILABLE`; existing registration and Twilio behavior remain available.

Auth must also be deployed with owner lookup and the new owner-token scopes, followed by USSD. Existing owners log in again to obtain `businesses:read transactions:create`. No new application client credentials/scopes are required.

Verification: `python manage.py test business_profiles.test_ussd_transactions whatsapp --settings=config.test_settings`. PostgreSQL row-lock tests use `config.registration_postgres_test_settings` and an explicitly disposable `REGISTRATION_TEST_DATABASE_URL`. AI/Twilio calls are mocked in tests. Sesotho prompts require fluent-speaker review before live use.

`GET /api/v1/transactions/health` is a read-only release check returning only `ready`, `schemaReady` and `aiConfigured`. It checks the recorded migration, both tables and presence of the configured AI provider key without exposing secrets or making an AI call. It returns 503 until ready.

The USSD client prepares a preview automatically after its last answer and offers one final review. `9. Confirm and post` is accepted only on the final preview page. `8. Back` on every preview page opens field editing, while `0. Exit` ends the session. Editing cancels the old pending proposal using the same operation key, preserves captured fields, and allocates a new key only after cancellation is confirmed. Ambiguous cancellation/confirmation keeps its saved intent for recovery. `7. Skip` supplies buyer `N/A`; this remains valid only for a paid sale.
