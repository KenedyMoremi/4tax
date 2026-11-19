# Synthetic registration API mock

Standalone **Spring Boot 4.1.2 / Java 25 / Maven** development substitute for the external business registration system. It owns its Maven build, wire models, Compose file and configuration. Data is synthetic and held in memory, resetting when the process restarts.

## Build and run

From this directory:

```sh
mvn verify
./scripts/dev-up.sh
docker compose ps
docker compose down
```

Requirements: Java 25, Maven 3.9+, Docker/Compose and Python 3. The script creates this service's `.env`, joins/creates the local Docker network `fourtax-development`, builds the image and waits for health. The default port is 8081, with network alias `registration-api`.

Run [auth](../auth/README.md) independently for JWT issuance and public keys. Configure `AUTH_ISSUER` and `AUTH_JWKS_URL` using this service's environment; the mock does not read auth's configuration. Defaults are issuer `http://localhost:9000` and internal JWKS URL `http://auth:9000/oauth2/jwks`.

## Behaviour

`POST /api/v1/businesses` requires a signed owner JWT, audience `registration-api`, kind `owner`, scope `businesses:create`, and an `Idempotency-Key`. Ownership comes from the JWT subject. Application JWTs are rejected.

It accepts transport, wellness and vendor payloads, applies basic required-field validation, and returns an entity ID and a `DEMO-` reference. Repeating the same owner/key/payload returns the original result; changing the payload returns `IDEMPOTENCY_CONFLICT`. Each owner can create multiple distinct entities.

The [consumer contract](../ussd/contracts/registration-api.yaml) defines the expected external interface. This service implements its own local Java records. A real external system must persist its idempotency results across restarts and perform authoritative business validation. This mock does not connect to RSL, issue TINs or store real transaction records.
