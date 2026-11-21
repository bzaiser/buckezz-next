import threading

from django.db import models
from django.utils.text import slugify

_sync_local = threading.local()


def _is_syncing():
    return getattr(_sync_local, "active", False)


def _split_full_name(full_name: str):
    parts = (full_name or "").strip().split(None, 1)
    if not parts:
        return "Unbekannt", ""
    return parts[0][:80], (parts[1][:80] if len(parts) > 1 else "")


def sync_person_from_domain(domain_person, db_alias=None):
    """Ensure a core.Person exists and stays synced for a domain_kit.Person."""
    if not domain_person or not domain_person.pk or _is_syncing():
        return None
    from core.models import Person as CorePerson

    db = db_alias or domain_person._state.db or "default"
    full_name = (domain_person.full_name or "").strip() or f"Person #{domain_person.pk}"
    email = (domain_person.email or "").strip() or None
    phone = (domain_person.phone or domain_person.mobile or "").strip() or None
    notes = (domain_person.notes or "").strip() or None

    _sync_local.active = True
    try:
        cp = CorePerson.objects.using(db).filter(domain_person_id=domain_person.pk).first()
        if not cp and domain_person.user_id:
            cp = CorePerson.objects.using(db).filter(user_id=domain_person.user_id, domain_person__isnull=True).first()
        if not cp and email:
            cp = CorePerson.objects.using(db).filter(email__iexact=email, domain_person__isnull=True).first()
        if not cp:
            cp = CorePerson.objects.using(db).filter(name__iexact=full_name, domain_person__isnull=True).first()

        if cp:
            changed = []
            if cp.domain_person_id != domain_person.pk:
                cp.domain_person_id = domain_person.pk
                changed.append("domain_person")
            if cp.name != full_name:
                cp.name = full_name[:255]
                changed.append("name")
            if email and cp.email != email:
                cp.email = email
                changed.append("email")
            if phone and cp.phone != phone:
                cp.phone = phone[:50]
                changed.append("phone")
            if domain_person.birth_date and cp.birth_date != domain_person.birth_date:
                cp.birth_date = domain_person.birth_date
                changed.append("birth_date")
            if notes and not cp.notes:
                cp.notes = notes
                changed.append("notes")
            if changed:
                cp.save(using=db, update_fields=changed)
            return cp

        # Avoid violating unique user constraint on core.Person.user
        user_id = None
        if domain_person.user_id and not CorePerson.objects.using(db).filter(user_id=domain_person.user_id).exists():
            user_id = domain_person.user_id

        return CorePerson.objects.using(db).create(
            name=full_name[:255],
            email=email,
            phone=phone[:50] if phone else None,
            birth_date=domain_person.birth_date,
            notes=notes,
            user_id=user_id,
            domain_person_id=domain_person.pk,
        )
    except Exception:
        return None
    finally:
        _sync_local.active = False


def sync_person_to_domain(core_person, db_alias=None):
    """Ensure a domain_kit.Person exists and stays linked for a core.Person."""
    if not core_person or not core_person.pk or _is_syncing():
        return None
    try:
        from domain_kit.models import Person as DomainPerson
    except ImportError:
        return None

    db = db_alias or core_person._state.db or "default"
    full_name = (core_person.name or "").strip()
    if not full_name:
        return None
    first_name, last_name = _split_full_name(full_name)
    email = (core_person.email or "").strip()
    phone = (core_person.phone or "").strip()

    _sync_local.active = True
    try:
        if core_person.domain_person_id:
            dp = DomainPerson.objects.using(db).filter(pk=core_person.domain_person_id).first()
            if dp:
                changed = []
                if dp.full_name != full_name:
                    dp.first_name = first_name
                    dp.last_name = last_name
                    dp.display_name = full_name[:140]
                    changed.extend(["first_name", "last_name", "display_name"])
                if email and not dp.email:
                    dp.email = email[:140]
                    changed.append("email")
                if phone and not dp.phone:
                    dp.phone = phone[:60]
                    changed.append("phone")
                if core_person.birth_date and not dp.birth_date:
                    dp.birth_date = core_person.birth_date
                    changed.append("birth_date")
                if changed:
                    dp.save(using=db, update_fields=changed)
                return dp

        # Try matching existing unlinked DomainPerson first
        dp = None
        if core_person.user_id:
            dp = DomainPerson.objects.using(db).filter(user_id=core_person.user_id, buckezz_person__isnull=True).first()
        if not dp and email:
            dp = DomainPerson.objects.using(db).filter(email__iexact=email, buckezz_person__isnull=True).first()
        if not dp:
            dp = DomainPerson.objects.using(db).filter(
                models.Q(display_name__iexact=full_name)
                | (models.Q(first_name__iexact=first_name) & models.Q(last_name__iexact=last_name)),
                buckezz_person__isnull=True,
            ).first()

        if not dp:
            dp = DomainPerson.objects.using(db).create(
                first_name=first_name,
                last_name=last_name,
                display_name=full_name[:140],
                email=email[:140],
                phone=phone[:60],
                birth_date=core_person.birth_date,
                notes=(core_person.notes or "")[:2000],
                user_id=core_person.user_id,
            )

        from core.models import Person as CorePerson
        CorePerson.objects.using(db).filter(pk=core_person.pk).update(domain_person_id=dp.pk)
        core_person.domain_person_id = dp.pk
        return dp
    except Exception:
        return None
    finally:
        _sync_local.active = False


def sync_all_persons(db_alias="default"):
    """Bidirectionally link all existing domain_kit.Person <-> core.Person records."""
    from core.models import Person as CorePerson
    try:
        from domain_kit.models import Person as DomainPerson
    except ImportError:
        return 0, 0

    from_domain = 0
    for dp in DomainPerson.objects.using(db_alias).all():
        existed = CorePerson.objects.using(db_alias).filter(domain_person_id=dp.pk).exists()
        cp = sync_person_from_domain(dp, db_alias=db_alias)
        if cp and not existed:
            from_domain += 1

    to_domain = 0
    for cp in CorePerson.objects.using(db_alias).filter(domain_person__isnull=True):
        dp = sync_person_to_domain(cp, db_alias=db_alias)
        if dp:
            to_domain += 1

    return from_domain, to_domain


def attach_domain_styles(tpl, items):
    """Pre-attach status & role styles from domain_kit to avoid N+1 queries in list rendering."""
    if not items:
        return
    try:
        eff_statuses = tpl.get_effective_statuses()
        status_by_key = {s.get("key"): s for s in eff_statuses if isinstance(s, dict) and s.get("key")}
        eff_roles = tpl.get_effective_roles()
        role_by_key = {r.get("key"): r for r in eff_roles if isinstance(r, dict) and r.get("key")}

        db_alias = items[0]._state.db or "default"
        from domain_kit.models import Status as DomainStatus, Role as DomainRole
        ds_by_key = {}
        for ds in DomainStatus.objects.using(db_alias).all().order_by("position", "id"):
            accent = ds.custom_color or f"var(--theme-state-{ds.color_state}, var(--app-primary, #0d6efd))"
            info = {
                "key": slugify(ds.name).replace("-", "_")[:20] or f"st_{ds.id}",
                "label": ds.name,
                "completes": bool(ds.is_final),
                "color_state": ds.color_state,
                "custom_color": ds.custom_color,
                "icon": ds.icon,
                "badge_style": ds.badge_style,
                "accent_color": accent,
            }
            ds_by_key[info["key"]] = info
            ds_by_key[ds.name.strip().lower()] = info

        dr_style_by_key = {}
        for dr in DomainRole.objects.using(db_alias).all():
            dr_style_by_key[dr.name.strip().lower()] = dr.badge_style
            skey = slugify(dr.name).replace("-", "_")[:20]
            if skey:
                dr_style_by_key[skey] = dr.badge_style
    except Exception:
        return

    has_custom_statuses = bool(tpl.allowed_statuses_json)
    for it in items:
        st_info = None
        if has_custom_statuses or tpl.use_status:
            cand = status_by_key.get(it.status)
            if cand:
                if not has_custom_statuses and it.status in ("active", "open") and not it.is_completed:
                    st_info = None
                else:
                    st_info = dict(cand)
        if st_info is None and it.status in ("waiting", "overdue"):
            st_info = {"key": it.status, "label": it.get_status_display(), "completes": False}
        if st_info is None and it.status not in ("active", "open", "done"):
            cand = ds_by_key.get(it.status) or ds_by_key.get(str(it.status).lower())
            if cand:
                st_info = dict(cand)
        if st_info and not st_info.get("badge_style"):
            match = ds_by_key.get(str(st_info.get("label", "")).strip().lower()) or ds_by_key.get(st_info.get("key"))
            if match:
                st_info["color_state"] = match["color_state"]
                st_info["custom_color"] = match["custom_color"]
                st_info["icon"] = match["icon"]
                st_info["badge_style"] = match["badge_style"]
                st_info["accent_color"] = match["accent_color"]
        it._cached_status_info = st_info

        for pr in it.person_roles.all():
            r_meta = role_by_key.get(pr.role)
            lbl = (r_meta.get("label") if r_meta else None) or pr.get_role_display()
            pr._cached_role_label = lbl
            pr._cached_role_style = (
                (r_meta.get("badge_style") if r_meta else None)
                or dr_style_by_key.get(lbl.strip().lower())
                or dr_style_by_key.get(pr.role)
                or ""
            )


def connect_domain_sync_signals():
    from django.db.models.signals import post_save
    from core.models import Person as CorePerson

    def _on_core_person_saved(sender, instance, **kwargs):
        if kwargs.get("raw"):
            return
        sync_person_to_domain(instance, db_alias=kwargs.get("using") or instance._state.db)

    post_save.connect(_on_core_person_saved, sender=CorePerson, dispatch_uid="buckezz_sync_core_to_domain_person")

    try:
        from domain_kit.models import Person as DomainPerson

        def _on_domain_person_saved(sender, instance, **kwargs):
            if kwargs.get("raw"):
                return
            sync_person_from_domain(instance, db_alias=kwargs.get("using") or instance._state.db)

        post_save.connect(_on_domain_person_saved, sender=DomainPerson, dispatch_uid="buckezz_sync_domain_to_core_person")
    except Exception:
        pass
