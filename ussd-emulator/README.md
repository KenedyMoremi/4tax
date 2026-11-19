# USSD emulator

An independent **Spring Boot 4.1.2 / Java 25** browser workbench for testing an HTTP/XML USSD callback. Its build, configuration, Compose project, UI and contracts live entirely in this folder.

## Start

From this directory:

```sh
mvn verify
./scripts/dev-up.sh
```

Open **http://localhost:8090**. Requirements: Java 25, Maven 3.9+, Docker/Compose and Python 3. The startup script generates or reuses this service's private `.env` and starts only the emulator. It joins the local `fourtax-development` network, creating it if necessary.

For a JVM-only run, use `mvn spring-boot:run`; the default callback is then `http://localhost:8080/ussd/callback/grapevine`. Docker defaults to `http://ussd:8080/ussd/callback/grapevine`, using the independently running USSD service's network alias. Paste another HTTP/HTTPS URL to test a different server.

When running in Docker, pasted localhost URLs are forwarded through `host.docker.internal`; the effective destination is returned with each exchange. Set `LOCALHOST_ALIAS` to an empty value to disable that mapping. The callback is requested by the emulator server, so browser CORS settings do not prevent testing it.

## Test a journey

1. Set the callback URL and service code.
2. If the callback requires credentials, paste its key into Gateway key. The default header is `X-Gateway-Key`; the header name is editable under Gateway options. The emulator never reads another service's environment file.
3. Generate a subscriber or edit an existing test profile, then select **Dial service**.
4. Type a reply or use the keypad, then Send. Names and locations can use the full keyboard.
5. Switch subscriber profiles to test isolated, concurrent calls and different owner numbers.

Each call retains its subscriber, IMSI, network, callback URL and session ID. Every normal exchange gets a fresh request ID; Replay request retains the exact IDs, input and XML timestamp. If the same callback URL is still selected, replay can use an updated gateway key to recover from a 401. Toggle request IDs off to test a gateway without that extension.

End call sends `type=abort, reason=ABORT`. Simulate timeout sends `type=abort, reason=TIMEOUT`. The configurable inactivity timer sends the same timeout event automatically. NextState keeps the handset active; End closes it. Connection failures, HTTP errors, malformed XML and callback timeouts are visible in the traffic inspector. An unconfirmed exchange must be replayed before sending the next answer.

The traffic inspector shows request/response XML, HTTP status, latency and callback errors. PIN inputs are masked by default; Reveal PIN input affects the on-screen request inspector and Copy action. Gateway credentials are never included in XML or displayed in the inspector. Requests, replies and credentials are held only in tab memory. Only test subscriber profiles are saved to browser storage; reloading requires entering the gateway key again and starting a new session.

## Generated identities

- Default MSISDN: `+26658` followed by six random digits, eight national digits in total.
- Default IMSI: MCC `651`, MNC `01`, then ten random digits, 15 digits in total.
- Additional published Vodacom MNC `10` is selectable.
- Network callback code: `VOD`.
- Generate one subscriber or a batch of five. API batches support up to 50, with unique MSISDNs and IMSIs within each batch. Profiles can be renamed, edited and removed when not in an active call.

The default 58 prefix is supported by Vodacom's published contact format and the ITU's Lesotho numbering material. Other 5-series prefixes can be entered as test configuration; the generator does not assert their current allocation. These are synthetic format-valid values, not provisioned SIMs or a guarantee that a number is unassigned. IMSI and mobile number are generated independently; there is no claim that the pair belongs to a real subscriber.

Sources: [Vodacom Lesotho number example](https://www.vodacom.co.ls/terms-conditions/international-roaming/), [ITU Lesotho numbering announcement](https://www.itu.int/dms_pub/itu-t/opb/sp/T-SP-OB.769-2002-PDF-F.pdf), [ITU MCC/MNC listing](https://www.itu.int/dms_pub/itu-t/opb/sp/T-SP-OB.1280-2023-OAS-PDF-F.pdf), [ITU E.212](https://www.itu.int/ITU-T/recommendations/rec.aspx?rec=15788).

## Wire format and API

This emulator targets the project's Grapevine XML v1.3 adapter, rather than claiming a universal Vodacom/Econet wire contract. It simulates the HTTP gateway boundary, not SS7 signalling, a radio network, airtime or billing.

Every request provides `msisdn`, `sessionId`, `network`, `code`, `type`, and the appropriate initial parameter, action fields or abort reason. It also sends the generated `imsi`, `mcc`, `mnc`, ISO timestamp and optional request ID as explicit extensions. The existing USSD adapter accepts these extra fields and currently routes by MSISDN/session, without using IMSI for authentication.

Responses must contain `ussdAppResponse` with `prompt`, `responseType=string`, and `state=NextState|End`. XML DTDs/external entities are rejected. Callback redirects are not followed, and full response transfer is bounded by the selected timeout and a 64 KiB response limit.

| Emulator endpoint | Purpose |
| --- | --- |
| `GET /api/emulator/config` | Non-secret default connection settings |
| `POST /api/emulator/identities` | Generate synthetic subscribers: `count`, `prefix`, `mnc` |
| `POST /api/emulator/exchanges` | Build an XML event, call the supplied URL and return the inspected exchange |

See [OpenAPI](openapi.yaml). No database, Redis or OAuth application credentials are needed for the emulator itself. Its Compose port binds to localhost. `docker compose down` stops this service independently.

## Verification

`mvn verify` tests identity generation, XML formats and escaping, request replay, abort/timeout events, HTTP failures, redirects, response limits, stalled-body timeouts, and the web/API endpoints.

With USSD running and connected to the hosted auth/registration services, use `python3 scripts/smoke-test.py` for callback tests. It prompts for the gateway key without saving it, or accepts `GATEWAY_KEY` in the process environment. It tests generated identities, both languages, all five sector menus, replay and recovery, then aborts before capturing personal details or creating auth/business records. Optional `EMULATOR_URL` and `USSD_CALLBACK_URL` select other local test endpoints.

## Vercel

`Dockerfile.vercel` builds this service independently. Configure `ALLOWED_CALLBACK_URL` to the exact hosted USSD callback before public deployment; other destinations are rejected before network access. See [the multi-service deployment guide](../docs/JAVA_VERCEL.md).
