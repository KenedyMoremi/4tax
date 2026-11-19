# WhatsApp bookkeeping: Groq + Twilio Sandbox

The owner sends a text record to Twilio WhatsApp. Groq extracts a structured draft; Django validates its accounts, amounts, dates and business ownership. The owner reviews the preview and replies `CONFIRM <code>` before existing bookkeeping services create balanced ledger entries. `CANCEL <code>` discards the draft. Drafts expire after 30 minutes and can also be reviewed in **Agent records** in the app.

Supported: paid expenses, paid sales, unpaid sales invoices, purchase bills and payments against an existing invoice/bill number. `SUMMARY` returns this month's posted revenue, expenses and profit without calling AI. `HELP` explains the commands. Text only; attachments, receipt images and voice notes are not downloaded or processed. Each message must contain one complete transaction; corrections require a new complete instruction. No conversation history is sent to the AI provider.

## Configuration

Install `requirements.txt`. Configure secrets in the ignored local `.env` or the hosting secret manager; never commit them or paste them into source.

```dotenv
WHATSAPP_ENABLED=1
TWILIO_ACCOUNT_SID=AC_REPLACE_WITH_ACCOUNT_SID
TWILIO_AUTH_TOKEN=REPLACE_WITH_AUTH_TOKEN
TWILIO_WHATSAPP_FROM=whatsapp:+REPLACE_WITH_SANDBOX_NUMBER
TWILIO_WEBHOOK_URL=https://4tax.vercel.app/webhooks/twilio/whatsapp/
BOOKKEEPING_AI_PROVIDER=groq
GROQ_API_KEY=REPLACE_WITH_API_KEY
GROQ_BOOKKEEPING_MODEL=openai/gpt-oss-120b
WHATSAPP_LINK_SECRET=REPLACE_WITH_LONG_RANDOM_SECRET
```

Use the exact Sandbox sender number from Twilio Console. Use the account SID/auth token for that Sandbox. The webhook URL must exactly match Twilio's configured URL (including scheme, hostname, path and trailing slash). The application verifies Twilio's signature, account and destination. A local development tunnel needs its hostname in `DJANGO_ALLOWED_HOSTS` and correctly configured HTTPS handling; never disable signature verification to troubleshoot a tunnel.

Apply the additive migrations (`books.0003_recordproposal`, `whatsapp.0001_initial` and `whatsapp.0002_whatsapplink_ai_provider`) before switching web/worker processes to this release:

```sh
python manage.py migrate --plan
python manage.py migrate
```

For an existing production database, obtain the operator's approval first and confirm backups. The changes add tables and a provider-consent field; they do not rename existing bookkeeping tables or change historical migrations. Migrations have been exercised on disposable SQLite, not the live Neon database.

## Vercel and the worker

Vercel receives and validates callbacks, stores them durably in PostgreSQL, and responds immediately. AI calls and outgoing replies run in a **separate long-running Django worker**:

```sh
python manage.py process_whatsapp
# For a bounded processing pass:
python manage.py process_whatsapp --once --limit 10
```

For Sandbox testing, run this command on your computer using the same Neon `DATABASE_URL` as the web application and the same dedicated `WHATSAPP_LINK_SECRET`, together with the provider variables above. Linking-code hashes use that dedicated secret; the worker does not need the production Django signing key. If the dedicated secret is omitted, the legacy fallback uses the Django secret. Changing either active link secret invalidates unverified codes. Keep the computer and process running while testing. For continuous availability, deploy the command to a persistent worker host with process supervision. Vercel Hobby does not run this persistent process; this implementation does not use threads after an HTTP response or promise instant replies without a worker. Groq and Twilio usage are billed independently of Vercel hosting.

The web process needs the Twilio settings and enabled flag. The Groq key is required only on the worker. `BOOKKEEPING_AI_PROVIDER` must match in the web and worker environments. OpenAI remains available by selecting `openai` and setting `OPENAI_API_KEY` and `OPENAI_BOOKKEEPING_MODEL`. Provider changes require owners to relink their numbers and consent again. Restart the worker after code/configuration changes. Run exactly one worker for the Sandbox: sends are spaced at least three seconds apart using persisted attempt times. Claims and business-level transactions protect concurrent processing, but production PostgreSQL concurrency should be exercised on a disposable database before scaling workers; a shared sender-rate lock would also be needed.

## Join and link

1. In Twilio’s legacy Console, activate the WhatsApp Sandbox and follow its participant join instructions on the owner's phone. Sandbox membership expires after three days, so rejoin when needed. This Sandbox join code is separate from the application's linking code.
2. Set **When a message comes in** to the exact public webhook URL above with method **POST**. Deploy the application/migrations and start the worker first.
3. Sign into the app, open **WhatsApp**, enter the international phone number (for example `+266…`), accept the processing consent and generate a linking code.
4. Send `LINK <code>` to the Sandbox number within ten minutes. Codes are shown once, stored as keyed hashes, and limited to five attempts. A number belongs to one workspace; verification binds it to the signed-in owner.
5. Send `Paid M250 for transport from M-Pesa today`. Review the amount, date, category and payment account. Confirm using the code in the reply, then check Expenses and General ledger.
6. Test `SUMMARY`, cancellation, an incomplete instruction, and a payment against a document number. State VAT percentage and whether the amount includes VAT if tax applies. Without VAT wording the preview explicitly shows zero VAT; the owner must verify that treatment.

Disconnecting or generating a new linking code invalidates queued work and cancels pending WhatsApp proposals. To move a number to a different workspace, the existing owner can first replace their linked number; an administrator can resolve ownership disputes after verifying identity.

## Reliability and operations

Incoming Twilio message SIDs are unique. Retried callbacks do not create duplicate jobs, and repeated confirmation of the same proposal returns its original result. Financial posting, proposal status and the outgoing response are committed atomically. This protects retries of the same message/proposal; sending the same transaction again as a new message and confirming a new proposal can still create a second record.

AI failures retry up to three times with a delay. Replies are stored in an outbox. Send attempts have a bounded timeout and no automatic transport retries. If a send times out, or a worker crashes during a send, its status becomes **Delivery uncertain**. Do not automatically resend: Twilio may already have accepted it. Inspect the Twilio message log and the Agent records screen first. An owner can inspect/confirm a pending preview in the web app even if its reply was lost. There is no delivery-status callback in this version; **Accepted by Twilio** means API acceptance, not handset delivery.

Replies older than 23 hours are expired conservatively to remain inside WhatsApp's customer-service window. This implementation sends no business-initiated template messages. Reconnect the worker promptly if messages remain queued. Recent processing/reply states are visible to the owner on the WhatsApp page. Unexpected worker errors should be investigated by an operator before restarting; do not log raw messages, phone numbers, tokens or provider error payloads.

The database retains inbound text, replies and proposals for private audit/review. No automatic deletion policy is configured. Restrict database access and backups and define retention before broader rollout. The selected AI provider receives the submitted text, message date, currency and chart account names/codes. Groq uses strict JSON-schema Chat Completions; the optional OpenAI adapter uses Responses with `store=False`. Provider retention policies still apply. It is not given database credentials, other businesses' records, SQL execution or posting tools.

## Validation and references

Tests use an isolated database and mocked providers; no paid AI calls or WhatsApp messages are sent by the test suite. Run `python manage.py test`, `python manage.py check`, `python manage.py makemigrations --check --dry-run`, and `python bookkeeping/scripts/check_concurrency.py`.

- [Twilio webhook security](https://www.twilio.com/docs/usage/webhooks/webhooks-security)
- [Twilio WhatsApp Sandbox](https://www.twilio.com/docs/whatsapp/sandbox)
- [Groq structured outputs](https://console.groq.com/docs/structured-outputs)
- [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
