# Business recommendations

Owners open **Recommendations** in the workspace sidebar at /recommendations/.
The page displays an aggregate snapshot of their own records. After checking the
consent box and selecting Generate recommendations, Groq returns up to four
prioritised actions, each with supporting metrics, a next step and a way to measure
progress. The page works for every sector.

The agent compares the last 30 calendar days (including today) with the preceding
30 days. It uses recorded revenue, expenses, surplus/deficit, current cash,
receivable/payable balances and journal-entry counts. Services also include
completed/cancelled/no-show appointment counts; other registered sectors include
active tracked-item and out-of-stock counts. Counts are not treated as revenue.
No recent ledger entries means no provider call; owners are prompted to record
activity first.

Only sector, dates, allowlisted aggregate metrics and reporting limitations are
sent to Groq. The snapshot excludes business/owner names, identity numbers,
contacts, addresses, credentials, raw transaction descriptions and profile JSON.
The agent cannot change records, send messages, initiate payments or browse.
Output is schema-validated, evidence keys must belong to the supplied snapshot,
and rendered text remains HTML-escaped. Private responses are marked no-store.
Plans are displayed for the current request, not saved in the database.

Configuration:
- GROQ_RECOMMENDATIONS_API_KEY: separate recommendations-only Groq key.
- GROQ_RECOMMENDATIONS_MODEL: defaults to openai/gpt-oss-120b.

The agent never falls back to GROQ_API_KEY used by bookkeeping interpretation.
The provider call has a 20-second timeout, no automatic retries, a 2,400-token
output limit, and requires an authenticated owner POST with CSRF and consent.
Provider errors return a generic message without leaking details or credentials.
The app does not enforce an account-wide provider spending quota; manage usage
limits in the Groq account.

Recommendations depend on recorded data and do not forecast profit, measure market
demand or compute inventory-adjusted margins. They require owner review.

Validation: python manage.py test recommendations. Provider calls are mocked in
automated tests; tenant isolation, consent, CSRF, unavailable providers, separate
credentials and invalid model evidence are covered. No migration is required.
