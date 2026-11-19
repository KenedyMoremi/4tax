# Django repository instructions

Apply these instructions throughout the repository. Follow more specific instructions in the directories you edit.

## Before making changes

- Read the README, dependency files, settings, CI configuration, and nearby code and tests relevant to the task. Use the project's declared Python and Django versions and its existing package manager, formatter, linter, and test runner.
- Preserve unrelated work. Keep changes focused and reuse existing Django features and project conventions. Add a dependency only when it solves a concrete need that the existing stack cannot reasonably meet.
- For a new project, settle the user model before the first migration. If the project needs a custom user model, configure `AUTH_USER_MODEL` before applying migrations. Reference the configured user model with `settings.AUTH_USER_MODEL` in relationships and `get_user_model()` when resolving the model at runtime.

## Application design

- Organize apps around cohesive business domains. Use clear names, standard Django conventions, and straightforward code. Introduce abstractions when they simplify a real use case.
- Keep request handlers focused on parsing input, enforcing access, invoking the operation, and returning a response. Validate request data with Django forms or, if the project uses Django REST Framework, serializers. Put reusable business rules near the data they govern and give multi-step operations an explicit callable. Keep critical workflows out of implicit signals where practical.
- Preserve existing routes, response formats, and behavior unless the task calls for a change. Use named URLs and reverse lookups. In DRF, declare writable and read-only fields explicitly, scope list querysets, and check authorization on detail and write operations.
- Use timezone-aware datetimes and `Decimal` for monetary calculations. Apply explicit rounding where the business rules require it.

## Data and migrations

- Use database constraints for invariants the database can enforce, including uniqueness. Use `transaction.atomic()` for writes that must succeed together. Protect concurrent updates with database constraints, conditional updates, or row locks as appropriate. Make retried jobs and webhook handlers idempotent where duplicate execution can cause harm.
- When external work depends on committed data, trigger it after commit. Use a durable outbox or equivalent when the operation requires guaranteed delivery across failures.
- Use the ORM by default. Check query patterns on list, report, and bulk paths. Use `select_related()` for joins to single-valued relations and `prefetch_related()` for collections when they prevent repeated queries. Paginate unbounded results and add indexes that match demonstrated query needs.
- Commit model changes with their migrations. Inspect generated operations and preserve migrations that may already have been applied. Use historical models through `apps.get_model()` in data migrations and the database alias from `schema_editor.connection.alias` for writes.
- Plan backfills, locking, and rollout order when changing populated tables. Stage changes when old and new application versions need to coexist. Flag irreversible operations and verify migration behavior against a disposable database. Obtain confirmation before running destructive or production database operations.

## Security and configuration

- Keep credentials and signing keys in environment variables or the project's secret manager. Use placeholders in example configuration. Keep secrets, tokens, and personal data out of source, fixtures, logs, and client-facing errors.
- Enforce authorization on the server. Scope queries to authorized objects before listing, searching, exporting, updating, or deleting. For multi-tenant features, derive tenant scope from verified membership and test cross-tenant access.
- Preserve CSRF protection for browser requests and template autoescaping. Use Django's authentication and password APIs. Validate file uploads, enforce size limits, and restrict access to private files. Use parameterized queries when raw SQL is necessary.
- Validate third-party callbacks with the provider's signing mechanism before processing them. Set explicit timeouts for outbound calls and handle failures without exposing sensitive data.
- Use production-appropriate settings for `DEBUG`, allowed hosts, HTTPS, and secure cookies. Run Django's deployment checks with production-like settings when changing deployment or security configuration.

## Tests and completion

- Add focused tests for new behavior and regressions existing tests would miss. Exercise the real entry point for changes involving permissions, validation, or response contracts. Cover relevant failure paths and use the production database engine when testing database-specific behavior.
- Run the repository's documented checks and targeted tests first, then broader checks as appropriate. Use isolated test settings and prevent real network calls or side effects in automated tests.
- For a standard Django setup, use `python manage.py check`, `python manage.py makemigrations --check --dry-run`, and `python manage.py test` where applicable. Use the configured runner instead if the repository uses another tool. For deployment checks, run `python manage.py check --deploy` with the appropriate settings.
- Review the final diff for scope and correctness. Report what changed, which checks ran and their outcomes, and any migration, configuration, or deployment steps the user needs to take.
