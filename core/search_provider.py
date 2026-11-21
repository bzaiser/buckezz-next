from django.db import models
from django.db.models import Q


def search_buckezz(request, q: str):
    """
    App-spezifischer Suchprovider für domain_kit (`DOMAIN_SEARCH_PROVIDERS`):
    Durchsucht alle Buckezz-Listen und Listeneinträge (inkl. Zusatzfeldern),
    auf die der eingeloggte Benutzer Zugriff hat, und verlinkt direkt in die Liste.
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return []

    from core.models import BucketList, ListItem

    if user.is_superuser:
        lists_qs = BucketList.objects.select_related("category")
    else:
        lists_qs = BucketList.objects.filter(
            Q(owner=user) | Q(shared_with=user)
        ).select_related("category").distinct()

    item_hits = []
    list_hits = []

    if q:
        q_low = q.lower()
        # 1. Search BucketLists
        for b in lists_qs.filter(Q(title__icontains=q) | Q(category__name__icontains=q))[:25]:
            list_hits.append({
                "title": b.title,
                "subtitle": b.category.name if b.category else "",
                "snippet": "",
                "badge": "Bucket",
                "url": b.get_absolute_url(),
                "url_label": "Bucket öffnen",
            })

        # 2. Search ListItems (standard text fields + custom_data_json)
        items_qs = (
            ListItem.objects.filter(bucket_list__in=lists_qs)
            .select_related("bucket_list", "bucket_list__category", "domain_category")
            .order_by("-updated_at")
        )
        text_matches = list(
            items_qs.filter(
                Q(title__icontains=q)
                | Q(notes__icontains=q)
                | Q(brand__icontains=q)
                | Q(shop__icontains=q)
                | Q(location__icontains=q)
                | Q(amount__icontains=q)
            )[:35]
        )
        seen_ids = {it.id for it in text_matches}

        # Also check custom_data_json on items with non-empty custom_data_json
        if len(text_matches) < 35:
            for it in items_qs.exclude(id__in=seen_ids).exclude(custom_data_json={})[:150]:
                cf = it.custom_data_json if isinstance(it.custom_data_json, dict) else {}
                if any(q_low in str(v or "").lower() for v in cf.values()):
                    text_matches.append(it)
                    seen_ids.add(it.id)
                    if len(text_matches) >= 35:
                        break

        for it in text_matches:
            parts = []
            if it.brand:
                parts.append(it.brand)
            if it.shop:
                parts.append(it.shop)
            if it.location:
                parts.append(it.location)
            if it.amount:
                parts.append(it.amount)
            subtitle = f"Liste: {it.bucket_list.title}"
            if parts:
                subtitle += " · " + " · ".join(parts)

            snippet = ""
            if it.notes and q_low in it.notes.lower():
                snippet = it.notes[:120]
            elif isinstance(it.custom_data_json, dict):
                for k, v in it.custom_data_json.items():
                    if q_low in str(v or "").lower():
                        snippet = f"{k}: {v}"[:120]
                        break

            badge = it.domain_category.name if it.domain_category else it.bucket_list.title
            item_hits.append({
                "title": it.title,
                "subtitle": subtitle,
                "snippet": snippet,
                "badge": badge,
                "url": it.get_absolute_url(),
                "url_label": "In Liste öffnen",
            })

    return [
        {
            "key": "buckezz_items",
            "label": "Listen-Einträge",
            "icon": "bi-check2-square",
            "state": 1,
            "handled_models": [
                "core.listitem",
                "core.listitemimage",
                "core.itempersonrole",
                "core.itemtrackerlog",
                "core.unit",
            ],
            "hits": item_hits,
        },
        {
            "key": "buckezz_lists",
            "label": "Buckets & Listen",
            "icon": "bi-bucket",
            "state": 2,
            "handled_models": ["core.bucketlist"],
            "hits": list_hits,
        },
    ]
