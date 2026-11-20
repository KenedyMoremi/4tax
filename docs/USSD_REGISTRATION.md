# Five-sector registration API

Web registration and the USSD client share Django form definitions in `business_profiles/forms.py`.

- `GET /api/v1/registration/options`: public sector menus, field types, choices and collection limits. No personal data is returned. The response declares schema version 2, LSL currency and monthly turnover/salary periods.
- `POST /api/v1/businesses`: persist a validated USSD registration. Requires an owner bearer JWT and `Idempotency-Key`. Returns `201 {"entityId":"<uuid>","reference":"4TAX-..."}`; identical retries return 200 with the original result. Both URLs also accept a trailing slash.

The owner token is issued by the existing auth service after phone/PIN registration or login. The API verifies its RS256 signature against the configured public JWKS, issuer, expiry, audience `registration-api`, `kind=owner`, UUID subject and `businesses:create` scope. Application tokens and web session cookies cannot authorize registration. Only this bearer endpoint is exempt from CSRF; web forms retain CSRF protection.

Example request (synthetic data):

```http
POST /api/v1/businesses
Authorization: Bearer <owner-access-token>
Idempotency-Key: <stable-operation-uuid>
Content-Type: application/json

{
  "sector": "retail",
  "owner": {"fullNames": "Example Owner", "idNumber": "0000123456"},
  "details": {
    "goods_type": "clothing",
    "other_description": "",
    "location": "Example market",
    "turnover_range": "1000_9999",
    "purchase_price_range": "100_499",
    "selling_price_range": "500_999"
  },
  "employees": [
    {"name": "Example Employee", "salary_range": "1000_9999"}
  ],
  "source": {"channel": "USSD", "language": "en"}
}
```

Use the options endpoint for each sector's exact field names and permitted values. `owner.fullNames` and `owner.idNumber`, `details`, `employees` and `source` are required for every sector. `businessName` is optional. National identity numbers must be strings to preserve leading zeros; they are self-reported, not verified with an identity authority. All registrations require location and monthly turnover. `other_description` is required when Other is selected.

Transport additionally requires `routes: [{"origin":"Example A","destination":"Example B","price":"25.50"}]`, a transport type, VIN, license plate and working hours. Services require service type, price range and hours. Working days are strings such as `Monday`; times use `HH:MM` and `overnight` is a boolean. Retail and e-commerce require purchase and selling price bands, with shipping/logistics also required for e-commerce.

Agriculture requires `livestock: [{"animal_type":"Sheep","number":5}]` (or `[]` when not applicable), activity, selling price range, `farmland_count`, `farmland_size` and `farmland_unit` (`hectares`, `acres`, `square_metres`). Count and size are separate inputs. Use zero for count and size when there is no land, with `farmland_unit` empty or omitted. Existing zero-land payloads containing a valid unit are still accepted. Positive land requires a valid unit; farming requires positive land details and livestock activity requires an animal entry. Exact decimals such as route prices and farmland size are strings in JSON.

Collections accept at most 50 rows. Send `employees: []` when there are no employees. USSD asks for each employee's name, then a salary menu, then offers Add another / Continue. Routes and livestock also repeat. Clear entries resets only that unsaved collection. Numeric zero is entered as `00` in USSD because `0` means Back.

Price/turnover bands: `below_100`, `100_499`, `500_999`, `1000_9999`, `10000_49999`, `50000_plus`. Monthly salary bands: `below_500`, `500_999`, `1000_9999`, `10000_19999`, `20000_plus`. Upper bands include M50,000 and M20,000 respectively. Ranges are categorical values, never converted to estimated amounts or ledger entries.

Errors have `{code, message, fields}`. Invalid JSON/key returns 400; invalid/missing JWT 401; missing owner kind/scope 403; changed payload for an existing retry key 409; invalid fields 422; oversized payload 413; wrong media type 415; unavailable keys/database or disabled configuration 503. Keep a stable key and payload across timeouts/5xx; do not start a new operation until the original result is resolved. Validation errors do not consume the key. The database uniqueness constraint scopes retries by verified issuer, owner subject and key.

## Identity and storage

`USSDRegistration` stores the registration payload against the external auth identity. It does not create a Django password account, attach an existing web workspace by phone/ID, or post bookkeeping transactions. A deliberate, verified account-linking flow is required before an external auth owner can use an existing web workspace. Multiple registrations per auth owner are supported.

Existing web profiles are not rewritten by the migration. When their owner saves the revised form, earlier operational details are retained under `previous_registration_details`; missing new fields must be completed.

## Configuration and rollout

1. Install requirements and run checks against a disposable test database.
2. After production database approval, apply `business_profiles.0002_ussdregistration` on Neon. It only adds the registration table and retry constraint.
3. Configure Django `REGISTRATION_AUTH_ISSUER=https://4tax-auth.vercel.app` and `REGISTRATION_AUTH_JWKS_URL=https://4tax-auth.vercel.app/oauth2/jwks`. These are public URLs; no auth private signing key is copied. Empty settings disable writes with 503.
4. Deploy Django and the updated USSD client together, then set USSD `REGISTRATION_URL=https://4tax.vercel.app` and redeploy USSD. The registration mock has been removed. Use the real API and its trusted hosted auth issuer. Old unfinished drafts must be discarded explicitly. Source defaults point to the hosted APIs; environment values configured on Vercel still take precedence.
5. Use an approved test identity for an end-to-end registration; do not run synthetic registration scripts against production without approval.

`python manage.py export_registration_schema` updates the checked-in Java menu resource from Django form metadata. `--check` checks for drift in CI. USSD does not fetch metadata on each screen, avoiding another network dependency in a short callback. Java auth remains responsible for PINs; PINs and bearer tokens are never included in registration payloads.

USSD navigation uses `8. Back`, `9. Continue`/Next/Confirm, `7. Skip` for optional answers, and `0. Exit`, each on its own line. Numeric eight and zero use `08` and `00` where a control is displayed. Weekday 7 is Sunday. Daytime hours derive `overnight=false`; overnight/24-hour work requires confirmation or corrected times.
