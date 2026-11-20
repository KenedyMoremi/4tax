# 4Tax USSD service

Standalone **Spring Boot 4.1.2 / Java 25 / Maven** service for informal-business registration. It owns its screens, nodes, routers, callback adapters, consumer contracts and temporary Redis state. It has no SQL database and no dependency on a shared Java module or outer Maven project.

## Build, test and run

From this directory:

```sh
mvn verify
./scripts/dev-up.sh
docker compose ps
docker compose down
```

Requirements: Java 25, Maven 3.9+, Docker/Compose and Python 3. Maven tests use a real Redis Testcontainer. Unit-only execution is available with `mvn -Dtest=JourneyTest,GrapevineXmlTest test`.

USSD uses the real registration API at **https://4tax.vercel.app** and its trusted auth issuer **https://4tax-auth.vercel.app**. There is no registration mock. The startup script generates a private service-local `.env`, validates its saved application credentials against the configured auth service and provisions replacements when needed. It starts only USSD and Redis. Owner records and business entities are created in the real services when a user confirms registration; no registrations are created by startup.

Defaults are `AUTH_URL=https://4tax-auth.vercel.app`, `AUTH_ISSUER=https://4tax-auth.vercel.app`, `AUTH_JWKS_URL=https://4tax-auth.vercel.app/oauth2/jwks` and `REGISTRATION_URL=https://4tax.vercel.app`. Host-side client provisioning uses the same hosted auth URL. Startup updates the known obsolete local defaults in an existing `.env`. Custom URLs remain configurable. For an isolated development backend, configure both sides to trust the same auth issuer. This service never reads a sibling service's environment file.

The public callback deployed on Vercel is **https://4tax-ussd.vercel.app/ussd/callback/grapevine**; the hosted emulator is **https://4tax-ussd-emulator.vercel.app**. Production Vercel environment variables override source defaults. Replace a production `REGISTRATION_URL=https://example.com` with the real base URL and redeploy USSD.

Default callback port is 8080. `.env.example` describes service-local settings. Startup automatically generates a private `.env` and obtains application credentials from auth; no manual secret creation is required. Existing local credentials are retained when auth accepts them.

Outbound auth, registration and JWKS calls use `BACKEND_CONNECT_TIMEOUT=5s` and `BACKEND_REQUEST_TIMEOUT=60s` by default to accommodate prototype Vercel cold starts and AI preview requests. Configure positive durations up to 10s and 60s respectively. The Redis processing lease exceeds the bounded submission calls so a slow request cannot lose its lock after 30 seconds. These prototype budgets must be checked against the chosen MNO's real session deadlines.

## Registration journeys

The five sectors are Transport, Services, E-Commerce, Retail and Agriculture. Their choices and fields are generated from the Django web forms into `registration-schema.json`; run `python manage.py export_registration_schema` at the repository root after changing those forms. CI checks for drift. See [field definitions and API setup](../docs/USSD_REGISTRATION.md).

All sectors collect location, monthly turnover and named employees with a separate monthly salary choice. Initial registration also collects owner names and national identity number. Employee capture opens directly with the full-name prompt, followed by a monthly salary range menu. After each employee, choose Add another or Continue; Clear entries resets the unsaved employee list. Choose `7. Skip` at the name prompt to continue without adding an employee. Empty route/livestock lists open directly at the first entry; routes and livestock activity require at least one row. Collection actions appear only when usable. Transport starts with Taxi/Cab/Catch-a-ride before details. The Other description is shown and required only when Other is selected in E-Commerce, Retail or Agriculture; listed types skip it in registration, review and editing. Agriculture captures farmland count and, when positive, size/unit. Zero plots records zero size with no applicable unit; farming requires land. Daytime hours derive `overnight=false`; overnight/24-hour hours require confirmation or correction. Exact decimal amounts are strings, and ranges use stable categorical keys. Existing registered entities are not overwritten.

Choose English or Sesotho. USSD checks the caller number with auth: existing owners go straight to PIN login, while new owners see Register business and Login. If the lookup fails, Retry/Login is shown without assuming the number is unregistered. A new owner completes business details, review/edit, PIN creation and confirmation. With an application JWT cached or obtained first, USSD calls auth to create the account and obtain an owner JWT, then calls the external API to create the entity. The PIN is sent only to auth.

Existing owners log in using the MNO-supplied caller number and PIN. Their post-login menu offers **Add business** and **Add transaction**. Add business asks only for sector and business details, skipping owner names, identity number and PIN creation. Ownership comes from the verified owner JWT. After registration, a success screen shows the reference and offers **1. Main menu** and **0. Exit**, keeping the owner signed in until exit.

Editing existing registered entities remains deferred. The authenticated menu offers Add business and Add transaction. Editing during registration is available from review.

- `8. Back`: previous page, or previous screen from the first page; `0. Exit` ends the session.
- `9. Next` advances pages; the last page offers `9. Continue`, `9. Confirm` or `9. Confirm and post` only when applicable. `8. Back` is displayed before `9` actions.
- `7. Skip` appears only for optional answers. Weekday `7` still means Sunday.
- Numeric values that match displayed controls use a leading zero: `08` for eight and `00` for zero. `9` is a normal answer when no Continue/Next action is displayed. Identity numbers and six-digit PINs retain leading zeros.
- Menus use page-local choices `1–7`; longer menus page without multi-digit choices. Only commands displayed on the current page are accepted. The welcome, main and PIN-login screens retain their existing clean layout.
- Screen text defaults to a configurable 160-character limit.

Every prompt, validation message and outcome has English and Sesotho wording in `src/main/resources/messages*.properties`. **Sesotho is draft copy requiring fluent-speaker review before live use.**

## Sessions, recovery and retries

Redis retains unfinished drafts for 15 minutes after the last meaningful update. Opening registration or selecting a business without entering an answer does not create a resumable draft. Navigation version 5 ends older active sessions with a redial message, preserving drafts, operation keys and receipts; cached replies are versioned too. Invalid input and pagination do not extend the draft. Ending a session clears its authenticated context. A returning owner must log in before resuming once account creation has begun. In-flight registration submissions retain their original payloads. Unsubmitted existing-owner drafts paused at owner details skip those prompts on resume.

Drafts exclude PIN values and bearer tokens. Active sessions can contain a short-lived JWT and a temporary keyed digest for PIN confirmation. Raw PINs are never stored in Redis. Data keys are keyed digests of caller/session identifiers.

If auth succeeds but business creation fails, keep the auth account and draft. Reuse the same operation key on retry. A lost response leaves the payload frozen until the operation can be confirmed, preventing changes from accidentally creating a second entity. A definite validation rejection permits editing. Success requires a confirmed entity ID and reference.

## Callback interfaces

`POST /ussd/callback/grapevine` accepts `application/xml` or `text/xml` with `X-Gateway-Key` from this service's configuration. Examples: [initial](examples/initial.xml), [action](examples/action.xml), [abort](examples/abort.xml), [Skip](examples/skip.xml) (only on an optional screen) and [Exit](examples/exit.xml).

The adapter implements published Grapevine v1.3 shapes. Replies contain `prompt`, `responseType=string` and `state=NextState|End`. Optional `requestId` enables reliable deduplication. Without a stable provider ID, repeated input cannot safely be distinguished from a legitimate next answer; account/entity side effects remain idempotent.

The emulator can send the same XML to `POST /ussd/callback/grapevine/inspect` with the same gateway key. It returns `{responseXml, exchanges}` with each downstream call's stage, URL, redacted request headers/body, HTTP status, duration and redacted response. Signing-key HTTP requests include status and duration (public key bodies are omitted). Local owner-JWT verification is explicitly marked `LOCAL`. Credentials, PINs, tokens and personal fields are excluded; validation failures expose field names rather than arbitrary upstream error text. Captures exist only during that HTTP request, with no Redis or logging storage. Normal gateway XML remains unchanged, and deduplicated callbacks do not repeat downstream calls or reproduce an earlier trace.

Vodacom Lesotho documents HTTP/XML integration. Grapevine is an initial prototype adapter, rather than a confirmed Vodacom or Econet Lesotho contract. Confirm each operator's payload, credentials, timeouts, encoding and limits before live activation, and configure a public HTTPS callback URL. The local Compose port binds to localhost.

Sources: [Vodacom Lesotho](https://www.vodacommessaging.co.ls/ussdapi.asp), [Grapevine guide](https://manuals.vine.co.za/docs/UG_USSD_V1.3.pdf).

With the `dev` profile, `POST /ussd/callback/simulator` accepts JSON through the same engine and requires the same gateway header:

```json
{"network":"TEST","sessionId":"demo-1","mobileNumber":"26658123456","event":"START","input":"","serviceCode":"*123#","requestId":"start-1"}
```

Continue with `event=INPUT`, only the latest answer, and a new unique request ID. Use `ABORT` to end. The simulator is absent outside `dev`.

See [USSD OpenAPI](openapi.yaml), [the external registration contract](contracts/registration-api.yaml), and [the authoritative auth API](../auth/openapi.yaml). Each consuming service defines its own wire models locally.

## Vercel

`Dockerfile.vercel` builds this service independently. Hosted sessions use the injected TLS `REDIS_URL`. `https://example.com` is treated as a disabled registration placeholder and receives no business data. See [the multi-service deployment guide](../docs/JAVA_VERCEL.md).

`python3 scripts/smoke-test.py` checks public service metadata and START/language/menu/ABORT callbacks. It does not create owners or business records. Complete registration journeys are tested with the in-memory backend in Maven tests and disposable databases in Django tests.

## Add transaction

After PIN login, choose **2. Add transaction**. The owner-authenticated business list comes from `GET /api/v1/businesses`; five results are returned per page. Every new transaction starts with a business list and an explicit choice, including when there is only one business. Business sectors are derived from saved registrations, not entered by the caller. An owner with no business can return to Add business. Posted receipts offer **Add transaction**, **Main menu** and **Exit**.

Sale summaries and buyer names are free text. The payment screen offers **1. Cash**, **2. Bank**, **3. M-Pesa**, and **4. EcoCash**. Text such as `unpaid + due date` remains available for unpaid invoices:

| Sector | Fields |
| --- | --- |
| Transport | One summary containing routes, passengers and fare per person or total |
| Services | One summary containing the service and its price |
| E-Commerce, Retail, Agriculture | One summary containing goods, quantities and unit prices or total |

Every new transaction has exactly three capture screens: **sale summary → payment/account details → buyer full names**. A summary such as `sold 2 weaves worth M1800 each` supplies quantity and unit price; the interpreter extracts these and the application calculates M3,600 using decimal arithmetic. The second screen selects a paid account (cash/bank/M-Pesa/EcoCash), or explicitly unpaid with a due date. A phone/account number alone is rejected on that screen before asking for the buyer. Previously rejected drafts with such a number return directly to account selection on resume, preserving the buyer and sale summary; choosing the account automatically rebuilds the preview. The third captures buyer names (`7. Skip` becomes `N/A`). Paid sales can use N/A. Unpaid invoices require an identifiable buyer and due date; the service never invents a payment account. Currency is explicit Maloti in the price prompts. Only displayed controls are reserved; use `08` or `00` for literal eight or zero.

The last answer automatically creates an AI preview. Review the full result, use `8. Back` to edit a field, `0. Exit` to leave, or `9. Confirm and post` on its final page. Ordinary previews fit one screen; longer summaries and VAT details paginate without dropping values. Back on every preview page opens editing. Back first confirms cancellation of the old proposal, retains the original text, and allocates a fresh operation only after cancellation is confirmed. A lost cancellation response retains the cancellation/edit intent for retry. USSD sends JSON with the owner JWT and a stable `Idempotency-Key` to `https://4tax.vercel.app/webhooks/twilio/whatsapp/`. It uses the authenticated USSD adapter, not a forged Twilio message. The API uses the existing bookkeeping AI, validation and posting functions. It returns a structured preview so fixed screen labels can be localized. **Only Confirm and post writes financial entries.** Cancelling an old preview for editing posts nothing. Legacy in-flight sector-specific drafts retain their exact original payloads until their result is resolved. A definite clarification or confirmed cancellation moves ordinary-sized legacy answers into the three-field editor, preserving payment and buyer details; oversized legacy text remains intact in its original form. Unclear or incomplete instructions return for editing; AI outages and unknown responses retain the original operation for retry.

Transaction drafts are retained in Redis for 15 minutes. Ending a call removes authenticated session context; after PIN login, Add transaction offers Resume. Resume directly retries an unresolved action with its original key, or displays an already prepared preview; it never treats Resume as new posting confirmation. Ambiguous submissions cannot be discarded into a new operation. Stale callbacks cannot act as confirmation of a preview that was not shown in that session. Confirmations are independently idempotent in the external API. A posted receipt is retained until acknowledged (within the same 15-minute TTL), so losing the final success screen does not immediately start another sale.

The emulator inspector shows owner-lookup, list-businesses and transaction-webhook entries. Transaction field values and proposal summaries are redacted in diagnostics. The API contract is local to this service at [transaction-api.yaml](contracts/transaction-api.yaml); the Django producer documents its adapter separately in [whatsapp/USSD.md](../whatsapp/USSD.md).

A definite clarification response saves the new operation ID and editable stage before returning, including retry/resume branches. Repeated clarification no longer causes a session/draft operation mismatch. Clarification opens a compact three-field editing menu.

Navigation upgrades also invalidate active pre-update transaction screens: a prior `9. Next` reply cannot be interpreted as confirmation of a newly compacted preview. Drafts and operation keys remain recoverable after redial and login.
