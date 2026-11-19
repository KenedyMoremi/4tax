from django.core.exceptions import ImproperlyConfigured
from psycopg.conninfo import conninfo_to_dict


def database_config(url, sqlite_path):
    if not url:
        return {'ENGINE': 'django.db.backends.sqlite3', 'NAME': sqlite_path,
                'OPTIONS': {'timeout': 20, 'transaction_mode': 'IMMEDIATE'}}
    if not url.startswith(('postgresql://', 'postgres://')):
        raise ImproperlyConfigured('DATABASE_URL must be a PostgreSQL connection URL.')
    try:
        parameters = conninfo_to_dict(url)
    except Exception:
        # Connection strings contain credentials; never include them in errors.
        raise ImproperlyConfigured('DATABASE_URL is not a valid PostgreSQL connection URL.') from None
    fields = {key: parameters.pop(value, '') for key, value in {
        'NAME': 'dbname', 'USER': 'user', 'PASSWORD': 'password', 'HOST': 'host', 'PORT': 'port'
    }.items()}
    if not fields['NAME'] or not fields['HOST']:
        raise ImproperlyConfigured('DATABASE_URL must include a database name and host.')
    parameters.setdefault('sslmode', 'require')
    parameters.setdefault('connect_timeout', '10')
    return {'ENGINE': 'django.db.backends.postgresql', **fields, 'OPTIONS': parameters,
            'CONN_MAX_AGE': 0, 'DISABLE_SERVER_SIDE_CURSORS': True}
