from django.db import models
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
import uuid

class UserSetting(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='settings')
    primary_color = models.CharField(max_length=7, default='#e1d7ff')
    accent_color = models.CharField(max_length=7, default='#4eb422')
    bg_color = models.CharField(max_length=7, default='#1f1325')
    text_color = models.CharField(max_length=7, default='#d3f5d1')
    input_bg_color = models.CharField(max_length=7, default='#614190')
    input_text_color = models.CharField(max_length=7, default='#fde5ff')
    header_bg_color = models.CharField(max_length=7, default='#543d62')
    header_text_color = models.CharField(max_length=7, default='#ffffff')
    glass_opacity = models.DecimalField(max_digits=3, decimal_places=2, default=0.11)
    timezone = models.CharField(max_length=50, default='Europe/Berlin')
    calendar_start_hour = models.IntegerField(default=8)
    calendar_end_hour = models.IntegerField(default=22)
    calendar_refresh_interval = models.CharField(max_length=10, default='PT15M')
    calendar_filter_tracker = models.BooleanField(default=True)
    calendar_filter_reminder = models.BooleanField(default=True)
    calendar_filter_completed = models.BooleanField(default=True)
    
    # Alexa Integration
    alexa_user_id = models.CharField(max_length=255, blank=True, null=True, unique=True, verbose_name="Alexa User ID")

    # Gym & Workout settings
    gym_weight = models.FloatField(null=True, blank=True)
    gym_body_measurements_json = models.JSONField(blank=True, null=True)
    gym_nutrition_plan_url = models.URLField(max_length=1000, blank=True, null=True)
    gym_fitness_goal = models.CharField(max_length=255, blank=True, null=True)
    gym_plan_adaptation_weeks = models.IntegerField(default=4)
    gym_plan_adaptation_message = models.TextField(default='Bitte melde dich beim Trainer für einen neuen Plan, damit die Fortschritte möglich sind.')

    def __str__(self):
        return f"Settings for {self.user.username}"

class Person(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True, null=True, verbose_name=_("Telefonnummer"))
    notes = models.TextField(blank=True, null=True, verbose_name=_("Kontaktnotizen"))
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='person_profile')
    domain_person = models.OneToOneField('domain_kit.Person', on_delete=models.SET_NULL, null=True, blank=True, related_name='buckezz_person')
    access_token = models.UUIDField(default=uuid.uuid4, unique=True)
    birth_date = models.DateField(null=True, blank=True)

    @property
    def avatar_url(self):
        if self.domain_person_id:
            try:
                if self.domain_person and self.domain_person.photo:
                    return self.domain_person.photo.url
            except Exception:
                return ''
        return ''

    @property
    def company_label(self):
        if self.domain_person_id:
            try:
                return (self.domain_person.company or '').strip()
            except Exception:
                return ''
        return ''

    @property
    def age(self):
        if not self.birth_date:
            return None
        from django.utils import timezone
        today = timezone.localdate()
        return today.year - self.birth_date.year - ((today.month, today.day) < (self.birth_date.month, self.birth_date.day))

    @property
    def active_milestone(self):
        current_age = self.age
        if current_age is None:
            return None
        if current_age < 30:
            return 'before_30'
        elif current_age < 40:
            return 'before_40'
        elif current_age < 50:
            return 'before_50'
        elif current_age < 60:
            return 'before_60'
        else:
            return 'before_die'

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _("Person")
        verbose_name_plural = _("Personen")

class ListCategory(models.Model):
    name = models.CharField(max_length=100)
    icon = models.CharField(max_length=50, help_text="Lucide-Icon Name oder Emoji", default="📋")
    slug = models.SlugField(unique=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _("Listen-Kategorie")
        verbose_name_plural = _("Listen-Kategorien")

class ListTemplate(models.Model):
    category = models.OneToOneField(ListCategory, on_delete=models.CASCADE, related_name='template')
    
    LOGIC_CHOICES = [
        ('generic', _('Allgemein (Standard)')),
        ('todo', _('To-Do Liste')),
        ('gift', _('Geschenkeliste')),
        ('bucket', _('Bucketliste')),
        ('event', _('Veranstaltungsplaner')),
        ('tracker', _('Tracker / Gewohnheiten')),
        ('workout', _('Trainingsplan / Sport')),
        ('nutrition', _('Kalorien- & Gewichtstracking')),
    ]
    logic_type = models.CharField(max_length=20, choices=LOGIC_CHOICES, default='generic', help_text=_("Bestimmt den spezifischen Workflow für diesen Listentyp"))

    # Visibility & Access Configuration
    use_is_public = models.BooleanField(default=False)
    use_allow_public_edit = models.BooleanField(default=False)
    use_beneficiary = models.BooleanField(default=False)
    use_secret_santa = models.BooleanField(default=False)

    # Configuration which fields are active
    use_price = models.BooleanField(default=False)
    use_amount = models.BooleanField(default=False)
    use_brand = models.BooleanField(default=False)
    use_shop = models.BooleanField(default=False)
    use_start_date = models.BooleanField(default=False)
    use_end_date = models.BooleanField(default=False)
    use_reminder = models.BooleanField(default=False)
    use_location = models.BooleanField(default=False)
    use_persons = models.BooleanField(default=False)
    use_url = models.BooleanField(default=False)
    use_status = models.BooleanField(default=True)
    use_rating = models.BooleanField(default=False)
    use_tracker = models.BooleanField(default=False)
    use_milestone = models.BooleanField(default=False)
    use_domain_category = models.BooleanField(default=False, verbose_name=_("Kategorie (Stammdaten)"))
    domain_category_purpose = models.CharField(max_length=32, blank=True, default='', verbose_name=_("Kategorie-Bereich"))
    use_image = models.BooleanField(default=False, verbose_name=_("Foto / Bildanhang erlauben"))
    use_subchecklist = models.BooleanField(default=False, verbose_name=_("Teil-Checkliste / Aufzählung aktivieren"))
    use_subchecklist_photos = models.BooleanField(default=False, verbose_name=_("Teil-Checkliste mit Foto pro Eintrag"))
    new_items_at_bottom = models.BooleanField(default=False, verbose_name="Neue Einträge unten anfügen", help_text="Wenn aktiv, werden neue Einträge am Ende der Liste angefügt, andernfalls oben.")

    # Custom status workflow & declarative logic-builder rules
    allowed_statuses_json = models.JSONField(default=list, blank=True, verbose_name=_("Erlaubte Eintrags-Stati"))
    allowed_roles_json = models.JSONField(default=list, blank=True, verbose_name=_("Erlaubte Personen-Rollen"))
    logic_rules_json = models.JSONField(default=dict, blank=True, verbose_name=_("Logik-Builder Regeln"))
    ui_style_json = models.JSONField(default=dict, blank=True, verbose_name=_("UI-Layout & Stil"))
    custom_fields_json = models.JSONField(default=list, blank=True, verbose_name=_("Eigene Zusatzfelder"))
    GROUP_BY_CHOICES = [
        ('none', _('Keine Gruppierung')),
        ('milestone', _('Alters-Meilensteine')),
        ('status', _('Status')),
        ('category', _('Kategorie (Stammdaten)')),
        ('person', _('Person / Zuständig')),
        ('shop', _('Geschäft / Shop')),
        ('brand', _('Marke / Hersteller')),
        ('location', _('Ort')),
    ]
    group_by = models.CharField(max_length=30, choices=GROUP_BY_CHOICES, default='none', blank=True, verbose_name=_("Gruppierung nach"))
    summary_rule_json = models.JSONField(default=dict, blank=True, verbose_name=_("KPI-Aggregationsregel"))
    recurrence_json = models.JSONField(default=dict, blank=True, verbose_name=_("Auto-Reset / Wiederholung"))

    # Customizable help guidelines
    help_purpose = models.TextField(blank=True, null=True, help_text="💡 Zweck der Vorlage (z.B. Ideal für den Wocheneinkauf)")
    help_fields = models.TextField(blank=True, null=True, help_text="🛠️ Welche Felder aktiv sind und wie man sie nutzt")
    help_example = models.TextField(blank=True, null=True, help_text="📝 Praxis-Beispiel für einen Eintrag")

    def __str__(self):
        return f"Template für {self.category.name}"

    def _get_domain_status_lookup(self):
        lookup = {}
        try:
            from domain_kit.models import Status as DomainStatus
            from django.utils.text import slugify
            db_alias = self._state.db or 'default'
            for ds in DomainStatus.objects.using(db_alias).all().order_by('position', 'id'):
                accent = ds.custom_color or f"var(--theme-state-{ds.color_state}, var(--app-primary, #0d6efd))"
                style_info = {
                    'domain_status_id': ds.id,
                    'color_state': ds.color_state,
                    'custom_color': ds.custom_color,
                    'icon': ds.icon,
                    'badge_style': ds.badge_style,
                    'accent_color': accent,
                    'completes': bool(ds.is_final),
                }
                lookup[ds.name.strip().lower()] = style_info
                slug_key = slugify(ds.name).replace('-', '_')[:20]
                if slug_key:
                    lookup[slug_key] = style_info
        except Exception:
            pass
        return lookup

    def get_effective_statuses(self):
        from django.utils.text import slugify
        ds_lookup = self._get_domain_status_lookup()

        def _enrich(entry):
            out = dict(entry)
            lbl = str(out.get('label') or '').strip().lower()
            key = str(out.get('key') or '').strip().lower()
            match = ds_lookup.get(lbl) or ds_lookup.get(key)
            if match:
                out.setdefault('color_state', match['color_state'])
                out.setdefault('custom_color', match['custom_color'])
                out.setdefault('icon', match['icon'])
                out.setdefault('badge_style', match['badge_style'])
                out.setdefault('accent_color', match['accent_color'])
            return out

        if isinstance(self.allowed_statuses_json, list) and len(self.allowed_statuses_json) > 0:
            return [_enrich(s) for s in self.allowed_statuses_json if isinstance(s, dict)]
        if self.logic_type == 'gift':
            return [
                _enrich({'key': 'open', 'label': 'Offen', 'completes': False}),
                _enrich({'key': 'reserved', 'label': 'Reserviert', 'completes': False}),
                _enrich({'key': 'fulfilled', 'label': 'Wunsch erfüllt', 'completes': True}),
            ]
        if self.use_status:
            try:
                from domain_kit.models import Status as DomainStatus
                db_alias = self._state.db or 'default'
                ds_list = list(
                    DomainStatus.objects.using(db_alias)
                    .filter(scope__in=['list', 'global'])
                    .order_by('position', 'id')
                )
                if ds_list:
                    out = []
                    seen = set()
                    for ds in ds_list:
                        key = slugify(ds.name).replace('-', '_')[:20] or f"st_{ds.id}"
                        if key in seen:
                            continue
                        seen.add(key)
                        accent = ds.custom_color or f"var(--theme-state-{ds.color_state}, var(--app-primary, #0d6efd))"
                        out.append({
                            'key': key,
                            'label': ds.name,
                            'completes': bool(ds.is_final),
                            'color_state': ds.color_state,
                            'custom_color': ds.custom_color,
                            'icon': ds.icon,
                            'badge_style': ds.badge_style,
                            'accent_color': accent,
                        })
                    return out
            except Exception:
                pass
        done_label = 'Erreicht' if self.logic_type == 'bucket' else 'Erledigt'
        return [
            _enrich({'key': 'open', 'label': 'Offen', 'completes': False}),
            _enrich({'key': 'completed', 'label': done_label, 'completes': True}),
        ]

    def get_logic_rule(self, key, default=False):
        if isinstance(self.logic_rules_json, dict) and key in self.logic_rules_json:
            return self.logic_rules_json[key]
        return default

    def _enrich_roles_with_domain(self, roles):
        try:
            from domain_kit.models import Role as DomainRole
            from django.utils.text import slugify
            db_alias = self._state.db or 'default'
            dr_lookup = {}
            for dr in DomainRole.objects.using(db_alias).all().order_by('position', 'name'):
                info = {
                    'color_state': dr.color_state,
                    'custom_color': dr.custom_color,
                    'badge_style': dr.badge_style,
                }
                dr_lookup[dr.name.strip().lower()] = info
                skey = slugify(dr.name).replace('-', '_')[:20]
                if skey:
                    dr_lookup[skey] = info
            if dr_lookup:
                enriched = []
                for r in roles:
                    item = dict(r)
                    match = dr_lookup.get(str(item.get('label') or '').strip().lower()) or dr_lookup.get(str(item.get('key') or '').strip().lower())
                    if match:
                        item.update(match)
                    enriched.append(item)
                return enriched
        except Exception:
            pass
        return roles

    def get_effective_roles(self):
        if isinstance(self.allowed_roles_json, list) and len(self.allowed_roles_json) > 0:
            from django.utils.text import slugify
            normalized = []
            for idx, entry in enumerate(self.allowed_roles_json):
                if isinstance(entry, dict):
                    label = str(entry.get('label') or entry.get('key') or f'Rolle {idx + 1}').strip()
                    raw_key = str(entry.get('key') or slugify(label) or f'role_{idx + 1}').strip()
                    normalized.append({
                        'key': raw_key[:20],
                        'label': label,
                        'completes': bool(entry.get('completes', False)),
                    })
                elif isinstance(entry, str) and entry.strip():
                    label = entry.strip()
                    key = (slugify(label) or f'role_{idx + 1}')[:20]
                    normalized.append({'key': key, 'label': label, 'completes': False})
            if normalized:
                return self._enrich_roles_with_domain(normalized)
        if self.logic_type == 'event':
            return self._enrich_roles_with_domain([
                {'key': 'assigned', 'label': 'Organisator / Zuständig', 'completes': False},
                {'key': 'invited', 'label': 'Gast (Eingeladen)', 'completes': False},
                {'key': 'attending', 'label': 'Zusage (Teilnahme)', 'completes': False},
                {'key': 'declined', 'label': 'Absage (Teilnahme)', 'completes': False},
                {'key': 'maybe', 'label': 'Vielleicht (Teilnahme)', 'completes': False},
                {'key': 'reserved', 'label': 'Bringe ich mit!', 'completes': False},
                {'key': 'fulfilled', 'label': 'Erledigt / Besorgt', 'completes': True},
                {'key': 'borrowed_from', 'label': 'Geliehen von', 'completes': False},
                {'key': 'lent_to', 'label': 'Verliehen an', 'completes': False},
            ])
        return self._enrich_roles_with_domain([
            {'key': 'assigned', 'label': 'Zuständig', 'completes': False},
            {'key': 'invited', 'label': 'Eingeladen', 'completes': False},
            {'key': 'attending', 'label': 'Zugesagt', 'completes': False},
            {'key': 'declined', 'label': 'Abgesagt', 'completes': False},
            {'key': 'maybe', 'label': 'Vielleicht', 'completes': False},
            {'key': 'reserved', 'label': 'Reserviert', 'completes': False},
            {'key': 'fulfilled', 'label': 'Wunsch erfüllt', 'completes': True},
            {'key': 'borrowed_from', 'label': 'Geliehen von', 'completes': False},
            {'key': 'lent_to', 'label': 'Verliehen an', 'completes': False},
        ])

    def get_ui_style(self):
        defaults = {
            'layout_mode': 'row',
            'card_width': '1/3',
            'density': 'normal',
            'show_creator': True,
            'genre': '',
            'card_layout': None,
        }
        if isinstance(self.ui_style_json, dict):
            defaults.update(self.ui_style_json)
        return defaults

    def get_effective_group_by(self):
        if self.group_by and self.group_by != 'none':
            return self.group_by
        if self.use_milestone:
            return 'milestone'
        return 'none'

class BucketList(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    todo_sync_url = models.URLField(blank=True, null=True, verbose_name="Microsoft To-Do iCal-Link", help_text="Öffentlicher iCal/ICS-Link zur Synchronisation (z.B. Microsoft To-Do)")
    category = models.ForeignKey(ListCategory, on_delete=models.PROTECT, related_name='lists')
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='owned_lists')
    shared_with = models.ManyToManyField(User, related_name='shared_lists', blank=True)
    is_public = models.BooleanField(default=False, help_text="Zugriff über Link ohne Login möglich")
    allow_public_edit = models.BooleanField(default=False, help_text="Personen mit Link dürfen Einträge hinzufügen/ändern")
    
    beneficiary = models.ForeignKey(Person, on_delete=models.SET_NULL, null=True, blank=True, related_name='beneficiary_lists', help_text="Für wen ist diese Liste? (z.B. Geburtstagskind)")
    is_secret_santa = models.BooleanField(default=False, help_text="Versteckt Zuordnungen vor dem Begünstigten")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    @property
    def has_icon_in_title(self):
        if not self.title:
            return False
        first_char = self.title.strip()[0] if self.title.strip() else ""
        if not first_char:
            return False
        return ord(first_char) > 2000

    @property
    def beneficiary_person(self):
        if self.beneficiary:
            return self.beneficiary
        # Find if the owner user has a Person profile
        from core.models import Person
        return Person.objects.filter(user=self.owner).first()

    class Meta:
        verbose_name = _("Liste")
        verbose_name_plural = _("Listen")

class ListParticipant(models.Model):
    bucket_list = models.ForeignKey(BucketList, on_delete=models.CASCADE, related_name='participants')
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name='participating_in')
    link_sent = models.BooleanField(default=False)

    class Meta:
        unique_together = ('bucket_list', 'person')
        verbose_name = _("Listen-Teilnehmer")
        verbose_name_plural = _("Listen-Teilnehmer")

class Unit(models.Model):
    name = models.CharField(max_length=50, unique=True, verbose_name="Name")
    slug = models.SlugField(max_length=50, unique=True, verbose_name="Slug")

    class Meta:
        verbose_name = "Einheit"
        verbose_name_plural = "Einheiten"
        ordering = ['name']

    def __str__(self):
        return self.name

class ListItem(models.Model):
    bucket_list = models.ForeignKey(BucketList, on_delete=models.CASCADE, related_name='items')
    title = models.CharField(max_length=255)
    
    # Potential fields (managed by template)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    amount = models.CharField(max_length=100, null=True, blank=True)
    amount_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    unit = models.ForeignKey('domain_kit.Unit', on_delete=models.SET_NULL, null=True, blank=True, related_name='items')
    domain_category = models.ForeignKey('domain_kit.Category', on_delete=models.SET_NULL, null=True, blank=True, related_name='buckezz_items')
    brand = models.CharField(max_length=255, null=True, blank=True)
    shop = models.CharField(max_length=255, null=True, blank=True)
    url = models.URLField(max_length=1000, null=True, blank=True)
    rating = models.PositiveSmallIntegerField(null=True, blank=True)
    
    tracker_unit = models.CharField(max_length=100, null=True, blank=True, help_text=_("Einheit, z.B. Tablette, Portion, ml"))
    tracker_times = models.CharField(max_length=255, null=True, blank=True, help_text=_("Komma-separierte Uhrzeiten, z.B. 08:00, 18:00"))
    tracker_stock_total = models.IntegerField(null=True, blank=True, help_text=_("Aktueller Gesamtbestand im Kasten/Packung"))
    tracker_stock_min = models.IntegerField(null=True, blank=True, help_text=_("Warnschwelle für Nachbestellung"))
    tracker_dosage_per_take = models.FloatField(default=1.0, help_text=_("Verbrauch pro Abhaken"))
    
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)
    reminder_at = models.DateTimeField(null=True, blank=True)
    reminder_sent = models.BooleanField(default=False)
    
    location = models.CharField(max_length=255, null=True, blank=True)
    image = models.ImageField(upload_to='item_photos/', blank=True, null=True, verbose_name=_("Foto / Beleg"))
    subchecklist_json = models.JSONField(default=list, blank=True, verbose_name=_("Teil-Checkliste"))
    custom_data_json = models.JSONField(default=dict, blank=True, verbose_name=_("Zusatzfeld-Werte"))
    
    # Workout activity fields
    WORKOUT_TYPE_CHOICES = [
        ('strength', _('Krafttraining (Gewichte/Sätze)')),
        ('endurance', _('Ausdauertraining (Distanz/Zeit)')),
        ('interval', _('Intervalltraining (Crossfit/HIIT)')),
    ]
    workout_type = models.CharField(max_length=20, choices=WORKOUT_TYPE_CHOICES, default='strength')
    workout_config_json = models.JSONField(blank=True, null=True, help_text=_("Konfiguration für Sätze, Distanzen, Intervalle"))
    
    STATUS_CHOICES = [
        ('active', _('Aktiv')),
        ('done', _('Erledigt')),
        ('overdue', _('Überfällig')),
        ('waiting', _('Wartend')),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    
    MILESTONE_CHOICES = [
        ('before_30', _('Vor 30')),
        ('before_40', _('Vor 40')),
        ('before_50', _('Vor 50')),
        ('before_60', _('Vor 60')),
        ('before_die', _('Bevor ich sterbe')),
    ]
    target_milestone = models.CharField(max_length=20, choices=MILESTONE_CHOICES, null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    @property
    def age_at_completion(self):
        beneficiary = self.bucket_list.beneficiary_person
        if not self.completed_at or not beneficiary or not beneficiary.birth_date:
            return None
        birth = beneficiary.birth_date
        comp = self.completed_at.date()
        return comp.year - birth.year - ((comp.month, comp.day) < (birth.month, birth.day))
    
    involved_persons = models.ManyToManyField(Person, through='ItemPersonRole', related_name='items', blank=True)
    notes = models.TextField(blank=True)
    
    is_invitation = models.BooleanField(default=False, verbose_name=_("Ist eine Einladung"))
    is_completed = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_items')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='updated_items')
    guest_created_by = models.CharField(max_length=100, blank=True, null=True)
    guest_updated_by = models.CharField(max_length=100, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # Synchronize and parse amount/unit fields
        if self.amount_value is not None:
            val_str = f"{self.amount_value:f}"
            if '.' in val_str:
                val_str = val_str.rstrip('0').rstrip('.')
            
            if self.unit:
                self.amount = f"{val_str} {self.unit.name}"
            else:
                self.amount = val_str
        elif self.amount:
            import re
            from decimal import Decimal, InvalidOperation
            s = self.amount.strip()
            match = re.match(r'^([\d\.,]+)\s*(.*)$', s)
            if match:
                num_str, unit_str = match.groups()
                num_str = num_str.replace(',', '.')
                try:
                    self.amount_value = Decimal(num_str)
                    unit_clean = unit_str.strip().lower()
                    if unit_clean:
                        from domain_kit.models import Unit as DomainUnit
                        from django.utils.text import slugify
                        slug_mapping = {
                            'stk': 'stk', 'stk.': 'stk', 'stück': 'stk', 'stueck': 'stk', 'x': 'stk',
                            'flaschen': 'flaschen', 'flasche': 'flaschen', 'fl.': 'flaschen', 'fl': 'flaschen',
                            'l': 'l', 'liter': 'l',
                            'g': 'g', 'gramm': 'g',
                            'kg': 'kg', 'kilo': 'kg', 'kilogramm': 'kg',
                            'm': 'm', 'meter': 'm',
                            'cm': 'cm', 'zentimeter': 'cm',
                        }
                        unit_slug = slug_mapping.get(unit_clean, slugify(unit_clean)[:20])
                        
                        name_mapping = {
                            'stk': 'Stk.',
                            'flaschen': 'Fl.',
                            'l': 'l',
                            'g': 'g',
                            'kg': 'kg',
                            'm': 'm',
                            'cm': 'cm'
                        }
                        unit_name = name_mapping.get(unit_slug, unit_str.strip())
                        
                        db_alias = self._state.db or 'default'
                        unit_obj = (
                            DomainUnit.objects.using(db_alias)
                            .filter(
                                models.Q(symbol__iexact=unit_slug)
                                | models.Q(name__iexact=unit_name or unit_clean)
                                | models.Q(symbol__iexact=unit_clean)
                                | models.Q(name__iexact=unit_clean)
                            )
                            .first()
                        )
                        if not unit_obj:
                            unit_obj, _ = DomainUnit.objects.using(db_alias).get_or_create(
                                symbol=(unit_slug or unit_clean)[:20],
                                defaults={'name': unit_name or unit_clean, 'dimension': 'count', 'position': 100}
                            )
                        self.unit = unit_obj
                except (InvalidOperation, ValueError, Exception):
                    pass

        # Handle completion dates
        if self.is_completed:
            if not self.completed_at:
                from django.utils import timezone
                self.completed_at = timezone.now()
        else:
            self.completed_at = None
        super().save(*args, **kwargs)
        if self.bucket_list:
            self.bucket_list.save()

    def delete(self, *args, **kwargs):
        bucket = self.bucket_list
        super().delete(*args, **kwargs)
        if bucket:
            bucket.save()

    @property
    def completed_tracker_times_today(self):
        from django.utils import timezone
        today = timezone.localdate()
        return list(self.tracker_logs.filter(date=today).values_list('scheduled_time', flat=True))

    @property
    def tracker_times_list(self):
        if not self.tracker_times:
            return []
        return [t.strip() for t in self.tracker_times.split(',') if t.strip()]

    def get_custom_field_display(self):
        tpl = getattr(getattr(self.bucket_list, 'category', None), 'template', None)
        fields = getattr(tpl, 'custom_fields_json', None) or []
        data = self.custom_data_json if isinstance(self.custom_data_json, dict) else {}
        result = []
        for f in fields:
            key = f.get('key')
            if not key or key not in data:
                continue
            val = data.get(key)
            if val is None or val == '' or val is False:
                continue
            if f.get('type') == 'checkbox':
                val = 'Ja'
            elif f.get('type') == 'currency':
                curr = (f.get('options') or '€').strip() or '€'
                val = f"{val} {curr}"
            elif f.get('type') == 'multiselect' and isinstance(val, list):
                if not val:
                    continue
                val = ', '.join(str(v) for v in val)
            result.append({
                'key': key,
                'label': f.get('label', key),
                'type': f.get('type', 'text'),
                'value': val,
                'show_on_card': f.get('show_on_card', True),
                'zone': f.get('zone', 'body'),
            })
        return result

    @property
    def effective_status_info(self):
        """Return matching custom or domain_kit status dict with live badge_style/icon."""
        if hasattr(self, '_cached_status_info'):
            return self._cached_status_info
        info = None
        tpl = getattr(getattr(self.bucket_list, 'category', None), 'template', None)
        if tpl and (tpl.allowed_statuses_json or tpl.use_status):
            for st in tpl.get_effective_statuses():
                if st.get('key') == self.status:
                    # Skip noisy default 'active'/'open' badge when template has no explicit custom statuses
                    if not tpl.allowed_statuses_json and self.status in ('active', 'open') and not self.is_completed:
                        return None
                    info = dict(st)
                    break
        if not info and self.status in ('waiting', 'overdue'):
            info = {'key': self.status, 'label': self.get_status_display(), 'completes': False}

        # Enrich with live domain_kit Status styling if not already enriched
        if info is None or not info.get('badge_style'):
            try:
                from domain_kit.models import Status as DomainStatus
                from django.utils.text import slugify
                db_alias = self._state.db or 'default'
                label_query = (info.get('label') if info else None) or self.status
                ds = None
                for cand in DomainStatus.objects.using(db_alias).all().order_by('position', 'id'):
                    c_slug = slugify(cand.name).replace('-', '_')[:20]
                    if cand.name.lower() == str(label_query).lower() or cand.name.lower() == str(self.status).lower() or c_slug == self.status:
                        ds = cand
                        break
                if ds:
                    if not info:
                        if self.status in ('active', 'open') and not self.is_completed:
                            return None
                        info = {'key': self.status, 'label': ds.name, 'completes': ds.is_final}
                    info['color_state'] = ds.color_state
                    info['custom_color'] = ds.custom_color
                    info['icon'] = ds.icon
                    info['badge_style'] = ds.badge_style
                    info['accent_color'] = ds.custom_color or f"var(--theme-state-{ds.color_state}, var(--app-primary, #0d6efd))"
            except Exception:
                pass
        return info

    @property
    def card_accent_color(self):
        st = self.effective_status_info
        if st and st.get('accent_color'):
            return st['accent_color']
        if self.domain_category_id:
            try:
                cat = self.domain_category
                if cat:
                    return cat.custom_color or f"var(--theme-state-{cat.color_state}, var(--app-primary, #0d6efd))"
            except Exception:
                pass
        return ''

    class Meta:
        ordering = ['order', '-created_at']
        verbose_name = _("Listen-Eintrag")
        verbose_name_plural = _("Listen-Einträge")


class ListItemImage(models.Model):
    item = models.ForeignKey(ListItem, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='item_photos/', verbose_name=_("Foto / Beleg"))
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Foto für {self.item.title}"

    class Meta:
        ordering = ['id']
        verbose_name = _("Eintrag-Foto")
        verbose_name_plural = _("Eintrag-Fotos")


class ItemPersonRole(models.Model):
    STATUS_CHOICES = [
        ('assigned', _('Zuständig')),
        ('invited', _('Eingeladen')),
        ('attending', _('Zugesagt')),
        ('declined', _('Abgesagt')),
        ('maybe', _('Vielleicht')),
        ('reserved', _('Reserviert')),
        ('fulfilled', _('Wunsch erfüllt')),
        ('borrowed_from', _('Geliehen von')),
        ('lent_to', _('Verliehen an')),
    ]
    item = models.ForeignKey(ListItem, on_delete=models.CASCADE, related_name='person_roles')
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name='item_roles')
    role = models.CharField(max_length=20, choices=STATUS_CHOICES, default='assigned')

    @property
    def role_label(self):
        if hasattr(self, '_cached_role_label'):
            return self._cached_role_label
        try:
            tpl = self.item.bucket_list.category.template
            for r in tpl.get_effective_roles():
                if r.get('key') == self.role:
                    return r.get('label') or self.get_role_display()
        except Exception:
            pass
        return self.get_role_display()

    @property
    def role_badge_style(self):
        if hasattr(self, '_cached_role_style'):
            return self._cached_role_style
        try:
            from domain_kit.models import Role as DomainRole
            from django.utils.text import slugify
            db_alias = self._state.db or 'default'
            lbl = self.role_label.strip().lower()
            for dr in DomainRole.objects.using(db_alias).all():
                if dr.name.strip().lower() == lbl or slugify(dr.name).replace('-', '_')[:20] == self.role:
                    return dr.badge_style
        except Exception:
            pass
        return ''

    class Meta:
        unique_together = ('item', 'person')
        verbose_name = _("Personen-Zuordnung")
        verbose_name_plural = _("Personen-Zuordnungen")

class ItemTrackerLog(models.Model):
    item = models.ForeignKey(ListItem, on_delete=models.CASCADE, related_name='tracker_logs')
    date = models.DateField(auto_now_add=True)
    scheduled_time = models.CharField(max_length=5) # z.B. "08:00"
    completed = models.BooleanField(default=True)
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('item', 'date', 'scheduled_time')
        verbose_name = _("Tracker-Protokoll")
        verbose_name_plural = _("Tracker-Protokolle")

    def __str__(self):
        return f"{self.item.title} am {self.date} um {self.scheduled_time}"

class WorkoutSessionLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='workout_sessions')
    bucket_list = models.ForeignKey(BucketList, on_delete=models.CASCADE, related_name='workout_sessions')
    date = models.DateTimeField(auto_now_add=True)
    duration_seconds = models.IntegerField(default=0)
    rating = models.PositiveSmallIntegerField(default=5)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-date']
        verbose_name = _("Trainingseinheit Protokoll")
        verbose_name_plural = _("Trainingseinheiten Protokolle")

    def __str__(self):
        return f"{self.bucket_list.title} am {self.date.strftime('%d.%m.%Y')}"

class WorkoutActivityLog(models.Model):
    session = models.ForeignKey(WorkoutSessionLog, on_delete=models.CASCADE, related_name='activities')
    title = models.CharField(max_length=255)
    activity_type = models.CharField(max_length=20) # 'strength', 'endurance', 'interval'
    logged_data_json = models.JSONField()

    class Meta:
        verbose_name = _("Aktivität Protokoll")
        verbose_name_plural = _("Aktivitäten Protokolle")

    def __str__(self):
        return f"{self.title} ({self.activity_type})"


class Tenant(models.Model):
    slug = models.SlugField(unique=True, verbose_name=_("Subdomain-Slug"))
    name = models.CharField(max_length=255, verbose_name=_("Instanz-Name"))
    owner_email = models.EmailField(verbose_name=_("Besitzer-E-Mail"))
    is_active = models.BooleanField(default=True, verbose_name=_("Aktiv"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Erstellt am"))

    def __str__(self):
        return f"{self.name} ({self.slug})"

    class Meta:
        verbose_name = _("Mandant")
        verbose_name_plural = _("Mandanten")


class NutritionGoal(models.Model):
    GENDER_CHOICES = [
        ('male', _('Männlich')),
        ('female', _('Weiblich')),
    ]
    ACTIVITY_CHOICES = [
        (1.2, _('Überwiegend sitzend (Bürojob, wenig Bewegung)')),
        (1.375, _('Leicht aktiv (1-3x Sport pro Woche)')),
        (1.55, _('Moderat aktiv (3-5x Sport pro Woche)')),
        (1.725, _('Sehr aktiv (6-7x Sport pro Woche)')),
    ]
    GOAL_CHOICES = [
        ('lose', _('Abnehmen (-400 kcal/Tag)')),
        ('maintain', _('Gewicht halten')),
        ('gain', _('Zunehmen / Aufbau (+350 kcal/Tag)')),
    ]

    bucket_list = models.OneToOneField(BucketList, on_delete=models.CASCADE, related_name='nutrition_goal')
    start_weight = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name=_("Startgewicht (kg)"))
    target_weight = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name=_("Zielgewicht (kg)"))
    target_calories = models.PositiveIntegerField(default=2000, verbose_name=_("Tägliche Zielkalorien"))
    
    # Optional calculator parameters
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, default='male', verbose_name=_("Geschlecht"))
    age = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name=_("Alter"))
    height_cm = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name=_("Körpergröße (cm)"))
    activity_level = models.FloatField(choices=ACTIVITY_CHOICES, default=1.2, verbose_name=_("Aktivitätslevel"))
    goal_type = models.CharField(max_length=15, choices=GOAL_CHOICES, default='lose', verbose_name=_("Ziel"))

    # Macro distribution in grams (optional)
    target_protein_g = models.PositiveIntegerField(default=140, verbose_name=_("Ziel-Protein (g)"))
    target_carbs_g = models.PositiveIntegerField(default=220, verbose_name=_("Ziel-Kohlenhydrate (g)"))
    target_fat_g = models.PositiveIntegerField(default=65, verbose_name=_("Ziel-Fett (g)"))
    target_water_ml = models.PositiveIntegerField(default=2500, verbose_name=_("Ziel-Wasser (ml)"))

    def calculate_recommended_calories(self):
        """Mifflin-St. Jeor Formel"""
        if not (self.start_weight and self.height_cm and self.age):
            return self.target_calories
        
        weight = float(self.start_weight)
        height = float(self.height_cm)
        age = float(self.age)

        if self.gender == 'female':
            bmr = 10 * weight + 6.25 * height - 5 * age - 161
        else:
            bmr = 10 * weight + 6.25 * height - 5 * age + 5

        tdee = bmr * float(self.activity_level or 1.2)

        if self.goal_type == 'lose':
            rec = tdee - 400
        elif self.goal_type == 'gain':
            rec = tdee + 350
        else:
            rec = tdee

        return max(1200, int(round(rec)))

    def __str__(self):
        return f"Ziel für {self.bucket_list.title}: {self.target_calories} kcal / Ziel: {self.target_weight} kg"


class WeightLog(models.Model):
    bucket_list = models.ForeignKey(BucketList, on_delete=models.CASCADE, related_name='weight_logs')
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='user_weight_logs')
    date = models.DateField(default=timezone.now, verbose_name=_("Messdatum"))
    weight = models.DecimalField(max_digits=5, decimal_places=2, verbose_name=_("Gewicht (kg)"))
    note = models.CharField(max_length=255, blank=True, verbose_name=_("Notiz"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['date', 'created_at']
        verbose_name = _("Gewichtsmessung")
        verbose_name_plural = _("Gewichtsmessungen")

    def __str__(self):
        return f"{self.date}: {self.weight} kg ({self.bucket_list.title})"


class NutritionMealLog(models.Model):
    MEAL_CHOICES = [
        ('breakfast', _('Frühstück')),
        ('lunch', _('Mittagessen')),
        ('dinner', _('Abendessen')),
        ('snack', _('Snacks & Drinks')),
        ('water', _('Wasser / Trinken')),
    ]

    bucket_list = models.ForeignKey(BucketList, on_delete=models.CASCADE, related_name='nutrition_meal_logs')
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='user_nutrition_logs')
    date = models.DateField(default=timezone.now, verbose_name=_("Datum"))
    meal_type = models.CharField(max_length=20, choices=MEAL_CHOICES, default='lunch', verbose_name=_("Mahlzeit"))
    title = models.CharField(max_length=255, verbose_name=_("Bezeichnung / Mahlzeit"))
    calories = models.PositiveIntegerField(verbose_name=_("Kalorien (kcal)"))
    protein_g = models.FloatField(default=0.0, blank=True, verbose_name=_("Protein (g)"))
    carbs_g = models.FloatField(default=0.0, blank=True, verbose_name=_("Kohlenhydrate (g)"))
    fat_g = models.FloatField(default=0.0, blank=True, verbose_name=_("Fett (g)"))
    amount = models.CharField(max_length=100, blank=True, verbose_name=_("Menge / Portion"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['date', 'created_at']
        verbose_name = _("Mahlzeit-Protokoll")
        verbose_name_plural = _("Mahlzeit-Protokolle")

    def __str__(self):
        return f"{self.date} [{self.get_meal_type_display()}]: {self.title} ({self.calories} kcal)"

