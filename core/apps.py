from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = 'core'

    def ready(self):
        from core.domain_sync import connect_domain_sync_signals
        from core.notifications import register_buckezz_topics
        connect_domain_sync_signals()
        register_buckezz_topics()
