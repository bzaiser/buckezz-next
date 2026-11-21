from django.db import models
from django.views.generic import TemplateView, ListView, DetailView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, render, redirect
from django.http import HttpResponse, HttpResponseForbidden
from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage
from .models import BucketList, ListItem, ListItemImage, ListCategory, UserSetting, Person, ItemPersonRole, ListParticipant


def _save_item_media_and_subchecklist(request, item, data):
    """Handle single/multi-photo uploads, deletions, and plain or photo-enabled subchecklists."""
    changed = False

    if data.get('delete_main_image') == '1' and item.image:
        item.image.delete(save=False)
        item.image = None
        changed = True

    if 'image' in request.FILES:
        item.image = request.FILES['image']
        changed = True

    for img_file in request.FILES.getlist('images'):
        ListItemImage.objects.create(item=item, image=img_file)

    delete_ids = [int(i) for i in data.getlist('delete_image_ids') if str(i).isdigit()]
    if delete_ids:
        item.images.filter(id__in=delete_ids).delete()

    if 'sub_title' in data:
        existing_states = {
            s.get('title'): s.get('done', False)
            for s in (item.subchecklist_json or [])
            if isinstance(s, dict)
        }
        titles = data.getlist('sub_title')
        existing_imgs = data.getlist('sub_existing_image')
        sub_items = []
        for idx, raw_title in enumerate(titles):
            title = raw_title.strip()
            if not title:
                continue
            img_url = existing_imgs[idx].strip() if idx < len(existing_imgs) else ''
            file_key = f'sub_image_{idx}'
            if file_key in request.FILES:
                f = request.FILES[file_key]
                saved_path = default_storage.save(f'subchecklist_photos/{f.name}', f)
                img_url = default_storage.url(saved_path)
            entry = {'title': title, 'done': existing_states.get(title, False)}
            if img_url:
                entry['image'] = img_url
            sub_items.append(entry)
        item.subchecklist_json = sub_items
        changed = True
    else:
        raw_checklist = data.get('subchecklist_text')
        if raw_checklist is not None:
            existing_states = {
                s.get('title'): s.get('done', False)
                for s in (item.subchecklist_json or [])
                if isinstance(s, dict)
            }
            sub_items = []
            for line in raw_checklist.splitlines():
                line = line.strip()
                if line:
                    sub_items.append({'title': line, 'done': existing_states.get(line, False)})
            item.subchecklist_json = sub_items
            changed = True

    if changed:
        item.save()


def _save_custom_data(request, item, tpl, data):
    """Persist custom_fields_json values (including files, multiselect, radio, url) into item.custom_data_json."""
    fields = getattr(tpl, 'custom_fields_json', None) or []
    if not fields:
        return
    custom_data = dict(item.custom_data_json) if isinstance(item.custom_data_json, dict) else {}
    for f in fields:
        key = f.get('key')
        if not key:
            continue
        ftype = f.get('type', 'text')
        post_key = f'custom_{key}'
        if ftype == 'checkbox':
            custom_data[key] = data.get(post_key) in ('on', 'true', '1')
        elif ftype == 'multiselect':
            custom_data[key] = [v.strip() for v in data.getlist(post_key) if v.strip()]
        elif ftype == 'image':
            if data.get(f'custom_clear_{key}') == '1':
                custom_data[key] = ''
            file_key = f'custom_file_{key}'
            if file_key in request.FILES:
                up = request.FILES[file_key]
                saved_path = default_storage.save(f'custom_field_photos/{up.name}', up)
                custom_data[key] = default_storage.url(saved_path)
        elif post_key in data:
            custom_data[key] = data.get(post_key, '').strip()
    item.custom_data_json = custom_data
    item.save()


def _apply_recurrence_resets(bucket):
    """Automatically reopen completed items whose recurrence window has elapsed."""
    from django.utils import timezone
    from datetime import timedelta

    tpl = bucket.category.template
    rec = tpl.recurrence_json if isinstance(tpl.recurrence_json, dict) else {}
    mode = rec.get('mode', 'none')
    if not mode or mode == 'none':
        return

    now = timezone.localtime(timezone.now())
    if mode == 'daily':
        cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif mode == 'weekly':
        cutoff = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    elif mode == 'monthly':
        cutoff = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif mode == 'days':
        try:
            days = max(1, int(rec.get('interval_days', 7)))
        except (TypeError, ValueError):
            days = 7
        cutoff = now - timedelta(days=days)
    else:
        return

    bucket.items.filter(is_completed=True, completed_at__lt=cutoff).update(
        is_completed=False, status='active', completed_at=None
    )


def _get_effective_ui_style(request, bucket):
    """Return template ui_style merged with per-list session layout override."""
    ui = bucket.category.template.get_ui_style()
    overrides = request.session.get('list_layout_overrides') or {}
    override_mode = overrides.get(str(bucket.id))
    if override_mode in ('row', 'cards', 'stacked'):
        ui['layout_mode'] = override_mode
    return ui


def _compute_kpi_summary(tpl, active_items, completed_items):
    """Compute flexible KPI aggregation (sum/avg/count) from summary_rule_json."""
    rule = tpl.summary_rule_json if isinstance(tpl.summary_rule_json, dict) else {}
    if not rule.get('enabled'):
        return None
    field = rule.get('field', 'price')
    op = rule.get('op', 'sum')
    status_filter = (rule.get('status_filter') or '').strip()
    label = rule.get('label') or 'Auswertung'
    unit = rule.get('unit') or ''

    def extract_num(it):
        if field == 'price':
            return float(it.price) if it.price is not None else None
        if field == 'amount_value':
            return float(it.amount_value) if it.amount_value is not None else None
        if field.startswith('custom:'):
            ckey = field.split(':', 1)[1]
            raw = (it.custom_data_json or {}).get(ckey)
            if raw is None or raw == '':
                return None
            try:
                return float(str(raw).replace(',', '.'))
            except ValueError:
                return None
        return None

    if status_filter == 'open':
        target_items = list(active_items)
    elif status_filter == 'completed':
        target_items = list(completed_items)
    elif status_filter:
        target_items = [i for i in (*active_items, *completed_items) if i.status == status_filter]
    else:
        target_items = list(active_items) + list(completed_items)

    active_vals = [v for v in (extract_num(i) for i in active_items) if v is not None]
    target_vals = [v for v in (extract_num(i) for i in target_items) if v is not None]

    if op == 'count':
        active_val = len(active_items)
        total_val = len(target_items)
    elif op == 'avg':
        active_val = round(sum(active_vals) / len(active_vals), 2) if active_vals else 0
        total_val = round(sum(target_vals) / len(target_vals), 2) if target_vals else 0
    else:
        active_val = round(sum(active_vals), 2)
        total_val = round(sum(target_vals), 2)

    def fmt_val(val):
        if unit in ('€', 'EUR'):
            num_str = f"{val:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        elif float(val).is_integer():
            num_str = str(int(val))
        else:
            num_str = str(val).replace('.', ',')
        return f"{num_str} {unit}".strip() if unit else num_str

    return {
        'field': field,
        'label': label,
        'unit': unit,
        'op': op,
        'active_value': active_val,
        'total_value': total_val,
        'total_display': fmt_val(total_val),
        'open_count': len(active_items),
        'done_count': len(completed_items),
        'counts_display': f"{len(active_items)} / {len(completed_items)}",
    }


def _collect_item_alerts(tpl, active_items, completed_items=None):
    """Evaluate declarative Wenn-Dann warning rules and non-blocking plausibility checks."""
    from django.utils import timezone
    rules = tpl.logic_rules_json if isinstance(tpl.logic_rules_json, dict) else {}
    alerts = []
    now = timezone.now()
    if rules.get('notify_on_overdue'):
        overdue = [i.title for i in active_items if i.end_date and i.end_date < now]
        if overdue:
            alerts.append({'level': 'danger', 'text': f"Überfällig ({len(overdue)}): {', '.join(overdue[:5])}"})
    if rules.get('notify_on_low_stock'):
        low = [
            i.title for i in active_items
            if i.tracker_stock_total is not None and i.tracker_stock_min is not None and i.tracker_stock_total <= i.tracker_stock_min
        ]
        if low:
            alerts.append({'level': 'warning', 'text': f"Niedriger Vorrat ({len(low)}): {', '.join(low[:5])}"})

    # Non-blocking plausibility checks across all items
    status_map = {s['key']: s for s in tpl.get_effective_statuses() if isinstance(s, dict) and s.get('key')}
    role_map = {r['key']: r for r in tpl.get_effective_roles() if isinstance(r, dict) and r.get('key')}
    sale_keys = [
        cf.get('key') for cf in (tpl.custom_fields_json or [])
        if isinstance(cf, dict) and cf.get('key') and any(k in f"{cf.get('key','')} {cf.get('label','')}".lower() for k in ('verkaufspreis', 'sale_price', 'erloes', 'erlös'))
    ]
    all_items = list(active_items) + list(completed_items or [])
    for it in all_items:
        st_info = status_map.get(it.status) or {}
        st_label = (st_info.get('label') or it.status or '').lower()
        st_completes = bool(st_info.get('completes')) or it.is_completed
        roles = list(it.person_roles.all())
        is_sold = ('verkauft' in st_label) or (it.status == 'sold')
        is_for_sale = (it.status == 'for_sale') or any(w in st_label for w in ('zum verkauf', 'inseriert', 'angebot'))

        if not st_completes and roles:
            for r in roles:
                r_info = role_map.get(r.role) or {}
                r_lbl = (r_info.get('label') or r.get_role_display() or r.role or '').lower()
                if r_info.get('completes') or r.role == 'fulfilled' or any(w in r_lbl for w in ('käufer', 'verkauf', 'erfüllt')):
                    alerts.append({'level': 'warning', 'text': f"„{it.title}“: Status noch offen, aber Abschluss-/Verkaufsrolle zugewiesen."})
                    break

        if ('verliehen' in st_label or it.status in ('lent_out', 'lent_to')) and not roles:
            alerts.append({'level': 'warning', 'text': f"„{it.title}“: Status ‚Verliehen‘ ohne zugewiesene Person."})

        if ('ausgeliehen' in st_label or it.status == 'borrowed') and (tpl.use_end_date or tpl.use_reminder) and not it.end_date and not it.reminder_at:
            alerts.append({'level': 'warning', 'text': f"„{it.title}“: Ausgeliehen ohne Rückgabedatum oder Erinnerung."})

        cf_data = it.custom_data_json if isinstance(it.custom_data_json, dict) else {}
        has_sale_val = any(cf_data.get(sk) not in (None, '') for sk in sale_keys)
        if is_sold:
            if (sale_keys and not has_sale_val) or (not sale_keys and tpl.use_price and not it.price):
                alerts.append({'level': 'warning', 'text': f"„{it.title}“: Status ‚Verkauft‘ ohne Verkaufspreis."})
        elif is_for_sale:
            if sale_keys and not has_sale_val:
                alerts.append({'level': 'warning', 'text': f"„{it.title}“: Status ‚Zum Verkauf‘, aber noch kein Preis eingetragen."})
        elif has_sale_val:
            alerts.append({'level': 'warning', 'text': f"„{it.title}“: Verkaufspreis eingetragen, Status steht weder auf ‚Zum Verkauf‘ noch auf ‚Verkauft‘."})

        if it.start_date and it.end_date and it.end_date < it.start_date:
            alerts.append({'level': 'warning', 'text': f"„{it.title}“: Enddatum liegt vor dem Startdatum."})

    return alerts[:8]


def _group_items_by_rule(tpl, active_items, completed_items, beneficiary):
    """Group items by configured group_by rule (milestone, status, person, shop, brand, location)."""
    mode = tpl.get_effective_group_by()
    if mode == 'milestone':
        return group_items_by_milestone(active_items, completed_items, beneficiary)
    if mode == 'none':
        return [], []

    def key_for(item):
        if mode == 'status':
            info = item.effective_status_info
            if info:
                return info['label']
            if tpl.allowed_statuses_json:
                first_open = next((s.get('label') for s in tpl.get_effective_statuses() if not s.get('completes')), None)
                if first_open:
                    return first_open
            return item.get_status_display()
        if mode == 'person':
            roles = list(item.person_roles.all())
            return roles[0].person.name if roles else 'Nicht zugewiesen'
        if mode == 'shop':
            return item.shop or 'Ohne Geschäft'
        if mode == 'brand':
            return item.brand or 'Ohne Marke'
        if mode == 'location':
            return item.location or 'Ohne Ort'
        return 'Allgemein'

    def build_groups(items):
        buckets = {}
        for it in items:
            lbl = key_for(it)
            buckets.setdefault(lbl, []).append(it)
        return [{'key': k, 'label': k, 'items': v, 'is_current': False} for k, v in buckets.items()]

    return build_groups(active_items), build_groups(completed_items)

class HomeView(TemplateView):
    template_name = 'core/home.html'

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated and 'start' not in request.GET:
            return redirect('core:dashboard')
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        person_id = self.request.session.get('person_id')
        
        if user.is_authenticated:
            if user.is_superuser:
                context['my_lists'] = BucketList.objects.all()
                allowed_lists = BucketList.objects.all()
            else:
                context['my_lists'] = BucketList.objects.filter(owner=user)
                allowed_lists = BucketList.objects.filter(
                    models.Q(owner=user) | models.Q(shared_with=user) | models.Q(participants__person__user=user)
                ).distinct()
        elif person_id:
            allowed_lists = BucketList.objects.filter(
                participants__person_id=person_id
            ).distinct()
        else:
            allowed_lists = BucketList.objects.none()
            
        context['categories'] = ListCategory.objects.prefetch_related(
            models.Prefetch('lists', queryset=allowed_lists, to_attr='visible_lists')
        )
        return context

class DashboardView(LoginRequiredMixin, ListView):
    model = BucketList
    template_name = 'core/dashboard.html'
    context_object_name = 'lists'

    def get_queryset(self):
        if self.request.user.is_superuser:
            return BucketList.objects.all()
        return BucketList.objects.filter(
            models.Q(owner=self.request.user) | models.Q(shared_with=self.request.user)
        ).distinct()
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = ListCategory.objects.all()
        return context

class CreateBucketView(LoginRequiredMixin, View):
    def post(self, request):
        category_id = request.POST.get('category_id')
        title = request.POST.get('title')
        
        if not category_id or not title:
            return redirect('core:dashboard')
            
        category = get_object_or_404(ListCategory, id=category_id)
        bucket = BucketList.objects.create(
            owner=request.user,
            category=category,
            title=title
        )
        return redirect('core:list_detail', pk=bucket.id)

import re

def get_price_sums(bucket, active_items, completed_items):
    active_sum = 0.0
    completed_sum = 0.0
    
    def parse_amount(amount_str):
        if not amount_str:
            return 1.0
        s = amount_str.strip()
        if not s:
            return 1.0
        # Search for first integer or decimal number (supporting both dot and comma)
        match = re.search(r'([0-9]+(?:[.,][0-9]+)?)', s)
        if match:
            num_str = match.group(1).replace(',', '.')
            try:
                val = float(num_str)
                return val if val > 0 else 1.0
            except ValueError:
                pass
        return 1.0
    
    status_price_breakdown = []
    tpl = bucket.category.template
    if tpl.use_price:
        use_amount = tpl.use_amount
        custom_statuses = tpl.get_effective_statuses() if tpl.allowed_statuses_json else []
        status_buckets = {s['key']: 0.0 for s in custom_statuses if isinstance(s, dict) and s.get('key')}
        fallback_open_key = next((s['key'] for s in custom_statuses if not s.get('completes')), None)

        def _item_price_total(it):
            if not it.price:
                return 0.0
            amount = float(it.amount_value) if (use_amount and it.amount_value is not None) else (parse_amount(it.amount) if use_amount else 1.0)
            return float(it.price) * amount

        for item in active_items:
            val = _item_price_total(item)
            if val:
                active_sum += val
                if custom_statuses:
                    k = item.status if item.status in status_buckets else fallback_open_key
                    if k:
                        status_buckets[k] = status_buckets.get(k, 0.0) + val
        for item in completed_items:
            val = _item_price_total(item)
            if val:
                completed_sum += val
                if custom_statuses:
                    k = item.status if item.status in status_buckets else next((s['key'] for s in custom_statuses if s.get('completes')), None)
                    if k:
                        status_buckets[k] = status_buckets.get(k, 0.0) + val

        for st in custom_statuses:
            k = st.get('key')
            s_val = status_buckets.get(k, 0.0)
            if s_val > 0:
                status_price_breakdown.append({
                    'key': k,
                    'label': st.get('label', k),
                    'completes': bool(st.get('completes')),
                    'sum': s_val,
                })

    return {
        'active_price_sum': active_sum,
        'completed_price_sum': completed_sum,
        'total_price_sum': active_sum + completed_sum,
        'status_price_breakdown': status_price_breakdown,
    }

def get_list_items_for_user(request, bucket):
    # Get current person from session or user profile
    current_person = None
    person_id = request.session.get('person_id')
    if person_id:
        try:
            current_person = Person.objects.get(id=person_id)
        except Person.DoesNotExist:
            pass
    elif request.user.is_authenticated:
        try:
            current_person = request.user.person_profile
        except Person.DoesNotExist:
            pass
            
    is_beneficiary = False
    if bucket.is_secret_santa and bucket.beneficiary and current_person == bucket.beneficiary:
        is_beneficiary = True

    if bucket.category.template.new_items_at_bottom:
        items = bucket.items.order_by('order', 'created_at')
    else:
        items = bucket.items.order_by('order', '-created_at')
    
    # Live Search Filter
    q = request.GET.get('q')
    if q:
        items = items.filter(title__icontains=q.strip())
        
    if is_beneficiary:
        # Beneficiary sees all items as active (hiding completed/fulfilled ones)
        active_items = list(items)
        completed_items = []
    else:
        active_items = [i for i in items if not i.is_completed]
        completed_items = [i for i in items if i.is_completed]
        
    return active_items, completed_items, is_beneficiary, current_person

def group_items_by_milestone(active_items, completed_items, beneficiary):
    milestones_cfg = [
        ('before_30', 'Vor 30'),
        ('before_40', 'Vor 40'),
        ('before_50', 'Vor 50'),
        ('before_60', 'Vor 60'),
        ('before_die', 'Bevor ich sterbe'),
        ('', 'Ohne Meilenstein')
    ]
    
    active_focus = beneficiary.active_milestone if beneficiary else None
    
    grouped_active = []
    for slug, label in milestones_cfg:
        m_items = [i for i in active_items if (i.target_milestone or '') == slug]
        if m_items:
            grouped_active.append({
                'slug': slug,
                'label': label,
                'items': m_items,
                'is_current': slug == active_focus
            })
            
    grouped_completed = []
    for slug, label in milestones_cfg:
        m_items = [i for i in completed_items if (i.target_milestone or '') == slug]
        if m_items:
            grouped_completed.append({
                'slug': slug,
                'label': label,
                'items': m_items
            })
            
    if active_focus:
        milestone_order = ['before_30', 'before_40', 'before_50', 'before_60', 'before_die', '']
        try:
            focus_idx = milestone_order.index(active_focus)
        except ValueError:
            focus_idx = 0
            
        def sort_weight(group):
            slug = group['slug']
            if slug == active_focus:
                return 0
            if not slug:
                return 100
            try:
                idx = milestone_order.index(slug)
            except ValueError:
                idx = 99
            if idx > focus_idx:
                return idx
            else:
                return 50 + idx
                
        grouped_active.sort(key=sort_weight)
        
    return grouped_active, grouped_completed, active_focus

class BucketListDetailView(DetailView):
    template_name = 'core/list_detail.html'
    context_object_name = 'bucket'

    def get_queryset(self):
        return BucketList.objects.all()

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        # Check permissions
        is_owner = obj.owner == self.request.user
        is_shared = self.request.user.is_authenticated and self.request.user in obj.shared_with.all()
        is_admin = self.request.user.is_authenticated and self.request.user.is_superuser
        
        # If public or is_secret_santa (which works with personalized links) or superuser/admin
        if not (is_owner or is_shared or obj.is_public or obj.is_secret_santa or is_admin):
            raise PermissionDenied("Zugriff verweigert.")
        return obj

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        
        # Personalized token auto-login
        token_str = request.GET.get('p')
        if token_str:
            try:
                person = Person.objects.get(access_token=token_str)
                request.session['person_id'] = person.id
                request.session['guest_name'] = person.name
            except (Person.DoesNotExist, ValueError):
                pass
                
        # Access control for Secret Santa lists
        if self.object.is_secret_santa:
            is_owner = self.object.owner == request.user
            person_id = request.session.get('person_id')
            
            # Auto-associate logged in user's person profile
            if request.user.is_authenticated and not person_id:
                try:
                    person = request.user.person_profile
                    request.session['person_id'] = person.id
                    request.session['guest_name'] = person.name
                except Person.DoesNotExist:
                    pass
                    
            if not is_owner and not request.session.get('person_id'):
                return render(request, 'core/secret_santa_error.html', {'bucket': self.object})
        elif not request.user.is_authenticated and not request.session.get('guest_name'):
            return render(request, 'core/guest_login.html', {'bucket': self.object})
            
        # Trigger Edeka Microsoft To-Do real-time sync (throttled to once every 10 seconds per session)
        tpl = self.object.category.template
        if self.object.todo_sync_url and (tpl.logic_type == 'todo' or tpl.get_logic_rule('enable_ical_sync')):
            import time
            session_key = f'last_todo_sync_{self.object.id}'
            last_sync = request.session.get(session_key, 0)
            now = time.time()
            if now - last_sync > 10:
                sync_microsoft_todo(self.object)
                request.session[session_key] = now

        context = self.get_context_data(object=self.object)
        if request.headers.get('HX-Request') == 'true' and 'q' in request.GET:
            return render(request, 'core/partials/item_list.html', context)
        return self.render_to_response(context)

    def post(self, request, *args, **kwargs):
        guest_name = request.POST.get('guest_name')
        if guest_name:
            request.session['guest_name'] = guest_name.strip()
        return redirect('core:list_detail', pk=self.kwargs['pk'])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        bucket = self.get_object()
        _apply_recurrence_resets(bucket)

        active_items, completed_items, is_beneficiary, current_person = get_list_items_for_user(self.request, bucket)
        tpl = bucket.category.template

        grouped_active = None
        grouped_completed = None
        group_mode = tpl.get_effective_group_by()
        if group_mode == 'milestone':
            beneficiary = bucket.beneficiary_person
            grouped_active, grouped_completed, _ = group_items_by_milestone(active_items, completed_items, beneficiary)
        elif group_mode != 'none':
            grouped_active, grouped_completed = _group_items_by_rule(tpl, active_items, completed_items, bucket.beneficiary_person)

        is_owner = bucket.owner == self.request.user
        is_admin = self.request.user.is_authenticated and self.request.user.is_superuser
        if bucket.is_secret_santa:
            can_edit = is_owner or is_beneficiary or is_admin
        else:
            can_edit = is_owner or is_admin or \
                      (self.request.user.is_authenticated and self.request.user in bucket.shared_with.all()) or \
                      (bucket.is_public and bucket.allow_public_edit)

        context['can_edit'] = can_edit
        context['active_items'] = active_items
        context['completed_items'] = completed_items
        context['grouped_active'] = grouped_active
        context['grouped_completed'] = grouped_completed
        context['effective_group_by'] = group_mode
        context['ui'] = _get_effective_ui_style(self.request, bucket)
        context['kpi_summary'] = _compute_kpi_summary(tpl, active_items, completed_items)
        context['item_alerts'] = _collect_item_alerts(tpl, active_items, completed_items)
        context['is_beneficiary'] = is_beneficiary
        context['current_person'] = current_person
        context['people'] = Person.objects.all()
        
        sums = get_price_sums(bucket, active_items, completed_items)
        context.update(sums)
        
        # Inject workout specific details
        if bucket.category.template.logic_type == 'workout':
            sessions_qs = bucket.workout_sessions.all().prefetch_related('activities')
            context['workout_sessions'] = sessions_qs
            
            import json
            from django.core.serializers.json import DjangoJSONEncoder
            sessions_data = []
            for session in reversed(sessions_qs):
                session_dict = {
                    'id': session.id,
                    'date': session.date.strftime('%d.%m.%Y'),
                    'isoDate': session.date.strftime('%Y-%m-%d'),
                    'duration_minutes': round(session.duration_seconds / 60),
                    'rating': session.rating,
                    'notes': session.notes,
                    'activities': []
                }
                for act in session.activities.all():
                    session_dict['activities'].append({
                        'title': act.title,
                        'type': act.activity_type,
                        'data': act.logged_data_json
                    })
                sessions_data.append(session_dict)
            context['workout_sessions_json'] = json.dumps(sessions_data, cls=DjangoJSONEncoder)
            
            if self.request.user.is_authenticated:
                from core.models import UserSetting
                user_settings, _ = UserSetting.objects.get_or_create(user=self.request.user)
                context['user_settings'] = user_settings

        # Inject nutrition specific details
        elif bucket.category.template.logic_type == 'nutrition':
            import json
            from django.core.serializers.json import DjangoJSONEncoder
            from core.models import NutritionGoal, WeightLog, NutritionMealLog
            from datetime import date

            goal, _ = NutritionGoal.objects.get_or_create(bucket_list=bucket)
            context['nutrition_goal'] = goal
            context['nutrition_goal_json'] = json.dumps({
                'start_weight': float(goal.start_weight) if goal.start_weight else None,
                'target_weight': float(goal.target_weight) if goal.target_weight else None,
                'target_calories': goal.target_calories or 2000,
                'gender': goal.gender or 'male',
                'age': goal.age,
                'height_cm': goal.height_cm,
                'activity_level': float(goal.activity_level or 1.2),
                'goal_type': goal.goal_type or 'lose',
                'target_protein_g': goal.target_protein_g or 140,
                'target_carbs_g': goal.target_carbs_g or 220,
                'target_fat_g': goal.target_fat_g or 65,
                'target_water_ml': goal.target_water_ml or 2500,
            }, cls=DjangoJSONEncoder)

            weight_logs = list(bucket.weight_logs.order_by('date'))
            context['weight_logs'] = weight_logs
            context['latest_weight'] = weight_logs[-1].weight if weight_logs else goal.start_weight

            weight_chart_data = [
                {
                    'id': w.id,
                    'date': w.date.strftime('%d.%m.%Y'),
                    'isoDate': w.date.strftime('%Y-%m-%d'),
                    'weight': float(w.weight),
                    'note': w.note
                } for w in weight_logs
            ]
            context['weight_chart_data_json'] = json.dumps(weight_chart_data, cls=DjangoJSONEncoder)

            meals_qs = bucket.nutrition_meal_logs.order_by('date', 'created_at')
            meals_data = [
                {
                    'id': m.id,
                    'date': m.date.strftime('%Y-%m-%d'),
                    'meal_type': m.meal_type,
                    'meal_type_display': m.get_meal_type_display(),
                    'title': m.title,
                    'calories': m.calories,
                    'protein_g': m.protein_g,
                    'carbs_g': m.carbs_g,
                    'fat_g': m.fat_g,
                    'amount': m.amount,
                } for m in meals_qs
            ]
            context['nutrition_meals_json'] = json.dumps(meals_data, cls=DjangoJSONEncoder)
            context['today_iso'] = date.today().strftime('%Y-%m-%d')
        
        return context

def render_item_list(request, bucket, can_edit):
    _apply_recurrence_resets(bucket)
    active_items, completed_items, is_beneficiary, current_person = get_list_items_for_user(request, bucket)
    tpl = bucket.category.template

    grouped_active = None
    grouped_completed = None
    group_mode = tpl.get_effective_group_by()
    if group_mode == 'milestone':
        beneficiary = bucket.beneficiary_person
        grouped_active, grouped_completed, _ = group_items_by_milestone(active_items, completed_items, beneficiary)
    elif group_mode != 'none':
        grouped_active, grouped_completed = _group_items_by_rule(tpl, active_items, completed_items, bucket.beneficiary_person)

    is_owner = bucket.owner == request.user
    if bucket.is_secret_santa:
        can_edit = is_owner or is_beneficiary
    else:
        can_edit = is_owner or \
                  (request.user.is_authenticated and request.user in bucket.shared_with.all()) or \
                  (bucket.is_public and bucket.allow_public_edit)

    sums = get_price_sums(bucket, active_items, completed_items)

    context = {
        'bucket': bucket,
        'active_items': active_items,
        'completed_items': completed_items,
        'grouped_active': grouped_active,
        'grouped_completed': grouped_completed,
        'effective_group_by': group_mode,
        'ui': _get_effective_ui_style(request, bucket),
        'kpi_summary': _compute_kpi_summary(tpl, active_items, completed_items),
        'item_alerts': _collect_item_alerts(tpl, active_items, completed_items),
        'can_edit': can_edit,
        'is_beneficiary': is_beneficiary,
        'current_person': current_person
    }
    context.update(sums)
    return render(request, 'core/partials/item_list.html', context)


class ToggleListLayoutView(View):
    def post(self, request, pk):
        bucket = get_object_or_404(BucketList, id=pk)
        layout_mode = request.POST.get('layout_mode', 'row')
        if layout_mode not in ('row', 'cards', 'stacked'):
            layout_mode = 'row'
        overrides = dict(request.session.get('list_layout_overrides') or {})
        overrides[str(bucket.id)] = layout_mode
        request.session['list_layout_overrides'] = overrides
        request.session.modified = True
        return render_item_list(request, bucket, False)


class BucketListConfigureView(LoginRequiredMixin, View):
    """Frontend configuration page for a BucketList (replaces Django Admin redirect)."""

    def _get_authorized_bucket(self, request, pk):
        bucket = get_object_or_404(BucketList.objects.select_related('category__template', 'owner'), id=pk)
        if bucket.owner != request.user and not request.user.is_superuser:
            return None
        return bucket

    def get(self, request, pk):
        bucket = self._get_authorized_bucket(request, pk)
        if not bucket:
            return HttpResponseForbidden("Nur der Besitzer darf diese Liste konfigurieren.")
        return render(request, 'core/list_configure.html', {
            'bucket': bucket,
            'categories': ListCategory.objects.select_related('template').order_by('name'),
            'people': Person.objects.order_by('name'),
            'users': User.objects.exclude(id=bucket.owner_id).order_by('username'),
            'shared_user_ids': set(bucket.shared_with.values_list('id', flat=True)),
        })

    def post(self, request, pk):
        bucket = self._get_authorized_bucket(request, pk)
        if not bucket:
            return HttpResponseForbidden("Nur der Besitzer darf diese Liste konfigurieren.")

        title = (request.POST.get('title') or '').strip()
        if title:
            bucket.title = title[:255]

        cat_id = request.POST.get('category')
        if cat_id:
            cat = ListCategory.objects.filter(id=cat_id).first()
            if cat:
                bucket.category = cat

        bucket.is_public = request.POST.get('is_public') == 'on'
        bucket.allow_public_edit = request.POST.get('allow_public_edit') == 'on'
        bucket.is_secret_santa = request.POST.get('is_secret_santa') == 'on'
        bucket.todo_sync_url = (request.POST.get('todo_sync_url') or '').strip() or None

        ben_id = request.POST.get('beneficiary')
        bucket.beneficiary = Person.objects.filter(id=ben_id).first() if ben_id else None
        bucket.save()

        shared_ids = [uid for uid in request.POST.getlist('shared_with') if uid.isdigit()]
        bucket.shared_with.set(User.objects.filter(id__in=shared_ids).exclude(id=bucket.owner_id))

        messages.success(request, f"Einstellungen für „{bucket.title}“ gespeichert.")
        return redirect('core:list_detail', pk=bucket.id)


class BucketListDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        bucket = get_object_or_404(BucketList, id=pk)
        if bucket.owner != request.user and not request.user.is_superuser:
            return HttpResponseForbidden("Nur der Besitzer darf diese Liste löschen.")
        title = bucket.title
        bucket.delete()
        messages.success(request, f"Liste „{title}“ wurde gelöscht.")
        return redirect('core:dashboard')

class GetItemFormView(View):
    def get(self, request, bucket_id, item_id=None):
        bucket = get_object_or_404(BucketList, id=bucket_id)
        
        # 1. View Permission Check
        is_owner = bucket.owner == request.user
        is_shared = request.user.is_authenticated and request.user in bucket.shared_with.all()
        is_admin = request.user.is_authenticated and request.user.is_superuser
        
        # Secret Santa session checks
        person_id = request.session.get('person_id')
        current_person = None
        if person_id:
            try:
                current_person = Person.objects.get(id=person_id)
            except Person.DoesNotExist:
                pass
        
        is_beneficiary = False
        if bucket.is_secret_santa and bucket.beneficiary and current_person == bucket.beneficiary:
            is_beneficiary = True

        can_view = is_owner or is_shared or bucket.is_public or (bucket.is_secret_santa and (is_owner or person_id)) or is_admin
        if not can_view:
            return HttpResponseForbidden("Zugriff verweigert.")
            
        # 2. Edit Permission Check
        if bucket.is_secret_santa:
            can_edit = is_owner or is_beneficiary or is_admin
        else:
            can_edit = is_owner or is_shared or (bucket.is_public and bucket.allow_public_edit) or is_admin
            
        item = None
        gift_status = "open"
        gift_person = None
        if item_id:
            item = get_object_or_404(ListItem, id=item_id)
            gift_role = item.person_roles.filter(role__in=['reserved', 'fulfilled']).first()
            if gift_role:
                gift_status = gift_role.role
                gift_person = gift_role.person
        
        from domain_kit.models import Unit
        units = Unit.objects.all().order_by('position', 'name')
        people = Person.objects.all()
        raw_cf = getattr(bucket.category.template, 'custom_fields_json', None) or []
        item_cf_data = (item.custom_data_json if item and isinstance(item.custom_data_json, dict) else {})
        custom_fields_with_values = []
        for cf in raw_cf:
            key = cf.get('key')
            if not key:
                continue
            opts = [o.strip() for o in (cf.get('options') or '').split(',') if o.strip()]
            raw_val = item_cf_data.get(key, '')
            custom_fields_with_values.append({
                'key': key,
                'label': cf.get('label', key),
                'type': cf.get('type', 'text'),
                'options_list': opts,
                'currency_code': (cf.get('options') or '€').strip() or '€',
                'value': raw_val,
                'value_list': raw_val if isinstance(raw_val, list) else [],
            })

        return render(request, 'core/partials/item_form.html', {
            'bucket': bucket,
            'item': item,
            'people': people,
            'can_edit': can_edit,
            'is_beneficiary': is_beneficiary,
            'current_person': current_person,
            'gift_status': gift_status,
            'gift_person': gift_person,
            'units': units,
            'custom_fields_with_values': custom_fields_with_values,
        })

def _apply_item_status(request, bucket, item, item_status):
    """Apply submitted item_status (gift, standard open/completed, or custom allowed_statuses_json)."""
    if not item_status:
        return
    person_id = request.session.get('person_id')
    current_person = None
    if person_id:
        current_person = Person.objects.filter(id=person_id).first()
    if not current_person and request.user.is_authenticated:
        current_person = Person.objects.filter(user=request.user).first()

    if bucket.category.template.logic_type == 'gift':
        if item_status == 'open':
            item.person_roles.filter(role__in=['reserved', 'fulfilled']).delete()
            item.is_completed = False
        elif item_status in ['reserved', 'fulfilled'] and current_person:
            item.person_roles.filter(role__in=['reserved', 'fulfilled']).delete()
            role, _ = ItemPersonRole.objects.get_or_create(item=item, person=current_person)
            role.role = item_status
            role.save()
            item.is_completed = (item_status == 'fulfilled')
        return

    statuses = {s['key']: s for s in bucket.category.template.get_effective_statuses()}
    if item_status == 'completed':
        item.is_completed = True
        item.status = 'done'
    elif item_status == 'open':
        item.is_completed = False
        item.status = 'active'
    elif item_status in statuses:
        item.is_completed = bool(statuses[item_status].get('completes', False))
        item.status = item_status[:20]


class AddItemView(View):
    def post(self, request, bucket_id):
        bucket = get_object_or_404(BucketList, id=bucket_id)
        can_edit = bucket.owner == request.user or \
                  (request.user.is_authenticated and request.user in bucket.shared_with.all()) or \
                  (bucket.is_public and bucket.allow_public_edit) or \
                  (request.user.is_authenticated and request.user.is_superuser)
        if not can_edit:
            return HttpResponseForbidden()

        data = request.POST
        guest_name = request.session.get('guest_name')
        
        from decimal import Decimal
        amount_value = None
        if data.get('amount_value'):
            try:
                amount_value = Decimal(data.get('amount_value').replace(',', '.'))
            except Exception:
                pass
                
        # Determine the order for the new item based on the template setting
        from django.db.models import Max
        if bucket.category.template.new_items_at_bottom:
            max_order = bucket.items.aggregate(Max('order'))['order__max'] or 0
            order_val = max_order + 1
        else:
            order_val = 0

        item = ListItem.objects.create(
            bucket_list=bucket,
            title=data.get('title'),
            amount=data.get('amount'),
            amount_value=amount_value,
            unit_id=data.get('unit_id') if data.get('unit_id') else None,
            price=data.get('price') if data.get('price') else None,
            brand=data.get('brand'),
            shop=data.get('shop'),
            location=data.get('location'),
            url=data.get('url'),
            start_date=data.get('start_date') if data.get('start_date') else None,
            end_date=data.get('end_date') if data.get('end_date') else None,
            notes=data.get('notes'),
            target_milestone=data.get('target_milestone') if data.get('target_milestone') else None,
            rating=data.get('rating') if data.get('rating') else None,
            tracker_unit=data.get('tracker_unit'),
            tracker_times=data.get('tracker_times'),
            tracker_stock_total=int(data.get('tracker_stock_total')) if data.get('tracker_stock_total') else None,
            tracker_stock_min=int(data.get('tracker_stock_min')) if data.get('tracker_stock_min') else None,
            tracker_dosage_per_take=float(data.get('tracker_dosage_per_take')) if data.get('tracker_dosage_per_take') else 1.0,
            reminder_at=data.get('reminder_at') if data.get('reminder_at') else None,
            created_by=request.user if request.user.is_authenticated else None,
            guest_created_by=guest_name if not request.user.is_authenticated else None,
            workout_type=data.get('workout_type', 'strength'),
            order=order_val
        )
        
        # Save workout config
        workout_type = data.get('workout_type', 'strength')
        if workout_type == 'strength':
            try:
                sets_count = int(data.get('workout_sets_count') or 3)
            except ValueError:
                sets_count = 3
            try:
                rest_time = int(data.get('workout_rest_time') or 120)
            except ValueError:
                rest_time = 120
            item.workout_config_json = {
                'sets_count': sets_count,
                'target_reps': data.get('workout_target_reps', '').strip(),
                'target_weight': data.get('workout_target_weight', '').strip(),
                'rest_time': rest_time
            }
        elif workout_type == 'endurance':
            item.workout_config_json = {
                'target_distance': data.get('workout_target_distance', '').strip(),
                'target_duration': data.get('workout_target_duration', '').strip(),
                'target_pace': data.get('workout_target_pace', '').strip(),
            }
        elif workout_type == 'interval':
            item.workout_config_json = {
                'interval_format': data.get('workout_interval_format', 'AMRAP').strip(),
                'interval_duration': data.get('workout_interval_duration', '').strip(),
            }
        is_invitation = request.POST.get('is_invitation') == 'true'
        item.is_invitation = is_invitation
        item.save()
        _save_item_media_and_subchecklist(request, item, data)
        _save_custom_data(request, item, bucket.category.template, data)
        
        # Handle persons
        tpl = bucket.category.template
        person_ids = request.POST.getlist('persons')
        if person_ids:
            effective_roles = tpl.get_effective_roles()
            allowed_role_keys = {r['key'] for r in effective_roles}
            requested_role = request.POST.get('person_default_role', '').strip()
            default_role = requested_role if requested_role in allowed_role_keys else (effective_roles[0]['key'] if tpl.allowed_roles_json and effective_roles else 'assigned')
            for pid in person_ids:
                ItemPersonRole.objects.create(item=item, person_id=pid, role=default_role)
                
        # Auto-invite all other participants if event list or invitation rule is active
        if (tpl.logic_type == 'event' or tpl.get_logic_rule('enable_event_invitations')) and is_invitation:
            participant_pids = set(bucket.participants.values_list('person_id', flat=True))
            organizer_pids = set(int(pid) for pid in person_ids)
            invited_pids = participant_pids - organizer_pids
            for pid in invited_pids:
                ItemPersonRole.objects.get_or_create(item=item, person_id=pid, defaults={'role': 'invited'})
        
        # Handle custom status box
        item_status = request.POST.get('item_status')
        if item_status:
            _apply_item_status(request, bucket, item, item_status)
            item.save()
        
        if request.htmx:
            return render_item_list(request, bucket, True)
        return HttpResponse(status=204)
 
class EditItemView(View):
    def post(self, request, item_id):
        item = get_object_or_404(ListItem, id=item_id)
        bucket = item.bucket_list
        can_edit = bucket.owner == request.user or \
                  (request.user.is_authenticated and request.user in bucket.shared_with.all()) or \
                  (bucket.is_public and bucket.allow_public_edit) or \
                  (request.user.is_authenticated and request.user.is_superuser)
        if not can_edit:
            return HttpResponseForbidden()
 
        data = request.POST
        item.title = data.get('title')
        
        from decimal import Decimal
        amount_value = None
        if data.get('amount_value'):
            try:
                amount_value = Decimal(data.get('amount_value').replace(',', '.'))
            except Exception:
                pass
        item.amount_value = amount_value
        item.unit_id = data.get('unit_id') if data.get('unit_id') else None
        
        # Keep amount text set to None if amount_value is cleared
        if amount_value is None:
            item.amount = None
            
        item.price = data.get('price') if data.get('price') else None
        item.brand = data.get('brand')
        item.shop = data.get('shop')
        item.location = data.get('location')
        item.url = data.get('url')
        item.start_date = data.get('start_date') if data.get('start_date') else None
        item.end_date = data.get('end_date') if data.get('end_date') else None
        item.notes = data.get('notes')
        item.target_milestone = data.get('target_milestone') if data.get('target_milestone') else None
        item.rating = data.get('rating') if data.get('rating') else None
        
        # Retroactive completion date override for milestone lists
        if item.is_completed and bucket.category.template.use_milestone:
            completed_at_val = data.get('completed_at')
            if completed_at_val:
                from django.utils.dateparse import parse_datetime
                from django.utils import timezone
                parsed = parse_datetime(completed_at_val)
                if parsed:
                    if timezone.is_naive(parsed):
                        parsed = timezone.make_aware(parsed)
                    item.completed_at = parsed
        item.tracker_unit = data.get('tracker_unit')
        item.tracker_times = data.get('tracker_times')
        item.tracker_stock_total = int(data.get('tracker_stock_total')) if data.get('tracker_stock_total') else None
        item.tracker_stock_min = int(data.get('tracker_stock_min')) if data.get('tracker_stock_min') else None
        item.tracker_dosage_per_take = float(data.get('tracker_dosage_per_take')) if data.get('tracker_dosage_per_take') else 1.0
        item.reminder_at = data.get('reminder_at') if data.get('reminder_at') else None
        
        # Save workout config
        workout_type = data.get('workout_type', 'strength')
        item.workout_type = workout_type
        if workout_type == 'strength':
            try:
                sets_count = int(data.get('workout_sets_count') or 3)
            except ValueError:
                sets_count = 3
            try:
                rest_time = int(data.get('workout_rest_time') or 120)
            except ValueError:
                rest_time = 120
            item.workout_config_json = {
                'sets_count': sets_count,
                'target_reps': data.get('workout_target_reps', '').strip(),
                'target_weight': data.get('workout_target_weight', '').strip(),
                'rest_time': rest_time
            }
        elif workout_type == 'endurance':
            item.workout_config_json = {
                'target_distance': data.get('workout_target_distance', '').strip(),
                'target_duration': data.get('workout_target_duration', '').strip(),
                'target_pace': data.get('workout_target_pace', '').strip(),
            }
        elif workout_type == 'interval':
            item.workout_config_json = {
                'interval_format': data.get('workout_interval_format', 'AMRAP').strip(),
                'interval_duration': data.get('workout_interval_duration', '').strip(),
            }
        
        was_completed = item.is_completed
        is_invitation = request.POST.get('is_invitation') == 'true'
        item.is_invitation = is_invitation
        item.save()
        _save_item_media_and_subchecklist(request, item, data)
        _save_custom_data(request, item, bucket.category.template, data)
        
        # Handle persons
        person_ids = request.POST.getlist('persons')
        new_pids = set(int(p) for p in person_ids)
        current_pids = set(item.person_roles.values_list('person_id', flat=True))
        
        tpl = bucket.category.template
        is_event_invitation = ((tpl.logic_type == 'event' or tpl.get_logic_rule('enable_event_invitations')) and is_invitation)
        
        # Remove persons not in the new list (except reserved/fulfilled roles which are status-tracked,
        # and also except invited/attending/declined/maybe if it's an event invitation!)
        if is_event_invitation:
            participant_pids = set(bucket.participants.values_list('person_id', flat=True))
            # Delete roles for people who are NOT in the organizer selection AND are NOT list participants
            # (unless they have status-tracked roles like reserved/fulfilled)
            ItemPersonRole.objects.filter(
                item=item,
                person_id__in=current_pids - new_pids
            ).exclude(
                person_id__in=participant_pids
            ).exclude(
                role__in=['reserved', 'fulfilled']
            ).delete()
        else:
            ItemPersonRole.objects.filter(
                item=item,
                person_id__in=current_pids - new_pids
            ).exclude(
                role__in=['reserved', 'fulfilled']
            ).delete()
            
        # Add new persons or update existing role to default role if they were selected in the form
        effective_roles = bucket.category.template.get_effective_roles()
        allowed_role_keys = {r['key'] for r in effective_roles}
        requested_role = request.POST.get('person_default_role', '').strip()
        default_role = requested_role if requested_role in allowed_role_keys else (effective_roles[0]['key'] if bucket.category.template.allowed_roles_json and effective_roles else 'assigned')
        for pid in new_pids:
            role_obj, created = ItemPersonRole.objects.get_or_create(item=item, person_id=pid)
            if created:
                role_obj.role = default_role
                role_obj.save()
            elif role_obj.role == 'invited':
                # If they were previously invited but now selected as organizer/responsible, upgrade them
                role_obj.role = default_role
                role_obj.save()
                
        # If it is an event invitation, automatically ensure all other list participants have 'invited' (or status) role
        if is_event_invitation:
            participant_pids = set(bucket.participants.values_list('person_id', flat=True))
            invited_pids = participant_pids - new_pids
            for pid in invited_pids:
                ItemPersonRole.objects.get_or_create(
                    item=item,
                    person_id=pid,
                    defaults={'role': 'invited'}
                )
            
        # Handle custom status box
        item_status = request.POST.get('item_status')
        if item_status:
            _apply_item_status(request, bucket, item, item_status)
            # Reset RSVP status if an invitation is reopened
            if was_completed and not item.is_completed and is_event_invitation:
                item.person_roles.exclude(role='assigned').update(role='invited')
            item.save()
        
        if request.htmx:
            return render_item_list(request, bucket, True)
        return HttpResponse(status=204)

class ToggleItemView(View):
    def post(self, request, pk):
        item = get_object_or_404(ListItem, pk=pk)
        bucket = item.bucket_list
        can_edit = bucket.owner == request.user or \
                  (request.user.is_authenticated and request.user in bucket.shared_with.all()) or \
                  (bucket.is_public and bucket.allow_public_edit) or \
                  (request.user.is_authenticated and request.user.is_superuser)
        if not can_edit:
            return HttpResponseForbidden()
        
        item.is_completed = not item.is_completed
        item.status = 'done' if item.is_completed else 'active'
        
        # When main item is toggled, also sync all subchecklist items
        if item.subchecklist_json and isinstance(item.subchecklist_json, list):
            new_sub = []
            for sub in item.subchecklist_json:
                if isinstance(sub, dict):
                    new_sub.append({'title': sub.get('title', ''), 'done': item.is_completed})
            item.subchecklist_json = new_sub

        # Reset guest RSVP roles back to 'invited' if reopened, and clear normal claimed roles
        tpl = bucket.category.template
        if not item.is_completed and (tpl.logic_type == 'event' or tpl.get_logic_rule('enable_event_invitations')):
            if item.is_invitation:
                item.person_roles.exclude(role='assigned').update(role='invited')
            else:
                item.person_roles.all().delete()
            
        if request.user.is_authenticated:
            item.updated_by = request.user
            item.guest_updated_by = None
        else:
            item.updated_by = None
            item.guest_updated_by = request.session.get('guest_name')
            
        item.save()
        
        if request.htmx:
            return render_item_list(request, bucket, True)
        return HttpResponse(status=204)

class ToggleSubCheckitemView(View):
    def post(self, request, item_id, index):
        item = get_object_or_404(ListItem, id=item_id)
        bucket = item.bucket_list
        can_edit = bucket.owner == request.user or \
                  (request.user.is_authenticated and request.user in bucket.shared_with.all()) or \
                  (bucket.is_public and bucket.allow_public_edit) or \
                  (request.user.is_authenticated and request.user.is_superuser)
        if not can_edit:
            return HttpResponseForbidden()

        sub_list = item.subchecklist_json or []
        if 0 <= index < len(sub_list) and isinstance(sub_list[index], dict):
            sub_list[index]['done'] = not sub_list[index].get('done', False)
            item.subchecklist_json = sub_list
            # If all subitems done, mark main item completed; otherwise leave/set active
            all_done = len(sub_list) > 0 and all(s.get('done', False) for s in sub_list)
            if all_done:
                item.is_completed = True
                item.status = 'done'
            else:
                item.is_completed = False
                item.status = 'active'
            item.save()

        if request.htmx:
            return render_item_list(request, bucket, True)
        return HttpResponse(status=204)

class DeleteItemView(View):
    def delete(self, request, pk):
        return self._do_delete(request, pk)

    def post(self, request, pk):
        return self._do_delete(request, pk)

    def _do_delete(self, request, pk):
        item = get_object_or_404(ListItem, pk=pk)
        bucket = item.bucket_list
        is_owner = bucket.owner == request.user
        is_admin = request.user.is_authenticated and request.user.is_superuser
        is_public_editable = bucket.is_public and bucket.allow_public_edit
        if not (is_owner or is_admin or is_public_editable):
            return HttpResponseForbidden()

        item.delete()
        if request.htmx:
            return render_item_list(request, bucket, True)
        return HttpResponse("")

    def post(self, request, pk):
        return self.delete(request, pk)


class ReorderItemsView(LoginRequiredMixin, View):
    def post(self, request, bucket_id):
        import json
        bucket = get_object_or_404(BucketList, id=bucket_id)
        is_owner = bucket.owner == request.user
        is_admin = request.user.is_authenticated and request.user.is_superuser
        if not (is_owner or is_admin):
            return HttpResponseForbidden()
        try:
            data = json.loads(request.body)
            order = data.get('order', [])  # list of item IDs in new order
            for idx, item_id in enumerate(order):
                ListItem.objects.filter(pk=item_id, bucket_list=bucket).update(order=idx)
            return JsonResponse({'status': 'ok'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

class ShareToggleView(LoginRequiredMixin, View):
    def post(self, request, pk):
        bucket = get_object_or_404(BucketList, id=pk)
        is_owner = bucket.owner == request.user
        is_admin = request.user.is_authenticated and request.user.is_superuser
        if not (is_owner or is_admin):
            return HttpResponseForbidden()
        
        action = request.POST.get('action')
        if action == 'toggle_public':
            bucket.is_public = not bucket.is_public
            # If we disable public access, also disable public edit for safety
            if not bucket.is_public:
                bucket.allow_public_edit = False
        elif action == 'toggle_edit':
            bucket.allow_public_edit = not bucket.allow_public_edit
        elif action == 'toggle_secret_santa':
            bucket.is_secret_santa = not bucket.is_secret_santa
        elif action == 'set_beneficiary':
            beneficiary_id = request.POST.get('beneficiary_id')
            if beneficiary_id:
                bucket.beneficiary_id = beneficiary_id
            else:
                bucket.beneficiary = None
        elif action == 'set_todo_sync_url':
            todo_sync_url = request.POST.get('todo_sync_url', '').strip()
            bucket.todo_sync_url = todo_sync_url if todo_sync_url else None
        elif action == 'add_participant':
            person_id = request.POST.get('person_id')
            new_person_name = request.POST.get('new_person_name')
            if person_id:
                person = get_object_or_404(Person, id=person_id)
                ListParticipant.objects.get_or_create(bucket_list=bucket, person=person)
            elif new_person_name:
                person = Person.objects.create(name=new_person_name.strip())
                ListParticipant.objects.create(bucket_list=bucket, person=person)
        elif action == 'remove_participant':
            participant_id = request.POST.get('participant_id')
            if participant_id:
                participant = get_object_or_404(ListParticipant, id=participant_id, bucket_list=bucket)
                participant.delete()
        elif action == 'toggle_participant_sent':
            participant_id = request.POST.get('participant_id')
            if participant_id:
                participant = get_object_or_404(ListParticipant, id=participant_id, bucket_list=bucket)
                participant.link_sent = not participant.link_sent
                participant.save()
            
        bucket.save()
        people = Person.objects.all()
        return render(request, 'core/partials/share_controls.html', {
            'bucket': bucket,
            'people': people
        })

class CyclePersonRoleView(View):
    def post(self, request, role_id):
        role = get_object_or_404(ItemPersonRole, id=role_id)
        bucket = role.item.bucket_list
        
        current_person_id = request.session.get('person_id')
        is_own_role = current_person_id and role.person_id == current_person_id
        
        can_edit = bucket.owner == request.user or \
                  (request.user.is_authenticated and request.user in bucket.shared_with.all()) or \
                  (bucket.is_public and bucket.allow_public_edit) or \
                  (bucket.is_secret_santa and is_own_role)
                  
        if not can_edit:
            return HttpResponseForbidden()
            
        if bucket.is_secret_santa:
            if role.role == 'reserved':
                role.role = 'fulfilled'
                role.save()
                role.item.is_completed = True
                role.item.save()
            else:
                role.delete()
                other_fulfilled = role.item.person_roles.filter(role='fulfilled').exclude(id=role.id).exists()
                if not other_fulfilled:
                    role.item.is_completed = False
                    role.item.save()
        else:
            effective_roles = {r['key']: r for r in bucket.category.template.get_effective_roles()}
            completing_keys = {k for k, v in effective_roles.items() if v.get('completes')} | {'fulfilled'}
            allowed_keys = set(effective_roles.keys()) | {c[0] for c in ItemPersonRole.STATUS_CHOICES}

            new_role = request.POST.get('role')
            if new_role == 'delete':
                role.delete()
                other_fulfilled = role.item.person_roles.filter(role__in=completing_keys).exists()
                if not other_fulfilled:
                    role.item.is_completed = False
                    role.item.save()
            elif new_role and new_role in allowed_keys:
                role.role = new_role
                role.save()
                if role.role in completing_keys:
                    role.item.is_completed = True
                    role.item.save()
                else:
                    other_fulfilled = role.item.person_roles.filter(role__in=completing_keys).exclude(id=role.id).exists()
                    if not other_fulfilled:
                        role.item.is_completed = False
                        role.item.save()
            else:
                choices = list(effective_roles.keys()) or [c[0] for c in ItemPersonRole.STATUS_CHOICES]
                current_index = choices.index(role.role) if role.role in choices else -1
                next_index = (current_index + 1) % len(choices)
                role.role = choices[next_index]
                role.save()
                if role.role in completing_keys:
                    role.item.is_completed = True
                    role.item.save()
                else:
                    other_fulfilled = role.item.person_roles.filter(role__in=completing_keys).exclude(id=role.id).exists()
                    if not other_fulfilled:
                        role.item.is_completed = False
                        role.item.save()
        
        if request.htmx:
            return render_item_list(request, bucket, True)
        return HttpResponse(status=204)

class ToggleReservationView(View):
    def post(self, request, item_id):
        item = get_object_or_404(ListItem, id=item_id)
        bucket = item.bucket_list
        
        person_id = request.session.get('person_id')
        if not person_id and request.user.is_authenticated:
            try:
                person = request.user.person_profile
                person_id = person.id
            except Person.DoesNotExist:
                pass
                
        if not person_id:
            return HttpResponseForbidden("Kein Teilnehmer-Profil gefunden.")
            
        person = get_object_or_404(Person, id=person_id)
        
        # Toggle the reservation:
        role, created = ItemPersonRole.objects.get_or_create(item=item, person=person)
        if not created:
            if role.role == 'reserved':
                role.role = 'fulfilled'
                role.save()
                item.is_completed = True
                item.save()
            else:
                role.delete()
                item.is_completed = False
                item.save()
        else:
            role.role = 'reserved'
            role.save()
            
        if request.htmx:
            return render_item_list(request, bucket, True)
        return HttpResponse(status=204)

class ThemeSettingsView(LoginRequiredMixin, View):
    def get(self, request):
        settings, _ = UserSetting.objects.get_or_create(user=request.user)
        from core.models import Person
        person, _ = Person.objects.get_or_create(user=request.user, defaults={'name': request.user.username})
        ctx = {'settings': settings, 'person': person}
        if request.user.is_staff:
            try:
                from ops_kit.views import get_updates_context
                ctx.update(get_updates_context())
            except Exception:
                pass
        return render(request, 'core/settings.html', ctx)

    def post(self, request):
        settings, _ = UserSetting.objects.get_or_create(user=request.user)
        settings.primary_color = request.POST.get('primary_color')
        settings.accent_color = request.POST.get('accent_color')
        settings.bg_color = request.POST.get('bg_color')
        settings.text_color = request.POST.get('text_color')
        settings.input_bg_color = request.POST.get('input_bg_color', '#000000')
        settings.input_text_color = request.POST.get('input_text_color', '#ffffff')
        settings.header_bg_color = request.POST.get('header_bg_color', '#543D62')
        settings.header_text_color = request.POST.get('header_text_color', '#ffffff')
        settings.glass_opacity = request.POST.get('glass_opacity')
        settings.timezone = request.POST.get('timezone', 'Europe/Berlin')
        settings.alexa_user_id = request.POST.get('alexa_user_id', '').strip() or None
        
        try:
            settings.calendar_start_hour = int(request.POST.get('calendar_start_hour', 8))
        except (ValueError, TypeError):
            settings.calendar_start_hour = 8
            
        try:
            settings.calendar_end_hour = int(request.POST.get('calendar_end_hour', 22))
        except (ValueError, TypeError):
            settings.calendar_end_hour = 22
            
        settings.calendar_filter_tracker = request.POST.get('calendar_filter_tracker') == 'on'
        settings.calendar_filter_reminder = request.POST.get('calendar_filter_reminder') == 'on'
        settings.calendar_filter_completed = request.POST.get('calendar_filter_completed') == 'on'
        settings.calendar_refresh_interval = request.POST.get('calendar_refresh_interval', 'PT15M')
        
        # Save Gym & Workout settings
        gym_weight = request.POST.get('gym_weight')
        if gym_weight:
            try:
                settings.gym_weight = float(gym_weight)
            except ValueError:
                pass
        else:
            settings.gym_weight = None
            
        settings.gym_fitness_goal = request.POST.get('gym_fitness_goal', '').strip()
        settings.gym_nutrition_plan_url = request.POST.get('gym_nutrition_plan_url', '').strip() or None
        
        try:
            settings.gym_plan_adaptation_weeks = int(request.POST.get('gym_plan_adaptation_weeks', 4))
        except (ValueError, TypeError):
            settings.gym_plan_adaptation_weeks = 4
            
        settings.gym_plan_adaptation_message = request.POST.get('gym_plan_adaptation_message', '').strip()
        
        # Save measurements
        measurements = {
            'brust': request.POST.get('measure_brust', '').strip(),
            'ruecken': request.POST.get('measure_ruecken', '').strip(),
            'arm_l': request.POST.get('measure_arm_l', '').strip(),
            'arm_r': request.POST.get('measure_arm_r', '').strip(),
            'bauch': request.POST.get('measure_bauch', '').strip(),
            'bein_l': request.POST.get('measure_bein_l', '').strip(),
            'bein_r': request.POST.get('measure_bein_r', '').strip(),
        }
        settings.gym_body_measurements_json = measurements
        
        settings.save()
        
        # Save birth date
        birth_date = request.POST.get('birth_date')
        from core.models import Person
        person, _ = Person.objects.get_or_create(user=request.user, defaults={'name': request.user.username})
        if birth_date:
            person.birth_date = birth_date
        else:
            person.birth_date = None
        person.save()
        
        return redirect('core:dashboard')

from django.http import JsonResponse
class WorkoutLogSessionView(View):
    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'status': 'error', 'message': 'Nicht autorisiert'}, status=403)
        try:
            import json
            from core.models import WorkoutSessionLog, WorkoutActivityLog, BucketList
            data = json.loads(request.body)
            bucket_id = data.get('bucket_id')
            bucket = BucketList.objects.get(id=bucket_id)
            
            # Check permissions
            if bucket.owner != request.user and request.user not in bucket.shared_with.all():
                return JsonResponse({'status': 'error', 'message': 'Zugriff verweigert'}, status=403)
            
            session = WorkoutSessionLog.objects.create(
                user=request.user,
                bucket_list=bucket,
                duration_seconds=data.get('duration_seconds', 0),
                rating=data.get('rating', 5),
                notes=data.get('notes', '')
            )
            
            activities = data.get('activities', [])
            for act in activities:
                WorkoutActivityLog.objects.create(
                    session=session,
                    title=act.get('title'),
                    activity_type=act.get('activity_type', 'strength'),
                    logged_data_json=act.get('logged_data')
                )
                
            # Reset the list items for next training session
            bucket.items.all().update(is_completed=False, status='active', completed_at=None)
            
            return JsonResponse({'status': 'success', 'session_id': session.id})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

class DeleteWorkoutSessionView(LoginRequiredMixin, View):
    def post(self, request, session_id):
        from core.models import WorkoutSessionLog
        session = get_object_or_404(WorkoutSessionLog, id=session_id)
        if session.bucket_list.owner != request.user:
            return HttpResponseForbidden()
        session.delete()
        return JsonResponse({'status': 'ok'})


class SaveNutritionGoalView(LoginRequiredMixin, View):
    def post(self, request, bucket_id):
        from core.models import BucketList, NutritionGoal
        import json
        bucket = get_object_or_404(BucketList, id=bucket_id)
        if bucket.owner != request.user and request.user not in bucket.shared_with.all():
            return HttpResponseForbidden()
        
        goal, _ = NutritionGoal.objects.get_or_create(bucket_list=bucket)
        data = json.loads(request.body)
        
        if 'start_weight' in data and data['start_weight']:
            goal.start_weight = float(data['start_weight'])
        if 'target_weight' in data and data['target_weight']:
            goal.target_weight = float(data['target_weight'])
        if 'target_calories' in data and data['target_calories']:
            goal.target_calories = int(data['target_calories'])
        if 'gender' in data:
            goal.gender = data['gender']
        if 'age' in data and data['age']:
            goal.age = int(data['age'])
        if 'height_cm' in data and data['height_cm']:
            goal.height_cm = int(data['height_cm'])
        if 'activity_level' in data and data['activity_level']:
            goal.activity_level = float(data['activity_level'])
        if 'goal_type' in data:
            goal.goal_type = data['goal_type']
        if 'target_protein_g' in data and data['target_protein_g']:
            goal.target_protein_g = int(data['target_protein_g'])
        if 'target_carbs_g' in data and data['target_carbs_g']:
            goal.target_carbs_g = int(data['target_carbs_g'])
        if 'target_fat_g' in data and data['target_fat_g']:
            goal.target_fat_g = int(data['target_fat_g'])
        if 'target_water_ml' in data and data['target_water_ml']:
            goal.target_water_ml = int(data['target_water_ml'])
            
        goal.save()
        rec = goal.calculate_recommended_calories()
        return JsonResponse({
            'status': 'ok',
            'recommended_calories': rec,
            'target_calories': goal.target_calories
        })


class LogWeightView(LoginRequiredMixin, View):
    def post(self, request, bucket_id):
        from core.models import BucketList, WeightLog
        from datetime import datetime
        import json
        bucket = get_object_or_404(BucketList, id=bucket_id)
        if bucket.owner != request.user and request.user not in bucket.shared_with.all():
            return HttpResponseForbidden()

        data = json.loads(request.body)
        date_str = data.get('date')
        log_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else timezone.now().date()
        weight_val = float(data.get('weight'))
        note = data.get('note', '')

        # An einem Tag wird der bestehende Eintrag aktualisiert oder neu angelegt
        log, created = WeightLog.objects.update_or_create(
            bucket_list=bucket,
            date=log_date,
            defaults={
                'user': request.user,
                'weight': weight_val,
                'note': note,
            }
        )
        return JsonResponse({
            'status': 'ok',
            'id': log.id,
            'date': log.date.strftime('%d.%m.%Y'),
            'isoDate': log.date.strftime('%Y-%m-%d'),
            'weight': float(log.weight),
            'note': log.note
        })


class DeleteWeightLogView(LoginRequiredMixin, View):
    def post(self, request, log_id):
        from core.models import WeightLog
        log = get_object_or_404(WeightLog, id=log_id)
        if log.bucket_list.owner != request.user and request.user not in log.bucket_list.shared_with.all():
            return HttpResponseForbidden()
        log.delete()
        return JsonResponse({'status': 'ok'})


class LogMealView(LoginRequiredMixin, View):
    def post(self, request, bucket_id):
        from core.models import BucketList, NutritionMealLog
        from datetime import datetime
        import json
        bucket = get_object_or_404(BucketList, id=bucket_id)
        if bucket.owner != request.user and request.user not in bucket.shared_with.all():
            return HttpResponseForbidden()

        data = json.loads(request.body)
        date_str = data.get('date')
        log_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else timezone.now().date()
        
        meal = NutritionMealLog.objects.create(
            bucket_list=bucket,
            user=request.user,
            date=log_date,
            meal_type=data.get('meal_type', 'lunch'),
            title=data.get('title', 'Mahlzeit'),
            calories=int(data.get('calories') or 0),
            protein_g=float(data.get('protein_g') or 0.0),
            carbs_g=float(data.get('carbs_g') or 0.0),
            fat_g=float(data.get('fat_g') or 0.0),
            amount=data.get('amount', '')
        )
        return JsonResponse({
            'status': 'ok',
            'id': meal.id,
            'date': meal.date.strftime('%Y-%m-%d'),
            'meal_type': meal.meal_type,
            'meal_type_display': meal.get_meal_type_display(),
            'title': meal.title,
            'calories': meal.calories,
            'protein_g': meal.protein_g,
            'carbs_g': meal.carbs_g,
            'fat_g': meal.fat_g,
            'amount': meal.amount
        })


class DeleteMealView(LoginRequiredMixin, View):
    def post(self, request, meal_id):
        from core.models import NutritionMealLog
        meal = get_object_or_404(NutritionMealLog, id=meal_id)
        if meal.bucket_list.owner != request.user and request.user not in meal.bucket_list.shared_with.all():
            return HttpResponseForbidden()
        meal.delete()
        return JsonResponse({'status': 'ok'})

class ToggleTrackerLogView(View):
    def post(self, request, item_id):
        item = get_object_or_404(ListItem, id=item_id)
        bucket = item.bucket_list
        can_edit = bucket.owner == request.user or \
                  (request.user.is_authenticated and request.user in bucket.shared_with.all()) or \
                  (bucket.is_public and bucket.allow_public_edit) or \
                  (request.session.get('person_id') is not None) or \
                  (request.user.is_authenticated and request.user.is_superuser)
        if not can_edit:
            return HttpResponseForbidden()

        scheduled_time = request.POST.get('scheduled_time')
        if not scheduled_time:
            return HttpResponse(status=400)

        # Get today's date in local timezone
        from django.utils import timezone
        today = timezone.localdate()

        # Check if already completed
        from core.models import ItemTrackerLog
        log = ItemTrackerLog.objects.filter(item=item, date=today, scheduled_time=scheduled_time).first()

        if log:
            # Toggle off: delete log, restore inventory
            log.delete()
            if item.tracker_stock_total is not None:
                item.tracker_stock_total += int(item.tracker_dosage_per_take)
                item.save()
        else:
            # Toggle on: create log, subtract from inventory
            ItemTrackerLog.objects.create(item=item, scheduled_time=scheduled_time)
            if item.tracker_stock_total is not None:
                item.tracker_stock_total = max(0, item.tracker_stock_total - int(item.tracker_dosage_per_take))
                item.save()

        if request.htmx:
            return render_item_list(request, bucket, True)
        return HttpResponse(status=204)

class AdjustAmountView(View):
    def post(self, request, item_id):
        item = get_object_or_404(ListItem, id=item_id)
        bucket = item.bucket_list
        can_edit = bucket.owner == request.user or \
                  (request.user.is_authenticated and request.user in bucket.shared_with.all()) or \
                  (bucket.is_public and bucket.allow_public_edit) or \
                  (request.user.is_authenticated and request.user.is_superuser)
        if not can_edit:
            return HttpResponseForbidden()

        action = request.POST.get('action')
        current_amount = item.amount_value or 0

        if action == 'increment':
            item.amount_value = current_amount + 1
            if request.user.is_authenticated:
                item.updated_by = request.user
                item.guest_updated_by = None
            else:
                item.updated_by = None
                item.guest_updated_by = request.session.get('guest_name')
            item.save()
        elif action == 'decrement':
            if current_amount > 0:
                item.amount_value = max(0, current_amount - 1)
                if request.user.is_authenticated:
                    item.updated_by = request.user
                    item.guest_updated_by = None
                else:
                    item.updated_by = None
                    item.guest_updated_by = request.session.get('guest_name')
                item.save()

        if request.htmx:
            return render_item_list(request, bucket, True)
        return HttpResponse(status=204)


class AdjustRatingView(View):
    def post(self, request, item_id):
        item = get_object_or_404(ListItem, id=item_id)
        bucket = item.bucket_list
        can_edit = bucket.owner == request.user or \
                   (request.user.is_authenticated and request.user in bucket.shared_with.all()) or \
                   (bucket.is_public and bucket.allow_public_edit) or \
                   (request.user.is_authenticated and request.user.is_superuser)
        if not can_edit:
            return HttpResponseForbidden()

        rating_val = request.POST.get('rating')
        if rating_val is not None:
            try:
                rating_val = int(rating_val)
                if 0 <= rating_val <= 5:
                    if item.rating == rating_val:
                        item.rating = None
                    else:
                        item.rating = rating_val
                    if request.user.is_authenticated:
                        item.updated_by = request.user
                        item.guest_updated_by = None
                    else:
                        item.updated_by = None
                        item.guest_updated_by = request.session.get('guest_name')
                    item.save()
            except ValueError:
                pass

        if request.htmx:
            return render_item_list(request, bucket, True)
        return HttpResponse(status=204)


from django.urls import reverse
import json

class CalendarView(LoginRequiredMixin, TemplateView):
    template_name = 'core/calendar.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get or lazily create Person profile for secure calendar feed token
        from core.models import Person
        person = Person.objects.filter(user=self.request.user).first()
        if not person and self.request.user.is_authenticated:
            person = Person.objects.create(
                user=self.request.user,
                name=self.request.user.get_full_name() or self.request.user.username,
                email=self.request.user.email
            )
        context['person'] = person

        # Fetch all lists where user is owner or shared_with
        if self.request.user.is_superuser:
            lists = BucketList.objects.all()
        else:
            lists = BucketList.objects.filter(
                models.Q(owner=self.request.user) | models.Q(shared_with=self.request.user)
            ).distinct()

        # Fetch all items with dates or tracker times from these lists
        items = ListItem.objects.filter(
            bucket_list__in=lists
        ).filter(
            models.Q(start_date__isnull=False) |
            models.Q(end_date__isnull=False) |
            models.Q(reminder_at__isnull=False) |
            (models.Q(tracker_times__isnull=False) & ~models.Q(tracker_times=''))
        ).select_related('bucket_list', 'bucket_list__category')

        events = []
        for item in items:
            list_url = reverse('core:list_detail', args=[item.bucket_list.id])
            cat_icon = item.bucket_list.category.icon if item.bucket_list.category else "📌"
            
            # Use distinct ids so FullCalendar doesn't complain about duplicates
            # 1. Start date & End date range
            if item.start_date and item.end_date:
                events.append({
                    'id': f"range-{item.id}",
                    'title': f"{cat_icon} {item.title}",
                    'start': item.start_date.isoformat(),
                    'end': item.end_date.isoformat(),
                    'allDay': False,
                    'url': list_url,
                    'color': 'var(--primary)',
                    'extendedProps': {
                        'listName': item.bucket_list.title,
                        'notes': item.notes,
                        'completed': item.is_completed
                    }
                })
            else:
                # 2. Only Start date
                if item.start_date:
                    events.append({
                        'id': f"start-{item.id}",
                        'title': f"{cat_icon} {item.title} (Start)",
                        'start': item.start_date.isoformat(),
                        'allDay': False,
                        'url': list_url,
                        'color': 'rgba(255,255,255,0.15)',
                        'extendedProps': {
                            'listName': item.bucket_list.title,
                            'notes': item.notes,
                            'completed': item.is_completed
                        }
                    })
                # 3. Only End date (due)
                if item.end_date:
                    events.append({
                        'id': f"end-{item.id}",
                        'title': f"🏁 {cat_icon} {item.title}",
                        'start': item.end_date.isoformat(),
                        'allDay': False,
                        'url': list_url,
                        'color': 'var(--accent)' if not item.is_completed else 'var(--primary)',
                        'extendedProps': {
                            'listName': item.bucket_list.title,
                            'notes': item.notes,
                            'completed': item.is_completed
                        }
                    })

            # 4. Reminder date and time
            if item.reminder_at:
                events.append({
                    'id': f"rem-{item.id}",
                    'title': f"⏰ {item.title} (Erinnerung)",
                    'start': item.reminder_at.isoformat(),
                    'allDay': False,
                    'url': list_url,
                    'color': '#ffab00',
                    'extendedProps': {
                        'listName': item.bucket_list.title,
                        'notes': item.notes,
                        'completed': item.is_completed
                    }
                })

            # 5. Recurring Daily Tracker Times
            if item.tracker_times:
                times_list = [t.strip() for t in item.tracker_times.split(',') if t.strip()]
                for t in times_list:
                    # Validate HH:MM format
                    if len(t) == 5 and t[2] == ':':
                        start_time = f"{t}:00"
                        try:
                            hour, minute = map(int, t.split(':'))
                            end_hour = hour
                            end_minute = minute + 30
                            if end_minute >= 60:
                                end_hour = (end_hour + 1) % 24
                                end_minute = end_minute - 60
                            end_time = f"{end_hour:02d}:{end_minute:02d}:00"
                        except Exception:
                            end_time = f"{t}:00"
                            
                        events.append({
                            'id': f"tracker-{item.id}-{t}",
                            'title': f"{cat_icon} {item.title}",
                            'startTime': start_time,
                            'endTime': end_time,
                            'daysOfWeek': [0, 1, 2, 3, 4, 5, 6], # Every day!
                            'url': list_url,
                            'color': 'rgba(0, 230, 118, 0.12)', # Soft neon-green glass
                            'borderColor': '#00e676',
                            'textColor': '#00e676',
                            'extendedProps': {
                                'listName': item.bucket_list.title,
                                'notes': f"Tägliche Routine um {t} Uhr.",
                                'completed': False
                            }
                        })

        context['events_json'] = json.dumps(events)
        return context


def sync_microsoft_todo(bucket_list):
    if not bucket_list.todo_sync_url:
        return
        
    import urllib.request
    import re
    from core.models import ListItem
    
    try:
        # Fetch the ICS content with a timeout of 3 seconds and a custom User-Agent
        req = urllib.request.Request(
            bucket_list.todo_sync_url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Buckezz/1.0'}
        )
        with urllib.request.urlopen(req, timeout=3) as response:
            content = response.read().decode('utf-8')
            
        # Parse VTODO blocks in the ICS feed
        vtodo_blocks = re.findall(r'BEGIN:VTODO(.*?)END:VTODO', content, re.DOTALL)
        
        for block in vtodo_blocks:
            # Extract SUMMARY (the item text)
            summary_match = re.search(r'SUMMARY:(.*?)[\r\n]', block)
            status_match = re.search(r'STATUS:(.*?)[\r\n]', block)
            
            if summary_match:
                title = summary_match.group(1).strip()
                # Clean up standard ICS escapes (like \,)
                title = title.replace(r'\,', ',').replace(r'\;', ';')
                
                # Check status: uncompleted is NEEDS-ACTION
                status = status_match.group(1).strip() if status_match else 'NEEDS-ACTION'
                
                if status == 'NEEDS-ACTION':
                    # Only add if not already in the active list
                    if not ListItem.objects.filter(bucket_list=bucket_list, title=title, is_completed=False).exists():
                        ListItem.objects.create(
                            bucket_list=bucket_list,
                            title=title,
                            is_completed=False
                        )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Microsoft To-Do sync failed for list {bucket_list.id}: {e}")

def custom_404_view(request, exception=None):
    from core.models import UserSetting
    # Try to load user settings for the theme
    user_settings = None
    if request.user.is_authenticated:
        user_settings, _ = UserSetting.objects.get_or_create(user=request.user)
    elif request.session.get('person_id'):
        from core.models import Person
        try:
            person = Person.objects.get(id=request.session.get('person_id'))
            if person.user:
                user_settings, _ = UserSetting.objects.get_or_create(user=person.user)
        except Person.DoesNotExist:
            pass

    return render(request, '404.html', {'user_settings': user_settings}, status=404)


import os
import shutil
import re
from django.views import View
from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.conf import settings
from core.models import Tenant, UserSetting, Person
from core.router import set_active_tenant, register_tenant_db

class RegisterTenantView(View):
    def get(self, request, *args, **kwargs):
        # Wenn bereits auf einer Subdomain, umleiten zur Hauptdomain
        if request.tenant is not None:
            host = request.get_host().split(':')[0]
            parts = host.split('.')
            if len(parts) > 3:
                main_host = '.'.join(parts[1:])
                return redirect(f"{request.scheme}://{main_host}/register/")
            return redirect('/')
            
        return render(request, 'register_tenant.html', {
            'registration_code_required': bool(settings.REGISTRATION_CODE)
        })

    def post(self, request, *args, **kwargs):
        if request.tenant is not None:
            return redirect('/')

        instance_name = request.POST.get('instance_name', '').strip()
        instance_slug = request.POST.get('instance_slug', '').strip().lower()
        admin_username = request.POST.get('admin_username', '').strip()
        admin_email = request.POST.get('admin_email', '').strip()
        admin_password = request.POST.get('admin_password', '')
        registration_code = request.POST.get('registration_code', '').strip()

        errors = {}

        # 1. Validierungen
        if settings.REGISTRATION_CODE and registration_code != settings.REGISTRATION_CODE:
            errors['registration_code'] = 'Der Registrierungsschlüssel ist ungültig.'

        if not instance_name:
            errors['instance_name'] = 'Bitte gib einen Namen für deine Instanz ein.'
        
        if not instance_slug:
            errors['instance_slug'] = 'Bitte gib eine gewünschte Subdomain ein.'
        elif not re.match(r'^[a-z0-9-]+$', instance_slug):
            errors['instance_slug'] = 'Die Subdomain darf nur Kleinbuchstaben, Zahlen und Bindestriche enthalten.'
        elif len(instance_slug) < 3:
            errors['instance_slug'] = 'Die Subdomain muss mindestens 3 Zeichen lang sein.'
        elif instance_slug in ['www', 'admin', 'api', 'register', 'static', 'media', 'localhost', 'default', 'test', 'sys']:
            errors['instance_slug'] = 'Diese Subdomain ist reserviert. Bitte wähle eine andere.'
        elif Tenant.objects.using('default').filter(slug=instance_slug).exists():
            errors['instance_slug'] = 'Diese Subdomain ist bereits vergeben.'

        if not admin_username:
            errors['admin_username'] = 'Bitte gib einen Administrator-Nutzernamen ein.'
        elif len(admin_username) < 3:
            errors['admin_username'] = 'Der Nutzername muss mindestens 3 Zeichen lang sein.'

        if not admin_email:
            errors['admin_email'] = 'Bitte gib eine gültige E-Mail-Adresse ein.'

        if not admin_password:
            errors['admin_password'] = 'Bitte gib ein Passwort ein.'
        elif len(admin_password) < 8:
            errors['admin_password'] = 'Das Passwort muss mindestens 8 Zeichen lang sein.'

        if errors:
            return render(request, 'register_tenant.html', {
                'errors': errors,
                'instance_name': instance_name,
                'instance_slug': instance_slug,
                'admin_username': admin_username,
                'admin_email': admin_email,
                'registration_code_required': bool(settings.REGISTRATION_CODE),
            })

        # 2. Registrierung ausführen
        try:
            default_db_path = settings.DATABASES['default']['NAME']
            db_dir = os.path.dirname(default_db_path)
            template_db_path = os.path.join(db_dir, 'db_template.sqlite3')
            tenant_db_path = os.path.join(db_dir, f'db_tenant_{instance_slug}.sqlite3')

            if not os.path.exists(template_db_path):
                errors['global'] = 'Systemfehler: Die Datenbankvorlage existiert nicht. Bitte wende dich an den Systemadministrator.'
                return render(request, 'register_tenant.html', {
                    'errors': errors,
                    'instance_name': instance_name,
                    'instance_slug': instance_slug,
                    'admin_username': admin_username,
                    'admin_email': admin_email,
                    'registration_code_required': bool(settings.REGISTRATION_CODE),
                })

            # Klonen der Template-DB
            shutil.copyfile(template_db_path, tenant_db_path)
            # Berechtigungen auf 777 setzen, damit der Webserver schreiben darf
            os.chmod(tenant_db_path, 0o777)

            # Tenant-Registry Eintrag in default-DB anlegen
            tenant = Tenant.objects.using('default').create(
                slug=instance_slug,
                name=instance_name,
                owner_email=admin_email,
                is_active=True
            )

            # Mandanten-Datenbank registrieren und Alias holen
            db_alias = register_tenant_db(instance_slug)

            # Temporär auf die neue Mandanten-Datenbank umschalten
            set_active_tenant(instance_slug)
            try:
                # Admin-Superuser explizit in der Mandanten-Datenbank erstellen
                user = User.objects.db_manager(db_alias).create_superuser(
                    username=admin_username,
                    email=admin_email,
                    password=admin_password
                )
                
                # UserSetting für den Admin explizit in der Mandanten-Datenbank erstellen/holen
                UserSetting.objects.using(db_alias).get_or_create(user=user)
                
                # Person-Eintrag für den Admin explizit in der Mandanten-Datenbank erstellen
                Person.objects.using(db_alias).create(
                    name=admin_username,
                    email=admin_email,
                    user=user
                )
            finally:
                # Unbedingt wieder auf Standard zurücksetzen
                set_active_tenant(None)

            # Erfolgs-Subdomain-URL zusammensetzen
            host = request.get_host()
            port_suffix = ""
            if ":" in host:
                port_suffix = ":" + host.split(':')[1]
                host_only = host.split(':')[0]
            else:
                host_only = host

            # Falls wir uns bereits auf einer Mandanten-Subdomain befinden (z.B. simon.zaisers.myds.me),
            # müssen wir den aktuellen Mandanten-Präfix abschneiden, um eine verschachtelte Subdomain zu verhindern.
            if getattr(request, 'tenant', None) and request.tenant.slug:
                prefix = f"{request.tenant.slug}."
                if host_only.lower().startswith(prefix.lower()):
                    host_only = host_only[len(prefix):]

            # Falls die Hauptdomain buckezz.zaisers.myds.me ist, schneiden wir "buckezz." ab,
            # damit die Mandanten direkt unter *.zaisers.myds.me erreichbar sind (wegen SSL-Zertifikat).
            if host_only.lower().endswith('.zaisers.myds.me') and host_only.lower().startswith('buckezz.'):
                host_only = host_only[len('buckezz.'):]

            parts = host_only.split('.')
            if parts[-1] == 'localhost':
                tenant_domain = f"{instance_slug}.localhost{port_suffix}"
            else:
                tenant_domain = f"{instance_slug}.{host_only}{port_suffix}"

            tenant_url = f"{request.scheme}://{tenant_domain}/login/"

            return render(request, 'register_tenant_success.html', {
                'instance_name': instance_name,
                'tenant_url': tenant_url,
            })

        except Exception as e:
            # Im Fehlerfall aufräumen
            if os.path.exists(tenant_db_path):
                try:
                    os.remove(tenant_db_path)
                except:
                    pass
            Tenant.objects.using('default').filter(slug=instance_slug).delete()
            
            errors['global'] = f'Registrierungsfehler: {str(e)}'
            return render(request, 'register_tenant.html', {
                'errors': errors,
                'instance_name': instance_name,
                'instance_slug': instance_slug,
                'admin_username': admin_username,
                'admin_email': admin_email,
            })


# =============================================================================
# Grafisches Vorlagen-Studio (Staff / Admin)
# =============================================================================
from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib import messages
from django.utils.text import slugify
from .models import ListTemplate


TEMPLATE_STUDIO_FIELDS = [
    {"key": "use_amount", "label": "Menge & Einheit", "icon": "bi-123", "desc": "Stückzahl, Gewicht oder Volumen mit +/- Buttons"},
    {"key": "use_price", "label": "Preis (€)", "icon": "bi-currency-euro", "desc": "Preiserfassung inkl. automatischer Summenleiste"},
    {"key": "use_brand", "label": "Marke / Hersteller", "icon": "bi-tag", "desc": "Marken-, Arzt- oder Herstellername"},
    {"key": "use_shop", "label": "Geschäft / Shop", "icon": "bi-shop", "desc": "Einkaufsort oder Bezugsquelle"},
    {"key": "use_location", "label": "Ort / Adresse", "icon": "bi-geo-alt", "desc": "Veranstaltungsort, Adresse oder Praxis"},
    {"key": "use_url", "label": "Produkt-URL", "icon": "bi-link-45deg", "desc": "Direktlink zum Produkt oder Angebot"},
    {"key": "use_start_date", "label": "Startdatum", "icon": "bi-calendar-event", "desc": "Startzeitpunkt (auch im Kalender sichtbar)"},
    {"key": "use_end_date", "label": "Enddatum", "icon": "bi-flag", "desc": "Endzeitpunkt oder Deadline"},
    {"key": "use_reminder", "label": "E-Mail-Erinnerung", "icon": "bi-alarm", "desc": "Zeitgesteuerte Erinnerung"},
    {"key": "use_persons", "label": "Personen & Rollen", "icon": "bi-people", "desc": "Zuständigkeiten, Gäste oder Wichtel"},
    {"key": "use_rating", "label": "Sterne-Bewertung", "icon": "bi-star", "desc": "1–5 Sterne Priorität oder Bewertung"},
    {"key": "use_tracker", "label": "Routine-Tracker", "icon": "bi-arrow-repeat", "desc": "Uhrzeiten-Chips & Vorrats-Bestand"},
    {"key": "use_milestone", "label": "Meilensteine", "icon": "bi-trophy", "desc": "Lebensabschnitte (Vor 30, Vor 40, ...)"},
    {"key": "use_image", "label": "Foto / Beleg", "icon": "bi-camera", "desc": "Kamera- oder Mehrfach-Bild-Upload pro Eintrag"},
    {"key": "use_subchecklist", "label": "Teil-Checkliste", "icon": "bi-list-check", "desc": "Unterpunkte zum separaten Abhaken"},
    {"key": "use_subchecklist_photos", "label": "Teil-Checkliste mit Foto", "icon": "bi-images", "desc": "Unterpunkte mit eigenem Foto pro Eintrag"},
]


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_staff


class TemplateStudioListView(StaffRequiredMixin, ListView):
    model = ListCategory
    template_name = 'core/template_studio_list.html'
    context_object_name = 'categories'

    def get_queryset(self):
        return ListCategory.objects.select_related('template').annotate(
            lists_count=models.Count('lists')
        ).order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cats = list(context['categories'])
        field_keys = [f['key'] for f in TEMPLATE_STUDIO_FIELDS]
        for cat in cats:
            tpl = getattr(cat, 'template', None)
            cat.active_field_labels = [
                f['label'] for f in TEMPLATE_STUDIO_FIELDS if tpl and getattr(tpl, f['key'], False)
            ]
        context['total_templates'] = len(cats)
        context['total_lists'] = sum(c.lists_count for c in cats)
        context['logic_types_count'] = len(ListTemplate.LOGIC_CHOICES)
        return context


class TemplateStudioBuilderView(StaffRequiredMixin, View):
    template_name = 'core/template_studio_builder.html'

    STATUS_PRESETS = [
        {"key": "active", "label": "Offen", "completes": False},
        {"key": "waiting", "label": "Wartend / In Arbeit", "completes": False},
        {"key": "overdue", "label": "Überfällig", "completes": False},
        {"key": "done", "label": "Erledigt", "completes": True},
        {"key": "reserved", "label": "Reserviert", "completes": False},
        {"key": "for_sale", "label": "Zum Verkauf / Inseriert", "completes": False},
        {"key": "sold", "label": "Verkauft", "completes": True},
        {"key": "fulfilled", "label": "Wunsch erfüllt", "completes": True},
    ]

    ROLE_PRESETS = [
        {"key": "borrowed_from", "label": "Geliehen von", "completes": False},
        {"key": "lent_to", "label": "Verliehen an", "completes": False},
        {"key": "assigned", "label": "Zuständig", "completes": False},
        {"key": "invited", "label": "Eingeladen", "completes": False},
        {"key": "attending", "label": "Zugesagt", "completes": False},
        {"key": "declined", "label": "Abgesagt", "completes": False},
        {"key": "maybe", "label": "Vielleicht", "completes": False},
        {"key": "reserved", "label": "Reserviert", "completes": False},
        {"key": "for_sale", "label": "Zum Verkauf / Inseriert", "completes": False},
        {"key": "sold", "label": "Verkauft", "completes": True},
        {"key": "fulfilled", "label": "Wunsch erfüllt", "completes": True},
    ]

    def get_status_presets(self):
        try:
            from domain_kit.models import Status as DomainStatus
            presets = []
            for st in DomainStatus.objects.all().order_by('position', 'name'):
                from django.utils.text import slugify
                key = slugify(st.name).replace('-', '_')[:20]
                presets.append({
                    "key": key,
                    "label": st.name,
                    "completes": bool(st.is_final),
                    "color_state": st.color_state,
                    "icon": st.icon,
                })
            if presets:
                return presets
        except Exception:
            pass
        return self.STATUS_PRESETS

    def get_role_presets(self):
        try:
            from domain_kit.models import Role as DomainRole
            presets = []
            for r in DomainRole.objects.all().order_by('position', 'name'):
                from django.utils.text import slugify
                key = slugify(r.name).replace('-', '_')[:20]
                presets.append({
                    "key": key,
                    "label": r.name,
                    "completes": False,
                    "color_state": r.color_state,
                })
            if presets:
                return presets
        except Exception:
            pass
        return self.ROLE_PRESETS

    def _build_context(self, category=None):
        tpl = getattr(category, 'template', None) if category else None
        active_keys = [
            f['key'] for f in TEMPLATE_STUDIO_FIELDS if tpl and getattr(tpl, f['key'], False)
        ]
        allowed_statuses = tpl.get_effective_statuses() if tpl else [
            {"key": "active", "label": "Offen", "completes": False},
            {"key": "done", "label": "Erledigt", "completes": True},
        ]
        allowed_roles = tpl.allowed_roles_json if (tpl and isinstance(tpl.allowed_roles_json, list)) else []
        logic_rules = tpl.logic_rules_json if (tpl and isinstance(tpl.logic_rules_json, dict)) else {}
        ui_style = tpl.get_ui_style() if tpl else {'layout_mode': 'row', 'card_width': '1/2', 'density': 'normal', 'show_creator': True}
        custom_fields = tpl.custom_fields_json if (tpl and isinstance(tpl.custom_fields_json, list)) else []
        summary_rule = tpl.summary_rule_json if (tpl and isinstance(tpl.summary_rule_json, dict)) else {}
        recurrence = tpl.recurrence_json if (tpl and isinstance(tpl.recurrence_json, dict)) else {}
        return {
            'category': category,
            'tpl': tpl,
            'field_defs': TEMPLATE_STUDIO_FIELDS,
            'active_keys': active_keys,
            'status_presets': self.get_status_presets(),
            'role_presets': self.get_role_presets(),
            'group_by_choices': ListTemplate.GROUP_BY_CHOICES,
            'allowed_statuses_json': json.dumps(allowed_statuses),
            'allowed_roles_json': json.dumps(allowed_roles),
            'logic_rules_json': json.dumps(logic_rules),
            'ui_style_json': json.dumps(ui_style),
            'custom_fields_json': json.dumps(custom_fields),
            'summary_rule_json': json.dumps(summary_rule),
            'recurrence_json': json.dumps(recurrence),
            'logic_choices': ListTemplate.LOGIC_CHOICES,
            'icon_presets': [
                '📋', '🛒', '✅', '🎁', '🎯', '🎉', '💊', '🐾', '🪴', '🏋️',
                '🥗', '✈️', '📚', '🎬', '🍷', '🚗', '🏠', '🔧', '💡', '📦',
                '🎵', '📷', '💰', '🗓️', '👶', '🎮', '🚴', '🧹', '🛍️', '❤️',
            ],
            'bi_icon_presets': [
                'bi-list-check', 'bi-cart3', 'bi-check2-square', 'bi-gift', 'bi-bullseye',
                'bi-balloon', 'bi-capsule', 'bi-heart-pulse', 'bi-flower1', 'bi-lightning-charge',
                'bi-cup-hot', 'bi-airplane', 'bi-book', 'bi-film', 'bi-cup-straw',
                'bi-car-front', 'bi-house-door', 'bi-tools', 'bi-lightbulb', 'bi-box-seam',
                'bi-music-note-beamed', 'bi-camera', 'bi-wallet2', 'bi-calendar-check', 'bi-people',
                'bi-controller', 'bi-bicycle', 'bi-stars', 'bi-bag', 'bi-key',
            ],
        }

    def get(self, request, pk=None):
        category = get_object_or_404(ListCategory.objects.select_related('template'), pk=pk) if pk else None
        return render(request, self.template_name, self._build_context(category))

    def post(self, request, pk=None):
        category = get_object_or_404(ListCategory.objects.select_related('template'), pk=pk) if pk else None
        name = (request.POST.get('name') or '').strip()
        icon = (request.POST.get('icon') or '📋').strip() or '📋'
        logic_type = request.POST.get('logic_type', 'generic')

        if not name:
            messages.error(request, 'Bitte gib einen Vorlagen-Namen ein.')
            return render(request, self.template_name, self._build_context(category))

        valid_logics = {c[0] for c in ListTemplate.LOGIC_CHOICES}
        if logic_type not in valid_logics:
            logic_type = 'generic'

        if category is None:
            base_slug = slugify(name) or 'vorlage'
            slug = base_slug
            counter = 2
            while ListCategory.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            category = ListCategory.objects.create(name=name, slug=slug, icon=icon)
        else:
            category.name = name
            category.icon = icon
            category.save()

        tpl, _ = ListTemplate.objects.get_or_create(category=category)
        tpl.logic_type = logic_type

        for f in TEMPLATE_STUDIO_FIELDS:
            setattr(tpl, f['key'], request.POST.get(f['key']) == 'on')

        for bool_field in ('use_is_public', 'use_allow_public_edit', 'use_beneficiary', 'use_secret_santa', 'new_items_at_bottom'):
            setattr(tpl, bool_field, request.POST.get(bool_field) == 'on')

        tpl.use_status = True
        tpl.help_purpose = request.POST.get('help_purpose', '').strip() or None
        tpl.help_fields = request.POST.get('help_fields', '').strip() or None
        tpl.help_example = request.POST.get('help_example', '').strip() or None

        # Save custom allowed statuses
        s_keys = request.POST.getlist('status_key')
        s_labels = request.POST.getlist('status_label')
        s_completes = request.POST.getlist('status_completes')
        custom_statuses = []
        for idx, skey in enumerate(s_keys):
            key_clean = slugify(skey).replace('-', '_')[:20] or f"status_{idx}"
            lbl = s_labels[idx].strip() if idx < len(s_labels) else key_clean
            comp = (s_completes[idx] == '1') if idx < len(s_completes) else False
            if lbl:
                custom_statuses.append({'key': key_clean, 'label': lbl, 'completes': comp})
        tpl.allowed_statuses_json = custom_statuses

        # Save custom allowed person roles (supports both presets and custom roles)
        r_keys = request.POST.getlist('role_key')
        r_labels = request.POST.getlist('role_label')
        r_completes = request.POST.getlist('role_completes')
        custom_roles = []
        for idx, rkey in enumerate(r_keys):
            key_clean = slugify(rkey).replace('-', '_')[:20]
            lbl = r_labels[idx].strip() if idx < len(r_labels) else key_clean
            if not key_clean and lbl:
                key_clean = slugify(lbl).replace('-', '_')[:20]
            if not key_clean:
                key_clean = f"role_{idx}"
            comp = (r_completes[idx] == '1') if idx < len(r_completes) else (key_clean == 'fulfilled')
            if lbl:
                custom_roles.append({'key': key_clean, 'label': lbl, 'completes': comp})
        tpl.allowed_roles_json = custom_roles

        # Save declarative logic rules
        tpl.logic_rules_json = {
            'hide_status_from_beneficiary': request.POST.get('rule_hide_from_beneficiary') == 'on',
            'enable_self_reserve': request.POST.get('rule_enable_self_reserve') == 'on',
            'reserve_button_label': (request.POST.get('rule_reserve_label') or '').strip() or 'Übernehmen',
            'show_price_summary': request.POST.get('rule_show_price_summary') == 'on',
            'enable_event_invitations': request.POST.get('rule_enable_event_invitations') == 'on',
            'enable_ical_sync': request.POST.get('rule_enable_ical_sync') == 'on',
            'notify_on_overdue': request.POST.get('rule_notify_overdue') == 'on',
            'notify_on_low_stock': request.POST.get('rule_notify_low_stock') == 'on',
        }

        # Save custom fields
        cf_keys = request.POST.getlist('cf_key')
        cf_labels = request.POST.getlist('cf_label')
        cf_types = request.POST.getlist('cf_type')
        cf_options = request.POST.getlist('cf_options')
        custom_fields = []
        allowed_cf_types = ('text', 'textarea', 'number', 'currency', 'date', 'url', 'image', 'select', 'radio', 'multiselect', 'checkbox', 'rating', 'color')
        for idx, lbl in enumerate(cf_labels):
            lbl_clean = lbl.strip()
            if not lbl_clean:
                continue
            raw_key = cf_keys[idx] if idx < len(cf_keys) else ''
            key_clean = slugify(raw_key or lbl_clean).replace('-', '_')[:30] or f"field_{idx}"
            ftype = cf_types[idx] if idx < len(cf_types) and cf_types[idx] in allowed_cf_types else 'text'
            opts = cf_options[idx].strip() if idx < len(cf_options) else ''
            custom_fields.append({'key': key_clean, 'label': lbl_clean, 'type': ftype, 'options': opts})
        tpl.custom_fields_json = custom_fields

        # Save group_by, summary_rule_json, recurrence_json
        group_by = request.POST.get('group_by', 'none')
        if group_by not in {c[0] for c in ListTemplate.GROUP_BY_CHOICES}:
            group_by = 'none'
        tpl.group_by = group_by

        tpl.summary_rule_json = {
            'enabled': request.POST.get('summary_enabled') == 'on',
            'field': request.POST.get('summary_field', 'price').strip() or 'price',
            'op': request.POST.get('summary_op', 'sum') if request.POST.get('summary_op') in ('sum', 'avg', 'count') else 'sum',
            'status_filter': (request.POST.get('summary_status_filter') or '').strip(),
            'label': (request.POST.get('summary_label') or '').strip() or 'Auswertung',
            'unit': (request.POST.get('summary_unit') or '').strip(),
        }

        rec_mode = request.POST.get('recurrence_mode', 'none')
        if rec_mode not in ('none', 'daily', 'weekly', 'monthly', 'days'):
            rec_mode = 'none'
        try:
            rec_days = max(1, int(request.POST.get('recurrence_days', 7) or 7))
        except (TypeError, ValueError):
            rec_days = 7
        tpl.recurrence_json = {'mode': rec_mode, 'interval_days': rec_days}

        # Save UI layout & style
        layout_mode = request.POST.get('ui_layout_mode', 'row')
        if layout_mode not in ('row', 'cards', 'stacked'):
            layout_mode = 'row'
        card_width = request.POST.get('ui_card_width', '1/3')
        if card_width not in ('1/4', '1/3', '1/2', '3/4', 'hero'):
            card_width = '1/3'
        density = request.POST.get('ui_density', 'normal')
        if density not in ('normal', 'compact'):
            density = 'normal'
        tpl.ui_style_json = {
            'layout_mode': layout_mode,
            'card_width': card_width,
            'density': density,
            'show_creator': request.POST.get('ui_show_creator') == 'on',
        }
        tpl.save()

        messages.success(request, f"Vorlage „{category.name}“ gespeichert.")
        return redirect('core:template_studio')


class TemplateStudioDeleteView(StaffRequiredMixin, View):
    def post(self, request, pk):
        category = get_object_or_404(ListCategory, pk=pk)
        if category.lists.exists():
            messages.error(request, f"Vorlage „{category.name}“ wird noch von {category.lists.count()} Liste(n) verwendet.")
            return redirect('core:template_studio')
        name = category.name
        category.delete()
        messages.success(request, f"Vorlage „{name}“ gelöscht.")
        return redirect('core:template_studio')


class TemplateStudioExportView(StaffRequiredMixin, View):
    def get(self, request, pk):
        category = get_object_or_404(ListCategory.objects.select_related('template'), pk=pk)
        tpl = category.template
        payload = {
            'name': category.name,
            'slug': category.slug,
            'icon': category.icon,
            'logic_type': tpl.logic_type,
            'flags': {f['key']: bool(getattr(tpl, f['key'], False)) for f in TEMPLATE_STUDIO_FIELDS},
            'behavior': {
                'use_is_public': tpl.use_is_public,
                'use_allow_public_edit': tpl.use_allow_public_edit,
                'use_beneficiary': tpl.use_beneficiary,
                'use_secret_santa': tpl.use_secret_santa,
                'new_items_at_bottom': tpl.new_items_at_bottom,
            },
            'allowed_statuses_json': tpl.allowed_statuses_json,
            'allowed_roles_json': tpl.allowed_roles_json,
            'logic_rules_json': tpl.logic_rules_json,
            'ui_style_json': tpl.ui_style_json,
            'custom_fields_json': tpl.custom_fields_json,
            'group_by': tpl.group_by,
            'summary_rule_json': tpl.summary_rule_json,
            'recurrence_json': tpl.recurrence_json,
            'help_purpose': tpl.help_purpose,
            'help_fields': tpl.help_fields,
            'help_example': tpl.help_example,
        }
        resp = HttpResponse(json.dumps(payload, ensure_ascii=False, indent=2), content_type='application/json; charset=utf-8')
        resp['Content-Disposition'] = f'attachment; filename="vorlage-{category.slug}.json"'
        return resp


class TemplateStudioImportView(StaffRequiredMixin, View):
    def post(self, request):
        raw = ''
        if 'template_file' in request.FILES:
            raw = request.FILES['template_file'].read().decode('utf-8', errors='replace')
        elif request.POST.get('template_json'):
            raw = request.POST.get('template_json', '')

        raw = raw.strip()
        if raw.startswith('```'):
            lines = raw.splitlines()
            if lines and lines[0].startswith('```'):
                lines = lines[1:]
            if lines and lines[-1].strip() == '```':
                lines = lines[:-1]
            raw = '\n'.join(lines).strip()

        try:
            data = json.loads(raw)
            name = (data.get('name') or 'Importierte Vorlage').strip()
        except Exception:
            messages.error(request, 'Ungültige JSON-Datei für Vorlagen-Import.')
            return redirect('core:template_studio')

        base_slug = slugify(data.get('slug') or name) or 'vorlage'
        slug = base_slug
        counter = 2
        while ListCategory.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1

        category = ListCategory.objects.create(name=name, slug=slug, icon=data.get('icon') or '📋')
        valid_logics = {c[0] for c in ListTemplate.LOGIC_CHOICES}
        logic_type = data.get('logic_type', 'generic')
        if logic_type not in valid_logics:
            logic_type = 'generic'

        tpl = ListTemplate.objects.create(category=category, logic_type=logic_type)
        flags = data.get('flags') or {}
        for f in TEMPLATE_STUDIO_FIELDS:
            setattr(tpl, f['key'], bool(flags.get(f['key'], False)))
        beh = data.get('behavior') or {}
        for bkey in ('use_is_public', 'use_allow_public_edit', 'use_beneficiary', 'use_secret_santa', 'new_items_at_bottom'):
            setattr(tpl, bkey, bool(beh.get(bkey, False)))

        tpl.allowed_statuses_json = data.get('allowed_statuses_json') or []
        tpl.allowed_roles_json = data.get('allowed_roles_json') or []
        tpl.logic_rules_json = data.get('logic_rules_json') or {}
        tpl.ui_style_json = data.get('ui_style_json') or {}
        tpl.custom_fields_json = data.get('custom_fields_json') or []
        tpl.group_by = data.get('group_by') or 'none'
        tpl.summary_rule_json = data.get('summary_rule_json') or {}
        tpl.recurrence_json = data.get('recurrence_json') or {}
        tpl.help_purpose = data.get('help_purpose')
        tpl.help_fields = data.get('help_fields')
        tpl.help_example = data.get('help_example')
        tpl.save()

        if request.POST.get('create_bucket') == 'on':
            bucket = BucketList.objects.create(
                title=(data.get('bucket_title') or category.name).strip(),
                category=category,
                owner=request.user,
            )
            statuses = tpl.get_effective_statuses() if tpl.allowed_statuses_json else []
            status_map = {s['key']: s for s in statuses if isinstance(s, dict) and s.get('key')}
            default_demo_status = statuses[0]['key'][:20] if statuses else 'active'
            for idx, demo in enumerate(data.get('demo_items') or []):
                if not isinstance(demo, dict) or not demo.get('title'):
                    continue
                demo_status = str(demo.get('status') or default_demo_status)[:20]
                is_done = bool(status_map.get(demo_status, {}).get('completes', False))
                ListItem.objects.create(
                    bucket_list=bucket,
                    title=str(demo['title'])[:255],
                    notes=str(demo.get('notes') or ''),
                    amount=str(demo.get('amount')) if demo.get('amount') else None,
                    status=demo_status,
                    is_completed=is_done,
                    custom_data_json=demo.get('custom_data_json') if isinstance(demo.get('custom_data_json'), dict) else {},
                    created_by=request.user,
                    order=idx,
                )
            messages.success(request, f"Vorlage & Liste „{bucket.title}“ erfolgreich erstellt.")
            return redirect('core:list_detail', pk=bucket.id)

        messages.success(request, f"Vorlage „{category.name}“ erfolgreich importiert.")
        return redirect('core:template_studio_edit', pk=category.id)



