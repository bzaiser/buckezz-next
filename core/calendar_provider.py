from datetime import datetime, timedelta, timezone as dt_timezone
import re

from django.db import models
from django.urls import reverse
from django.utils import timezone

_LOGIC_ICONS = {
    "todo": "bi-check2-square",
    "event": "bi-calendar-event",
    "tracker": "bi-arrow-repeat",
    "bucket": "bi-stars",
    "gift": "bi-gift",
    "workout": "bi-activity",
    "nutrition": "bi-heart-pulse",
}

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _iso_local(dt):
    if not dt:
        return None
    return timezone.localtime(dt).isoformat() if timezone.is_aware(dt) else dt.isoformat()


def _resolve_icon(item, default_bi="bi-card-checklist"):
    cat = getattr(item.bucket_list, "category", None)
    raw = (getattr(cat, "icon", "") or "").strip()
    if raw:
        return raw
    tpl = getattr(cat, "template", None) if cat else None
    logic = getattr(tpl, "logic_type", "") if tpl else ""
    return _LOGIC_ICONS.get(logic, default_bi)


def _get_user_lists(user):
    from core.models import BucketList

    if user.is_superuser:
        return BucketList.objects.all()
    return BucketList.objects.filter(
        models.Q(owner=user) | models.Q(shared_with=user)
    ).distinct()


def _extract_custom_date_entries(item):
    """Return list of (key, label, YYYY-MM-DD) for populated custom date fields on item."""
    cf_data = item.custom_data_json
    if not isinstance(cf_data, dict) or not cf_data:
        return []
    cat = getattr(item.bucket_list, "category", None)
    tpl = getattr(cat, "template", None) if cat else None
    fields = getattr(tpl, "custom_fields_json", None) if tpl else None
    if not isinstance(fields, list) or not fields:
        return []

    out = []
    for f in fields:
        if not isinstance(f, dict) or f.get("type") != "date":
            continue
        key = f.get("key")
        if not key:
            continue
        val = str(cf_data.get(key) or "").strip()
        if _ISO_DATE_RE.match(val):
            out.append((key, (f.get("label") or key).strip(), val))
    return out


def get_buckezz_calendar_events(request, window_start, window_end):
    """
    Event-Provider für cal_kit: Liefert alle Aufgaben (To-Dos), Termine,
    Erinnerungen, Tracker-Routinen und benutzerdefinierte Datumsfelder
    aus Buckezz Listen für den eingeloggten Benutzer.
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return []

    from core.models import ListItem, ListTemplate

    lists = _get_user_lists(user)

    # Templates that define at least one custom 'date' field
    date_cf_cat_ids = [
        tpl.category_id
        for tpl in ListTemplate.objects.only("category_id", "custom_fields_json")
        if isinstance(tpl.custom_fields_json, list)
        and any(isinstance(f, dict) and f.get("type") == "date" for f in tpl.custom_fields_json)
    ]

    date_filter = (
        models.Q(start_date__isnull=False)
        | models.Q(end_date__isnull=False)
        | models.Q(reminder_at__isnull=False)
        | (models.Q(tracker_times__isnull=False) & ~models.Q(tracker_times=""))
    )
    if date_cf_cat_ids:
        date_filter |= models.Q(bucket_list__category_id__in=date_cf_cat_ids) & ~models.Q(custom_data_json={})

    items = (
        ListItem.objects.filter(bucket_list__in=lists)
        .filter(date_filter)
        .select_related("bucket_list", "bucket_list__category", "bucket_list__category__template")
    )

    events = []
    for item in items:
        list_url = reverse("core:list_detail", args=[item.bucket_list.id])
        icon = _resolve_icon(item)

        base_ext = {
            "master_id": f"buckezz_{item.id}",
            "source": "buckezz",
            "read_only": True,
            "listName": item.bucket_list.title,
            "location": item.location or "",
            "has_location": bool(item.location),
            "description": item.notes or "",
            "completed": item.is_completed,
            "all_day": False,
        }

        # 1. Start- und Enddatum (gültige Zeitspanne)
        if item.start_date and item.end_date and item.end_date >= item.start_date:
            events.append({
                "id": f"buckezz-range-{item.id}",
                "title": item.title,
                "start": _iso_local(item.start_date),
                "end": _iso_local(item.end_date),
                "allDay": False,
                "editable": False,
                "url": list_url,
                "backgroundColor": "var(--app-primary, #6366f1)",
                "borderColor": "var(--app-primary, #6366f1)",
                "extendedProps": {
                    **base_ext,
                    "event_type": "range",
                    "color_state": 1,
                    "icon": icon,
                    "is_reminder": False,
                },
            })
        else:
            # 2. Startdatum
            if item.start_date:
                events.append({
                    "id": f"buckezz-start-{item.id}",
                    "title": f"{item.title} (Start)",
                    "start": _iso_local(item.start_date),
                    "allDay": False,
                    "editable": False,
                    "url": list_url,
                    "backgroundColor": "var(--theme-state-2, #3b82f6)",
                    "borderColor": "var(--theme-state-2, #3b82f6)",
                    "extendedProps": {
                        **base_ext,
                        "event_type": "start",
                        "color_state": 2,
                        "icon": icon,
                        "is_reminder": False,
                    },
                })
            # 3. Fälligkeitsdatum (Endtermin / To-Do)
            if item.end_date:
                color = "var(--theme-state-4, #22c55e)" if item.is_completed else "var(--theme-state-5, #ef4444)"
                events.append({
                    "id": f"buckezz-end-{item.id}",
                    "title": item.title,
                    "start": _iso_local(item.end_date),
                    "allDay": False,
                    "editable": False,
                    "url": list_url,
                    "backgroundColor": color,
                    "borderColor": color,
                    "extendedProps": {
                        **base_ext,
                        "event_type": "end",
                        "color_state": 4 if item.is_completed else 5,
                        "icon": "bi-check2-square" if not icon.startswith("bi-") else icon,
                        "is_reminder": False,
                    },
                })

        # 4. Erinnerung (Reminder)
        if item.reminder_at:
            events.append({
                "id": f"buckezz-rem-{item.id}",
                "title": f"{item.title} (Erinnerung)",
                "start": _iso_local(item.reminder_at),
                "allDay": False,
                "editable": False,
                "url": list_url,
                "backgroundColor": "var(--theme-state-3, #f59e0b)",
                "borderColor": "var(--theme-state-3, #f59e0b)",
                "extendedProps": {
                    **base_ext,
                    "event_type": "reminder",
                    "color_state": 3,
                    "icon": "bi-alarm-fill",
                    "is_reminder": True,
                    "has_alarm": True,
                },
            })

        # 5. Tägliche Tracker-Routinen
        if item.tracker_times:
            times_list = [t.strip() for t in item.tracker_times.split(",") if t.strip()]
            for t in times_list:
                if len(t) == 5 and t[2] == ":":
                    start_time = f"{t}:00"
                    try:
                        hour, minute = map(int, t.split(":"))
                        end_hour = hour
                        end_minute = minute + 30
                        if end_minute >= 60:
                            end_hour = (end_hour + 1) % 24
                            end_minute = end_minute - 60
                        end_time = f"{end_hour:02d}:{end_minute:02d}:00"
                    except Exception:
                        end_time = f"{t}:00"

                    events.append({
                        "id": f"buckezz-tracker-{item.id}-{t}",
                        "title": item.title,
                        "startTime": start_time,
                        "endTime": end_time,
                        "daysOfWeek": [0, 1, 2, 3, 4, 5, 6],
                        "editable": False,
                        "url": list_url,
                        "backgroundColor": "var(--theme-state-4, #22c55e)",
                        "borderColor": "var(--theme-state-4, #22c55e)",
                        "extendedProps": {
                            **base_ext,
                            "event_type": "tracker",
                            "description": f"Tägliche Routine um {t} Uhr.",
                            "completed": False,
                            "color_state": 4,
                            "icon": icon,
                            "is_reminder": False,
                            "is_recurring": True,
                            "recurrence_rule": "daily",
                        },
                    })

        # 6. Benutzerdefinierte Datumsfelder aus Template-Studio (type == 'date')
        for cf_key, cf_label, date_str in _extract_custom_date_entries(item):
            events.append({
                "id": f"buckezz-cf-{item.id}-{cf_key}",
                "title": f"{item.title} ({cf_label})",
                "start": date_str,
                "allDay": True,
                "editable": False,
                "url": list_url,
                "backgroundColor": "var(--theme-state-6, #8b5cf6)",
                "borderColor": "var(--theme-state-6, #8b5cf6)",
                "extendedProps": {
                    **base_ext,
                    "event_type": "custom_date",
                    "color_state": 6,
                    "icon": icon,
                    "is_reminder": False,
                    "all_day": True,
                },
            })

    return events


def _fmt_ics_utc(dt):
    if timezone.is_aware(dt):
        utc_dt = dt.astimezone(dt_timezone.utc)
    else:
        utc_dt = timezone.make_aware(dt).astimezone(dt_timezone.utc)
    return utc_dt.strftime("%Y%m%dT%H%M%SZ")


def _ics_escape(text):
    return (text or "").replace("\\", "\\\\").replace("\r\n", "\\n").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")


def get_buckezz_ical_events(user):
    """
    Liefert formatierte VEVENT-Blöcke für alle Buckezz-Termine, Fälligkeiten,
    Erinnerungen (inkl. VALARM) und benutzerdefinierten Datumsfelder.
    """
    if not user or not user.is_authenticated:
        return ""

    from core.models import ListItem, ListTemplate

    lists = _get_user_lists(user)
    date_cf_cat_ids = [
        tpl.category_id
        for tpl in ListTemplate.objects.only("category_id", "custom_fields_json")
        if isinstance(tpl.custom_fields_json, list)
        and any(isinstance(f, dict) and f.get("type") == "date" for f in tpl.custom_fields_json)
    ]

    date_filter = (
        models.Q(start_date__isnull=False)
        | models.Q(end_date__isnull=False)
        | models.Q(reminder_at__isnull=False)
    )
    if date_cf_cat_ids:
        date_filter |= models.Q(bucket_list__category_id__in=date_cf_cat_ids) & ~models.Q(custom_data_json={})

    items = (
        ListItem.objects.filter(bucket_list__in=lists)
        .filter(date_filter)
        .select_related("bucket_list", "bucket_list__category", "bucket_list__category__template")
    )

    lines = []
    for item in items:
        stamp_dt = item.updated_at or item.created_at or timezone.now()
        dtstamp = _fmt_ics_utc(stamp_dt)
        desc = f"Liste: {item.bucket_list.title}"
        if item.notes:
            desc += f"\n\n{item.notes}"

        def _append_vevent(uid, dtstart_line, dtend_line, summary, with_alarm=False):
            lines.extend([
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{dtstamp}",
                dtstart_line,
                dtend_line,
                f"SUMMARY:{_ics_escape(summary)}",
                f"DESCRIPTION:{_ics_escape(desc)}",
            ])
            if item.location:
                lines.append(f"LOCATION:{_ics_escape(item.location)}")
            if with_alarm:
                lines.extend([
                    "BEGIN:VALARM",
                    "ACTION:DISPLAY",
                    f"DESCRIPTION:{_ics_escape(f'Erinnerung: {item.title}')}",
                    "TRIGGER:-PT0M",
                    "END:VALARM",
                ])
            lines.append("END:VEVENT")

        # 1. Start + End range
        if item.start_date and item.end_date and item.end_date >= item.start_date:
            _append_vevent(
                f"buckezz-range-{item.id}@buckezz",
                f"DTSTART:{_fmt_ics_utc(item.start_date)}",
                f"DTEND:{_fmt_ics_utc(item.end_date)}",
                f"{item.title} ({item.bucket_list.title})",
            )
        else:
            if item.start_date:
                _append_vevent(
                    f"buckezz-start-{item.id}@buckezz",
                    f"DTSTART:{_fmt_ics_utc(item.start_date)}",
                    f"DTEND:{_fmt_ics_utc(item.start_date + timedelta(hours=1))}",
                    f"{item.title} (Start) ({item.bucket_list.title})",
                )
            if item.end_date:
                _append_vevent(
                    f"buckezz-end-{item.id}@buckezz",
                    f"DTSTART:{_fmt_ics_utc(item.end_date - timedelta(hours=1))}",
                    f"DTEND:{_fmt_ics_utc(item.end_date)}",
                    f"{item.title} ({item.bucket_list.title})",
                )

        # 2. Reminder with VALARM
        if item.reminder_at:
            _append_vevent(
                f"buckezz-rem-{item.id}@buckezz",
                f"DTSTART:{_fmt_ics_utc(item.reminder_at)}",
                f"DTEND:{_fmt_ics_utc(item.reminder_at + timedelta(minutes=30))}",
                f"Erinnerung: {item.title} ({item.bucket_list.title})",
                with_alarm=True,
            )

        # 3. Custom date fields
        for cf_key, cf_label, date_str in _extract_custom_date_entries(item):
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
            next_d = d + timedelta(days=1)
            _append_vevent(
                f"buckezz-cf-{item.id}-{cf_key}@buckezz",
                f"DTSTART;VALUE=DATE:{d.strftime('%Y%m%d')}",
                f"DTEND;VALUE=DATE:{next_d.strftime('%Y%m%d')}",
                f"{item.title} ({cf_label})",
            )

    return "\r\n".join(lines)
