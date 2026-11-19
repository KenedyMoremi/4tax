# Deploy 4Tax through GitHub to Vercel

Use a personal GitHub repository for a Hobby deployment. Vercel's [Hobby rules](https://vercel.com/docs/limits/fair-use-guidelines) restrict that plan to personal/non-commercial use. A learning or personal demo may qualify; live commercial use needs a suitable plan. This configuration does not select, upgrade, or purchase any plan.

## Repository and deployment

1. Push this project to its own GitHub repository. Private is appropriate. `.env`, local databases, `.venv`, and generated deployment files are excluded. Never paste credentials into a commit or README.
2. In the intended Vercel account, choose **Add New → Project**, import the GitHub repository, and use the **Django** framework preset. The project root is the repository root.
3. Set environment variables below before the first deployment. Enable Vercel's automatically exposed system environment variables so the exact deployment hostname is available.
4. Deploy. Vercel reads `.python-version` (3.14), installs `requirements.txt`, runs `scripts/vercel_build.py`, collects Django static files, and serves them from its CDN. The build compiles Tailwind and runs deployment checks. In production only, it then runs the approved, scoped USSD schema release command. It never seeds data or runs general migrations. Preview builds do not migrate.
5. The supplied Neon database has already been migrated. The approved USSD transaction release uses `python manage.py apply_ussd_schema` inside the production build, using Vercel’s configured `DATABASE_URL`. It serializes concurrent builds with a transaction-scoped PostgreSQL lock and commits DDL/history atomically. It applies only `business_profiles.0003_ussd_transactions` and known additive profile/registration/proposal prerequisites if pending; other migration plans stop the release. Already-applied targets are skipped, so later schema versions are never downgraded. Other future schema changes still require a separate controlled rollout. Do not run migrations against production from pull-request builds.
6. Verify `/accounts/login/`, create a business, and exercise an invoice/payment flow. Check that `/static/` serves fingerprinted CSS and JS. The empty Neon database does not contain the local SQLite demo account.
7. Subsequent pushes to the production branch redeploy through Vercel's GitHub integration. CI runs tests separately; if required, configure Vercel checks or branch protection to prevent deployment of failing changes.

## Environment variables

| Variable | Value / purpose |
| --- | --- |
| `DATABASE_URL` | The active Neon connection string from the local private `.env`. Keep `sslmode=require&channel_binding=require`. Set as a sensitive variable. |
| `DJANGO_SECRET_KEY` | A new, long random production secret. Keep stable across deployments. Set as a sensitive variable. |
| `DJANGO_DEBUG` | `0`; hosted Vercel settings force it off regardless. |
| `DJANGO_ALLOWED_HOSTS` | Optional comma-separated custom domains. Exact Vercel deployment/production hostnames are detected from system environment variables. Do not use `*`. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Optional custom origins, e.g. `https://books.example.com`. Exact Vercel origins are added automatically. |

Use separate database credentials or a Neon branch for Preview deployments; do not give untrusted PR builds access to live customer data. If previews have no `DATABASE_URL`, the build deliberately fails rather than falling back to temporary SQLite storage.

Do not copy the local `.env` into GitHub or the deployment bundle. Supply its values through Vercel's encrypted environment-variable settings or an authenticated deployment integration. Never put secrets in `vercel.json`.

## Hosting behavior

The existing `config.wsgi:application` is the server entrypoint. `vercel.json` selects Django and a 60-second function limit. Runtime state is held in Neon, not the read-only/ephemeral function filesystem. Django sessions use the database. The app has no uploaded-file storage requirement.

Only when `VERCEL=1` does Django trust Vercel's `X-Forwarded-Proto` header. This avoids HTTPS redirect loops and preserves secure cookies and CSRF origin checks. Production static files use hashed names through Django's `ManifestStaticFilesStorage`.

Current official references:

- [Django deployment and automatic static files](https://vercel.com/docs/frameworks/full-stack/django)
- [Supported Python versions](https://vercel.com/docs/functions/runtimes/python)
- [Forwarded request headers](https://vercel.com/docs/headers/request-headers)
- [Hobby plan usage rules](https://vercel.com/docs/limits/fair-use-guidelines)
