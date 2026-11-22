from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = 'core'

    def ready(self):
        from core.auth_sync import connect_auth_sync_signals
        from core.domain_sync import connect_domain_sync_signals
        from core.notifications import register_buckezz_topics
        connect_auth_sync_signals()
        connect_domain_sync_signals()
        register_buckezz_topics()
