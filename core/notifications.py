def register_buckezz_topics() -> None:
    """Register Buckezz notification topics in notify_kit if installed."""
    try:
        from notify_kit.registry import register_notification_topic
    except Exception:
        return

    topics = [
        (
            "buckezz.reminder",
            "Fällige Listen-Erinnerungen",
            "Benachrichtigung, wenn ein Listen-Termin oder eine Erinnerung fällig ist.",
            "bi-alarm",
            True,
        ),
        (
            "buckezz.overdue",
            "Überfällige Einträge",
            "Hinweis bei überschrittenem Enddatum in Listen mit Überfälligkeits-Regel.",
            "bi-exclamation-triangle",
            True,
        ),
        (
            "buckezz.low_stock",
            "Niedriger Tracker-Bestand",
            "Warnung, wenn ein Tracker-Vorrat den Mindestbestand erreicht.",
            "bi-box-seam",
            True,
        ),
        (
            "buckezz.shared",
            "Freigaben, Zuweisungen & Reservierungen",
            "Meldung bei neuen Listen-Freigaben, Rollenwechseln oder Übernahmen.",
            "bi-people",
            True,
        ),
    ]
    for key, label, desc, icon, default_enabled in topics:
        try:
            register_notification_topic(
                key=key,
                label=label,
                description=desc,
                icon=icon,
                default_enabled=default_enabled,
            )
        except Exception:
            pass


def notify_user_safe(
    user,
    title: str,
    message: str = "",
    level: str = "info",
    link: str = "",
    topic: str = "",
    deduplicate_unread: bool = False,
):
    """Send an in-app notification via notify_kit if installed; fail silently otherwise."""
    if user is None or not getattr(user, "is_authenticated", True) or not getattr(user, "pk", None):
        return None
    try:
        from notify_kit.models import Notification
        from notify_kit.services import notify
    except Exception:
        return None

    try:
        if deduplicate_unread:
            qs = Notification.objects.filter(user=user, is_read=False)
            if topic:
                qs = qs.filter(topic=topic)
            if link:
                qs = qs.filter(link=link[:255])
            if qs.exists():
                return None
        return notify(
            user=user,
            title=title,
            message=message,
            level=level,
            link=link,
            topic=topic,
        )
    except Exception:
        return None
