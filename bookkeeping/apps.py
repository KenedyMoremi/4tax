from django.apps import AppConfig


class BookkeepingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'bookkeeping'
    # Existing database tables, content types and migrations use this label.
    label = 'books'
    verbose_name = 'Bookkeeping'
