# finances/apps.py
from django.apps import AppConfig

class FinancesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'finances'

    def ready(self):
        # import signals to register them
        import finances.signals  # noqa
