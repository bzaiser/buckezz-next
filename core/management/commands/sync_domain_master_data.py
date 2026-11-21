from django.core.management.base import BaseCommand
from django.db import models
from django.utils.text import slugify

from domain_kit.models import Category, Role, Status, Unit as DomainUnit
from domain_kit.services import seed_domain_defaults


class Command(BaseCommand):
    help = "Synchronisiert Stammdaten verlustfrei von core nach domain_kit (Units, Kategorien, Stati, Rollen)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--database",
            default="default",
            help="Nominates a database to synchronize master data for.",
        )

    def handle(self, *args, **options):
        db_alias = options.get("database") or "default"
        self.stdout.write(f"🔄 Starte Stammdaten-Synchronisation für Datenbank '{db_alias}'...")

        # 1. Standard-Stammdaten sicherstellen
        try:
            seed_domain_defaults(db_alias=db_alias)
            self.stdout.write(self.style.SUCCESS("  ✓ Domain-Kit Standard-Stammdaten geprüft."))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"  ⚠ Hinweis beim Laden der Domain-Standards: {e}"))

        # 2. Einheiten aus core.Unit migrieren & ListItem-Zuordnungen aktualisieren
        migrated_units = 0
        try:
            from core.models import ListItem, Unit as CoreUnit

            unit_map = {}  # core_unit_id -> domain_unit
            for cu in CoreUnit.objects.using(db_alias).all():
                # Finde bestehende Domain-Einheit nach Name oder Symbol
                du = (
                    DomainUnit.objects.using(db_alias)
                    .filter(
                        models.Q(name__iexact=cu.name)
                        | models.Q(symbol__iexact=cu.slug)
                        | models.Q(name__iexact=cu.slug)
                        | models.Q(symbol__iexact=cu.name)
                    )
                    .first()
                )
                if not du:
                    du = DomainUnit.objects.using(db_alias).create(
                        name=cu.name,
                        symbol=(cu.slug or cu.name)[:20],
                        dimension="count",
                        decimals=0,
                        position=100,
                    )
                    migrated_units += 1
                unit_map[cu.id] = du

            # Re-map ListItem FKs
            for cu_id, du in unit_map.items():
                updated_count = ListItem.objects.using(db_alias).filter(unit_id=cu_id).update(unit_id=du.id)
                if updated_count > 0:
                    self.stdout.write(f"    -> {updated_count} Einträge von '{cu_id}' auf Domain-Einheit '{du.name}' umgemappt.")

            if migrated_units:
                self.stdout.write(self.style.SUCCESS(f"  ✓ {migrated_units} neue Einheit(en) aus core.Unit übernommen."))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"  ⚠ Hinweis bei Unit-Migration: {e}"))

        # 3. ListCategory in domain_kit.Category(purpose="list") spiegeln
        migrated_cats = 0
        try:
            from core.models import ListCategory

            for lc in ListCategory.objects.using(db_alias).all():
                _, created = Category.objects.using(db_alias).get_or_create(
                    name=lc.name,
                    purpose="list",
                    defaults={
                        "code": lc.slug[:40],
                        "icon": "bi-list-task",
                        "color_state": 1,
                        "position": 10,
                    },
                )
                if created:
                    migrated_cats += 1
            if migrated_cats:
                self.stdout.write(self.style.SUCCESS(f"  ✓ {migrated_cats} Listen-Kategorie(n) in Domain-Kit gespiegelt."))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"  ⚠ Hinweis bei Kategorie-Sync: {e}"))

        # 4. Stati aus Vorlagen in domain_kit.Status überführen
        migrated_statuses = 0
        try:
            from core.models import ListTemplate

            for tpl in ListTemplate.objects.using(db_alias).all():
                for st in tpl.get_effective_statuses():
                    label = str(st.get("label") or st.get("key") or "").strip()
                    if not label:
                        continue
                    is_final = bool(st.get("completes", False))
                    _, created = Status.objects.using(db_alias).get_or_create(
                        name=label,
                        scope="global",
                        defaults={
                            "is_final": is_final,
                            "color_state": 4 if is_final else 1,
                            "icon": "bi-check-circle" if is_final else "bi-circle",
                            "position": 50 if not is_final else 90,
                        },
                    )
                    if created:
                        migrated_statuses += 1
            if migrated_statuses:
                self.stdout.write(self.style.SUCCESS(f"  ✓ {migrated_statuses} Status-Definition(en) in Domain-Kit übernommen."))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"  ⚠ Hinweis bei Status-Sync: {e}"))

        # 5. Rollen aus Vorlagen in domain_kit.Role überführen
        migrated_roles = 0
        try:
            from core.models import ListTemplate

            for tpl in ListTemplate.objects.using(db_alias).all():
                for rl in tpl.get_effective_roles():
                    label = str(rl.get("label") or rl.get("key") or "").strip()
                    if not label:
                        continue
                    _, created = Role.objects.using(db_alias).get_or_create(
                        name=label,
                        defaults={
                            "color_state": 1,
                            "position": 50,
                            "description": f"Rolle aus Vorlage '{tpl.category.name}'",
                        },
                    )
                    if created:
                        migrated_roles += 1
            if migrated_roles:
                self.stdout.write(self.style.SUCCESS(f"  ✓ {migrated_roles} Rollen-Definition(en) in Domain-Kit übernommen."))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"  ⚠ Hinweis bei Rollen-Sync: {e}"))

        self.stdout.write(self.style.SUCCESS(f"✅ Stammdaten-Synchronisation für '{db_alias}' erfolgreich abgeschlossen!\n"))
