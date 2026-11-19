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

Start the independent [auth service](../auth/README.md) first and the Django application for business creation. Apply its migrations to a disposable development database and configure its trusted auth issuer/JWKS. The old registration mock and smoke scripts use the legacy contract and must not be used with the new journeys. Each is started using its own `scripts/dev-up.sh`. This service's script generates its own `.env`, obtains an application client ID/secret from auth's public provisioning endpoint, saves that pair locally, and starts only USSD and Redis.

All local stacks join `fourtax-development`; each startup script can create that Docker network. Legacy Compose defaults (override REGISTRATION_URL to the Django API before using these journeys) are `AUTH_URL=http://auth:9000`, `AUTH_JWKS_URL=http://auth:9000/oauth2/jwks` and `REGISTRATION_URL=http://registration-api:8081`. Host-side provisioning uses `AUTH_PUBLIC_URL=http://localhost:9000`. Replace these URLs to use separately deployed APIs. This service never reads a sibling service's environment file. Startup validates its saved client credentials with auth and automatically provisions a replacement when starting against a fresh auth database.

Default callback port is 8080. `.env.example` describes service-local settings. Startup automatically generates a private `.env` and obtains application credentials from auth; no manual secret creation is required. Existing local credentials are retained when auth accepts them.

## Registration journeys

The five sectors are Transport, Services, E-Commerce, Retail and Agriculture. Their choices and fields are generated from the Django web forms into `registration-schema.json`; run `python manage.py export_registration_schema` at the repository root after changing those forms. CI checks for drift. See [field definitions and API setup](../docs/USSD_REGISTRATION.md).

All sectors collect owner names, national identity number, location, monthly turnover and named employees with a separate monthly salary choice. Employee, route and livestock collection menus support Add another / Continue / Clear entries. Transport starts with Taxi/Cab/Catch-a-ride before details. Agriculture separately captures farmland count and size/unit. Exact decimal amounts are strings, and ranges use stable categorical keys. Existing registered entities are not overwritten.

Choose English or Sesotho, then Register business or Login. A new owner completes business details, review/edit, PIN creation and confirmation. With an application JWT cached or obtained first, USSD calls auth to create the account and obtain an owner JWT, then calls the external API to create the entity. The PIN is sent only to auth.

Existing owners log in using the MNO-supplied caller number and PIN. Their post-login menu offers **Add business**, reusing the same sector flows without PIN creation.

Viewing, editing existing registered entities and recording transactions are deferred. Editing during registration is available from review.

- `0`: Back; `99`: Exit.
- `88` / `87`: Next/previous page on multi-page screens.
- Optional text accepts `-` to skip; numeric fields accept `00` for zero because `0` is Back.
- Screen text defaults to a configurable 160-character limit.

Every prompt, validation message and outcome has English and Sesotho wording in `src/main/resources/messages*.properties`. **Sesotho is draft copy requiring fluent-speaker review before live use.**

## Sessions, recovery and retries

Redis retains unfinished drafts for 15 minutes after the last meaningful update. Invalid input and pagination do not extend the draft. Ending a session clears its authenticated context. A returning owner must log in before resuming once account creation has begun.

Drafts exclude PIN values and bearer tokens. Active sessions can contain a short-lived JWT and a temporary keyed digest for PIN confirmation. Raw PINs are never stored in Redis. Data keys are keyed digests of caller/session identifiers.

If auth succeeds but business creation fails, keep the auth account and draft. Reuse the same operation key on retry. A lost response leaves the payload frozen until the operation can be confirmed, preventing changes from accidentally creating a second entity. A definite validation rejection permits editing. Success requires a confirmed entity ID and reference.

## Callback interfaces

`POST /ussd/callback/grapevine` accepts `application/xml` or `text/xml` with `X-Gateway-Key` from this service's configuration. Examples: [initial](examples/initial.xml), [action](examples/action.xml), [abort](examples/abort.xml).

The adapter implements published Grapevine v1.3 shapes. Replies contain `prompt`, `responseType=string` and `state=NextState|End`. Optional `requestId` enables reliable deduplication. Without a stable provider ID, repeated input cannot safely be distinguished from a legitimate next answer; account/entity side effects remain idempotent.

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
