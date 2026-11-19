# Independent Java services on Vercel

Each service is a separate Vercel project connected to the same GitHub repository, with its own root directory and production URL. The existing Django project remains separate.

| Project | Root | Intended stable URL |
| --- | --- | --- |
| 4tax-auth | auth | https://4tax-auth.vercel.app |
| 4tax-ussd | ussd | https://4tax-ussd.vercel.app |
| 4tax-ussd-emulator | ussd-emulator | https://4tax-ussd-emulator.vercel.app |

These services retain Java 25 and Spring Boot. Vercel's Container runtime builds `Dockerfile.vercel` using Maven and starts the JAR on `PORT=8080`. Docker build contexts include only source and the Maven descriptor, excluding credentials and local storage. The existing Dockerfiles/Compose projects still support local development. Container instances scale to zero: local files and memory cannot hold durable credentials or sessions.

## Auth

The isolated Neon database `fourtax_auth` uses its own login role, separate from bookkeeping. Configure these as production secrets on **4tax-auth**:

- `AUTH_DATABASE_URL`: JDBC PostgreSQL URL with SSL and channel binding enabled.
- `POSTGRES_USER`, `POSTGRES_PASSWORD`: auth-only database credentials.
- `AUTH_ISSUER`: the exact stable public auth URL, without a trailing slash.
- `AUTH_SIGNING_JWK`: a persistent private RSA JWK with a stable `kid`. It must be identical across instances and deployments. Never regenerate at startup or expose it through JWKS; JWKS publishes the public portion only.
- `PORT=8080`.

Auth can still use its existing PKCS12 keystore locally when no JWK is supplied. Hikari pools are bounded to three connections per function instance. Flyway applies auth's existing schema migration to its isolated database on startup. Do not configure a bookkeeping database as the auth database.

## USSD

A free Upstash Redis resource (`4tax-ussd-sessions`) is connected only to **4tax-ussd** production. Automatic paid upgrades were disabled during provisioning. Its injected `REDIS_URL` supplies the connection; set `REDIS_SSL=true`. Keep sessions outside the container so multiple instances and restarts preserve deduplication and drafts.

Configure `AUTH_URL` and `AUTH_ISSUER` to the auth production URL, `AUTH_JWKS_URL` to that URL plus `/oauth2/jwks`, and save the application's issued `USSD_CLIENT_ID` and `USSD_CLIENT_SECRET` as production secrets. Generate independent `GATEWAY_KEY` and `STATE_SECRET` values. Do not publish them in emulator HTML or `/api/emulator/config`.

`REGISTRATION_URL=https://example.com` is an explicit placeholder. The application refuses to send business records or owner tokens to that host and returns a service-unavailable outcome. Menu navigation and login are available, but business registration cannot finish until a real compatible API is configured. No registration mock is deployed. The real API must accept `POST /api/v1/businesses`, validate the auth issuer/JWKS, audience `registration-api`, scope `businesses:create`, and honor `Idempotency-Key` (see `ussd/contracts/registration-api.yaml`).

## Emulator

Set both `DEFAULT_CALLBACK_URL` and `ALLOWED_CALLBACK_URL` to the USSD production URL plus `/ussd/callback/grapevine`. The hosted relay accepts only this exact callback, preventing public users from forwarding requests to arbitrary services or private network addresses. Local development leaves the allowlist blank to retain the existing general-purpose test workflow. Redirects remain disabled.

The gateway key must be entered into the emulator's Gateway key field. It is held only in tab memory and not returned by its config API. The UI sends requests to its own backend, which calls USSD server-to-server; no cross-origin browser API wiring is required.

## Verification

GitHub Actions runs `mvn -B verify` for all three projects using Java 25 and real PostgreSQL/Redis Testcontainers. Deployment verification should check auth health/JWKS/token issuance, USSD health/unauthorized callbacks, and a synthetic emulator START → language selection → ABORT exchange. Never use smoke tests that create synthetic owners/businesses against real production systems without explicit authorization.

The auth client-provisioning endpoint remains public by the existing prototype contract. These are prototype deployments; no operator USSD network is connected by deploying a URL. Configure the actual MNO callback contract separately.

Reference: [Vercel Container runtime](https://vercel.com/docs/functions/runtimes/container).
