# 4Tax authentication service

Standalone **Spring Boot 4.1.2 / Java 25 / Maven** service. Auth owns application credentials, owner PIN credentials and signed JWT issuance. It stores credentials in PostgreSQL and signing keys in its own persistent volume. No sibling service or outer Maven project is required to build it.

## Build, test and run

From this directory:

```sh
mvn verify
./scripts/dev-up.sh
docker compose ps
docker compose down
```

Requirements: Java 25, Maven 3.9+, Docker/Compose and Python 3. Tests use a real PostgreSQL Testcontainer. The startup script generates or reuses **this service's** private `.env`, creates its persistent volumes, builds its image and waits for health on port 9000. `.env.example` describes its settings. Signing keys are generated automatically in the auth-owned volume. No manual secret creation is required for local startup.

For local communication, independently started service stacks join the Docker network `fourtax-development`. This script creates the network if absent. Auth has the DNS alias `auth`. It can also run alone. The configured issuer defaults to `http://localhost:9000`; clients must validate this exact issuer even when using an internal URL for JWKS.

`AUTH_DATA_VOLUME` and `AUTH_KEY_VOLUME` identify auth-owned persistent volumes. Existing configuration may retain older volume names so stored accounts, clients and signing keys survive the move to a service-local Compose project. `docker compose down` retains those volumes.

## Public application provisioning

**Auth does not need an OAuth client ID/secret for itself.** It generates those credentials for consuming applications.

As requested, application provisioning is public during the prototype:

```http
POST /api/v1/clients
Content-Type: application/json

{"applicationName":"4Tax USSD","scopes":["owners:create","owners:login"]}
```

The response contains generated `clientId`, `clientSecret`, `tokenEndpoint` and scopes. The raw secret is returned once; only its BCrypt hash is stored. Supported scopes are `owners:create` and `owners:login`. Each provisioning request creates a new pair. The consuming application's local setup saves its own returned credentials.

Use the issued pair with HTTP Basic authentication on `POST /oauth2/token` and form fields:

```text
grant_type=client_credentials&scope=owners:create owners:login
```

Application JWTs have audience `auth-api`, kind `application` and a five-minute lifetime.

## Owners and PINs

Both endpoints require an application bearer token with the relevant scope:

| Endpoint | Scope | Behaviour |
| --- | --- | --- |
| `POST /api/v1/auth/owners` | `owners:create` | Create owner credentials; requires a stable `Idempotency-Key` |
| `POST /api/v1/auth/pin/login` | `owners:login` | Authenticate the caller number and PIN |

Both accept `{"mobileNumber":"+26658123456","pin":"012345"}`. PINs are six-character numeric strings, preserving leading zeros. The caller number is normalized to international form. Auth stores a unique number, owner UUID, BCrypt PIN hash and attempt/lock state. Five failed attempts lock PIN login for 15 minutes.

Account creation is idempotent for the same operation, mobile and PIN. A changed payload is rejected; a different operation for an existing owner returns `OWNER_EXISTS` and never overwrites the PIN. Failed-login counters commit even when authentication fails.

Successful account creation/login returns an owner JWT with audience `registration-api`, scope `businesses:create`, kind `owner` and a 15-minute lifetime. The subject is auth's owner UUID. No refresh token is issued. Business information and transaction records belong to the external registration system.

Issuer metadata is at `/.well-known/oauth-authorization-server`; public signing keys are at `/oauth2/jwks`. JWTs enforce signature, issuer, audience, kind, scope and expiry. Auth API DTOs redact PINs, tokens and issued client secrets from diagnostic string output.

See [the OpenAPI contract](openapi.yaml) and [configuration](src/main/resources/application.yml).

## Vercel

`Dockerfile.vercel` builds this service independently. Hosted instances use a persistent secret `AUTH_SIGNING_JWK` instead of a mounted keystore. See [the multi-service deployment guide](../docs/JAVA_VERCEL.md).
