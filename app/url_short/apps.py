from django.apps import AppConfig


class UrlShortConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'url_short'

    def ready(self):
        from . import signals  # noqa: F401
