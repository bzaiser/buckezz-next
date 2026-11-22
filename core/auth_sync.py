from django.apps import apps as django_apps
from django.db.models.signals import post_save


def get_app_settings_context(request) -> dict:
    """Provide Buckezz-specific UserSetting and Person objects for auth_kit's App-Einstellungen tab."""
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return {}
    from core.models import Person, UserSetting

    user_setting, _ = UserSetting.objects.get_or_create(user=user)
    person, _ = Person.objects.get_or_create(user=user, defaults={"name": user.username})
    return {
        "settings": user_setting,
        "person": person,
    }


def _sync_auth_profile_to_buckezz(sender, instance, **kwargs):
    user = getattr(instance, "user", None)
    if user is None:
        return
    db_alias = getattr(instance._state, "db", None) or "default"
    from core.models import Person, UserSetting

    display = (instance.display_name or user.get_full_name() or user.username or "").strip()[:100]
    person, _ = Person.objects.using(db_alias).get_or_create(user=user, defaults={"name": display or user.username})
    changed_person = False
    if display and person.name != display:
        person.name = display
        changed_person = True
    email_val = (user.email or "").strip() or None
    if person.email != email_val:
        person.email = email_val
        changed_person = True
    phone_val = (instance.phone or "").strip()[:50] or None
    if person.phone != phone_val:
        person.phone = phone_val
        changed_person = True
    if changed_person:
        person.save(using=db_alias)

    tz_val = (instance.timezone or "").strip()
    if tz_val:
        us, _ = UserSetting.objects.using(db_alias).get_or_create(user=user)
        if us.timezone != tz_val:
            us.timezone = tz_val
            us.save(using=db_alias, update_fields=["timezone"])


def connect_auth_sync_signals() -> None:
    if not django_apps.is_installed("auth_kit"):
        return
    try:
        from auth_kit.models import UserProfile
        post_save.connect(
            _sync_auth_profile_to_buckezz,
            sender=UserProfile,
            dispatch_uid="buckezz_sync_auth_kit_profile",
        )
    except Exception:
        pass
