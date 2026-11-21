import re
from datetime import datetime
from django.db import models
from django.urls import reverse
from django.utils import timezone


def get_buckezz_calendar_events(request, window_start, window_end):
    """
    Event-Provider für cal_kit: Liefert alle Aufgaben, Termine, Erinnerungen
    und Tracker-Routinen aus Buckezz Listen für den eingeloggten Benutzer.
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return []

    from core.models import BucketList, ListItem

    if user.is_superuser:
        lists = BucketList.objects.all()
    else:
        lists = BucketList.objects.filter(
            models.Q(owner=user) | models.Q(shared_with=user)
        ).distinct()

    items = (
        ListItem.objects.filter(bucket_list__in=lists)
        .filter(
            models.Q(start_date__isnull=False)
            | models.Q(end_date__isnull=False)
            | models.Q(reminder_at__isnull=False)
            | (models.Q(tracker_times__isnull=False) & ~models.Q(tracker_times=""))
        )
        .select_related("bucket_list", "bucket_list__category")
    )

    events = []
    for item in items:
        list_url = reverse("core:list_detail", args=[item.bucket_list.id])
        cat_icon = item.bucket_list.category.icon if item.bucket_list.category else "📋"

        # 1. Start- und Enddatum (Zeitspanne)
        if item.start_date and item.end_date:
            events.append({
                "id": f"buckezz-range-{item.id}",
                "title": f"{cat_icon} {item.title}",
                "start": item.start_date.isoformat(),
                "end": item.end_date.isoformat(),
                "allDay": False,
                "url": list_url,
                "backgroundColor": "var(--app-primary, #6366f1)",
                "borderColor": "var(--app-primary, #6366f1)",
                "extendedProps": {
                    "master_id": f"buckezz_{item.id}",
                    "listName": item.bucket_list.title,
                    "location": item.location or "",
                    "description": item.notes or "",
                    "completed": item.is_completed,
                    "color_state": 1,
                    "icon": cat_icon,
                    "is_reminder": False,
                    "all_day": False,
                },
            })
        else:
            # 2. Nur Startdatum
            if item.start_date:
                events.append({
                    "id": f"buckezz-start-{item.id}",
                    "title": f"{cat_icon} {item.title} (Start)",
                    "start": item.start_date.isoformat(),
                    "allDay": False,
                    "url": list_url,
                    "backgroundColor": "var(--theme-state-2, #3b82f6)",
                    "borderColor": "var(--theme-state-2, #3b82f6)",
                    "extendedProps": {
                        "master_id": f"buckezz_{item.id}",
                        "listName": item.bucket_list.title,
                        "location": item.location or "",
                        "description": item.notes or "",
                        "completed": item.is_completed,
                        "color_state": 2,
                        "icon": cat_icon,
                        "is_reminder": False,
                        "all_day": False,
                    },
                })
            # 3. Nur Fälligkeitsdatum (Endtermin)
            if item.end_date:
                color = "var(--theme-state-4, #22c55e)" if item.is_completed else "var(--theme-state-5, #ef4444)"
                events.append({
                    "id": f"buckezz-end-{item.id}",
                    "title": f"🏁 {cat_icon} {item.title}",
                    "start": item.end_date.isoformat(),
                    "allDay": False,
                    "url": list_url,
                    "backgroundColor": color,
                    "borderColor": color,
                    "extendedProps": {
                        "master_id": f"buckezz_{item.id}",
                        "listName": item.bucket_list.title,
                        "location": item.location or "",
                        "description": item.notes or "",
                        "completed": item.is_completed,
                        "color_state": 4 if item.is_completed else 5,
                        "icon": "bi-flag",
                        "is_reminder": False,
                        "all_day": False,
                    },
                })

        # 4. Erinnerung (Reminder)
        if item.reminder_at:
            events.append({
                "id": f"buckezz-rem-{item.id}",
                "title": f"⏰ {item.title} (Erinnerung)",
                "start": item.reminder_at.isoformat(),
                "allDay": False,
                "url": list_url,
                "backgroundColor": "var(--theme-state-3, #f59e0b)",
                "borderColor": "var(--theme-state-3, #f59e0b)",
                "extendedProps": {
                    "master_id": f"buckezz_{item.id}",
                    "listName": item.bucket_list.title,
                    "location": item.location or "",
                    "description": item.notes or "",
                    "completed": item.is_completed,
                    "color_state": 3,
                    "icon": "bi-alarm",
                    "is_reminder": True,
                    "has_alarm": True,
                    "all_day": False,
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
                        "title": f"{cat_icon} {item.title}",
                        "startTime": start_time,
                        "endTime": end_time,
                        "daysOfWeek": [0, 1, 2, 3, 4, 5, 6],
                        "url": list_url,
                        "backgroundColor": "var(--theme-state-2, #3b82f6)",
                        "borderColor": "var(--theme-state-2, #3b82f6)",
                        "extendedProps": {
                            "master_id": f"buckezz_{item.id}",
                            "listName": item.bucket_list.title,
                            "location": item.location or "",
                            "description": f"Tägliche Routine um {t} Uhr.",
                            "completed": False,
                            "color_state": 2,
                            "icon": cat_icon,
                            "is_reminder": False,
                            "is_recurring": True,
                            "recurrence_rule": "daily",
                            "all_day": False,
                        },
                    })

    return events


def get_buckezz_ical_events(user):
    """
    Liefert formatierte VEVENT-Blöcke für alle Buckezz-Deadlines und Erinnerungen.
    """
    if not user or not user.is_authenticated:
        return ""

    from core.models import BucketList, ListItem

    lists = BucketList.objects.filter(
        models.Q(owner=user) | models.Q(shared_with=user)
    ).distinct()

    items = (
        ListItem.objects.filter(bucket_list__in=lists)
        .filter(
            models.Q(start_date__isnull=False)
            | models.Q(end_date__isnull=False)
            | models.Q(reminder_at__isnull=False)
        )
        .select_related("bucket_list")
    )

    lines = []
    for item in items:
        dt = item.end_date or item.start_date or item.reminder_at
        if not dt:
            continue
        utc_dt = dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        dt_str = utc_dt.strftime("%Y%m%dT%H%M%SZ")
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:buckezz-{item.id}@buckezz",
            f"DTSTAMP:{dt_str}",
            f"DTSTART:{dt_str}",
            f"SUMMARY:{item.title} ({item.bucket_list.title})",
        ])
        if item.notes:
            clean_notes = item.notes.replace("\n", "\\n")
            lines.append(f"DESCRIPTION:{clean_notes}")
        if item.location:
            lines.append(f"LOCATION:{item.location}")
        lines.append("END:VEVENT")

    return "\r\n".join(lines)
