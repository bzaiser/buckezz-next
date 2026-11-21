from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = 'core'

    def ready(self):
        from core.domain_sync import connect_domain_sync_signals
        connect_domain_sync_signals()
