from django.contrib.auth import get_user_model
from seed_kit.registry import fake_amount, register_seeder

from core.models import BucketList, ListCategory, ListItem, ListTemplate


def seed_buckezz_demo(count: int = 5):
    """Idempotent demo seeder for Buckezz 2.0 (never overwrites existing data)."""
    User = get_user_model()
    demo_user, _ = User.objects.get_or_create(
        username="demo_buckezz",
        defaults={"email": "demo@buckezz.local", "is_active": True},
    )

    category, _ = ListCategory.objects.get_or_create(
        slug="demo-einkauf",
        defaults={"name": "Demo Einkauf", "icon": "🛒"},
    )
    ListTemplate.objects.get_or_create(
        category=category,
        defaults={
            "logic_type": "generic",
            "use_price": True,
            "use_amount": True,
            "use_status": True,
        },
    )

    bucket, _ = BucketList.objects.get_or_create(
        title="Demo Wocheneinkauf",
        owner=demo_user,
        defaults={"category": category},
    )

    created_items = 0
    for idx in range(1, count + 1):
        title = f"Demo Artikel {idx}"
        _, created = ListItem.objects.get_or_create(
            bucket_list=bucket,
            title=title,
            defaults={
                "price": fake_amount(1, 25),
                "amount": "1 Stk",
                "notes": "",
            },
        )
        if created:
            created_items += 1

    return f"Demo bucket ready ({created_items} items created)"


register_seeder("buckezz_demo", seed_buckezz_demo, order=50)
