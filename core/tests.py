from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from core.models import ListCategory, ListTemplate, BucketList, ListItem, UserSetting
from core.views import get_price_sums


class BuckezzRegressionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester', password='secret')
        self.category = ListCategory.objects.create(
            name='Einkauf',
            icon='🛒',
            slug='einkauf',
        )
        self.template = ListTemplate.objects.create(
            category=self.category,
            logic_type='generic',
            use_price=True,
            use_amount=True,
            use_status=True,
        )
        self.bucket = BucketList.objects.create(
            title='Wocheneinkauf',
            category=self.category,
            owner=self.user,
        )
        self.item = ListItem.objects.create(
            bucket_list=self.bucket,
            title='Äpfel',
            price=Decimal('2.50'),
            amount='2 kg',
        )

    def test_home_view_unauthenticated(self):
        resp = self.client.get(reverse('core:home'))
        self.assertEqual(resp.status_code, 200)

    def test_home_view_authenticated_redirects_to_dashboard(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('core:home'))
        self.assertRedirects(resp, reverse('core:dashboard'))

    def test_home_view_authenticated_with_start(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('core:home') + '?start=1')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Wocheneinkauf')

    def test_dashboard_requires_login(self):
        resp = self.client.get(reverse('core:dashboard'))
        self.assertEqual(resp.status_code, 302)

    def test_dashboard_authenticated(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('core:dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Wocheneinkauf')

    def test_create_bucket(self):
        self.client.force_login(self.user)
        resp = self.client.post(reverse('core:list_create'), {
            'category_id': self.category.id,
            'title': 'Baumarkt',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(BucketList.objects.filter(title='Baumarkt', owner=self.user).exists())

    def test_bucket_detail_view(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('core:list_detail', args=[self.bucket.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Äpfel')

    def test_add_toggle_delete_item(self):
        self.client.force_login(self.user)
        add_resp = self.client.post(reverse('core:add_item', args=[self.bucket.id]), {
            'title': 'Brot',
            'price': '3.20',
            'amount': '1',
            'notes': '',
        })
        self.assertIn(add_resp.status_code, (200, 204, 302))
        brot = ListItem.objects.get(bucket_list=self.bucket, title='Brot')

        toggle_resp = self.client.post(reverse('core:toggle_item', args=[brot.id]))
        self.assertIn(toggle_resp.status_code, (200, 204, 302))
        brot.refresh_from_db()
        self.assertTrue(brot.is_completed)

        del_resp = self.client.post(reverse('core:delete_item', args=[brot.id]))
        self.assertIn(del_resp.status_code, (200, 204, 302))
        self.assertFalse(ListItem.objects.filter(id=brot.id).exists())

    def test_price_sums_calculation(self):
        active = [self.item]
        completed = []
        sums = get_price_sums(self.bucket, active, completed)
        self.assertAlmostEqual(sums['active_price_sum'], 5.0)
        self.assertAlmostEqual(sums['completed_price_sum'], 0.0)
        self.assertAlmostEqual(sums['total_price_sum'], 5.0)

    def test_calendar_and_settings_views(self):
        self.client.force_login(self.user)
        cal_resp = self.client.get(reverse('core:calendar'))
        self.assertIn(cal_resp.status_code, [200, 302])
        cal_kit_resp = self.client.get(reverse('cal_kit:calendar'))
        self.assertEqual(cal_kit_resp.status_code, 200)

        settings_resp = self.client.get(reverse('core:settings'))
        self.assertEqual(settings_resp.status_code, 200)
        self.assertNotContains(settings_resp, 'Erweiterte Farbwerte')

        post_resp = self.client.post(reverse('core:settings'), {
            'timezone': 'Europe/Berlin',
        })
        self.assertRedirects(post_resp, reverse('core:dashboard'))
        self.assertEqual(UserSetting.objects.get(user=self.user).timezone, 'Europe/Berlin')

    def test_healthz_endpoint(self):
        resp = self.client.get('/healthz')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['status'], 'ok')

    def test_design_studio_accessible(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('design_studio:studio'))
        self.assertEqual(resp.status_code, 200)

    def test_template_studio_requires_staff(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('core:template_studio'))
        self.assertEqual(resp.status_code, 403)

    def test_template_studio_create_edit_delete(self):
        staff = User.objects.create_user(username='admin_staff', password='secret', is_staff=True)
        self.client.force_login(staff)

        list_resp = self.client.get(reverse('core:template_studio'))
        self.assertEqual(list_resp.status_code, 200)

        create_resp = self.client.post(reverse('core:template_studio_create'), {
            'name': 'Packliste Urlaub',
            'icon': '✈️',
            'logic_type': 'generic',
            'use_amount': 'on',
            'use_subchecklist': 'on',
            'use_is_public': 'on',
        })
        self.assertRedirects(create_resp, reverse('core:template_studio'))
        created_cat = ListCategory.objects.get(name='Packliste Urlaub')
        self.assertTrue(created_cat.template.use_amount)
        self.assertTrue(created_cat.template.use_subchecklist)
        self.assertFalse(created_cat.template.use_price)

        edit_resp = self.client.post(reverse('core:template_studio_edit', args=[created_cat.id]), {
            'name': 'Packliste Urlaub',
            'icon': '🏖️',
            'logic_type': 'todo',
            'use_price': 'on',
        })
        self.assertRedirects(edit_resp, reverse('core:template_studio'))
        created_cat.refresh_from_db()
        self.assertEqual(created_cat.icon, '🏖️')
        self.assertEqual(created_cat.template.logic_type, 'todo')
        self.assertTrue(created_cat.template.use_price)

        # Protected delete when category has a BucketList
        prot_resp = self.client.post(reverse('core:template_studio_delete', args=[self.category.id]))
        self.assertRedirects(prot_resp, reverse('core:template_studio'))
        self.assertTrue(ListCategory.objects.filter(id=self.category.id).exists())

        # Clean delete when unused
        del_resp = self.client.post(reverse('core:template_studio_delete', args=[created_cat.id]))
        self.assertRedirects(del_resp, reverse('core:template_studio'))
        self.assertFalse(ListCategory.objects.filter(id=created_cat.id).exists())

    def test_multi_photo_and_subchecklist_photo_upload(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from core.models import ListItemImage

        self.template.use_image = True
        self.template.use_subchecklist_photos = True
        self.template.save()

        self.client.force_login(self.user)
        tiny_png = (
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
            b'\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00'
            b'\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
        )
        img1 = SimpleUploadedFile('a.png', tiny_png, content_type='image/png')
        img2 = SimpleUploadedFile('b.png', tiny_png, content_type='image/png')
        sub_img = SimpleUploadedFile('sub.png', tiny_png, content_type='image/png')

        resp = self.client.post(reverse('core:add_item', args=[self.bucket.id]), {
            'title': 'Foto-Test',
            'notes': '',
            'images': [img1, img2],
            'sub_title': ['Punkt 1', 'Punkt 2'],
            'sub_existing_image': ['', ''],
            'sub_image_0': sub_img,
        })
        self.assertIn(resp.status_code, (200, 204, 302))
        created = ListItem.objects.get(bucket_list=self.bucket, title='Foto-Test')
        self.assertEqual(created.images.count(), 2)
        self.assertEqual(len(created.subchecklist_json), 2)
        self.assertTrue(created.subchecklist_json[0].get('image', '').startswith('/media/subchecklist_photos/'))
        self.assertNotIn('image', created.subchecklist_json[1])

        # Clean up uploaded files and test delete_image_ids
        first_img = created.images.first()
        edit_resp = self.client.post(reverse('core:edit_item', args=[created.id]), {
            'title': 'Foto-Test',
            'notes': '',
            'delete_image_ids': [str(first_img.id)],
        })
        self.assertIn(edit_resp.status_code, (200, 204, 302))
        self.assertEqual(created.images.count(), 1)
        for remaining in ListItemImage.objects.filter(item=created):
            remaining.image.delete(save=False)

    def test_custom_statuses_and_logic_builder_rules(self):
        staff = User.objects.create_user(username='logic_admin', password='secret', is_staff=True)
        self.client.force_login(staff)

        resp = self.client.post(reverse('core:template_studio_create'), {
            'name': 'Workflow Liste',
            'icon': '⚙️',
            'logic_type': 'generic',
            'status_key': ['active', 'waiting', 'done'],
            'status_label': ['Offen', 'In Klärung', 'Abgeschlossen'],
            'status_completes': ['0', '0', '1'],
            'rule_enable_self_reserve': 'on',
            'rule_reserve_label': 'Schnappen',
            'rule_show_price_summary': 'on',
        })
        self.assertRedirects(resp, reverse('core:template_studio'))

        cat = ListCategory.objects.get(name='Workflow Liste')
        self.assertEqual(len(cat.template.allowed_statuses_json), 3)
        self.assertEqual(cat.template.logic_rules_json['reserve_button_label'], 'Schnappen')
        self.assertTrue(cat.template.logic_rules_json['enable_self_reserve'])

        bucket = BucketList.objects.create(title='Test Workflow', category=cat, owner=staff)
        item = ListItem.objects.create(bucket_list=bucket, title='Aufgabe 1')

        # Set to 'waiting' (not completed)
        self.client.post(reverse('core:edit_item', args=[item.id]), {
            'title': 'Aufgabe 1',
            'notes': '',
            'item_status': 'waiting',
        })
        item.refresh_from_db()
        self.assertEqual(item.status, 'waiting')
        self.assertFalse(item.is_completed)

        # Set to 'done' (completes=True)
        self.client.post(reverse('core:edit_item', args=[item.id]), {
            'title': 'Aufgabe 1',
            'notes': '',
            'item_status': 'done',
        })
        item.refresh_from_db()
        self.assertEqual(item.status, 'done')
        self.assertTrue(item.is_completed)

    def test_allowed_roles_and_entkoppelte_rules(self):
        from core.models import Person, ItemPersonRole
        staff = User.objects.create_user(username='role_admin', password='secret', is_staff=True)
        self.client.force_login(staff)

        resp = self.client.post(reverse('core:template_studio_create'), {
            'name': 'Verleih-Test',
            'icon': '📦',
            'logic_type': 'generic',
            'use_persons': 'on',
            'role_key': ['borrowed_from', 'lent_to'],
            'role_label': ['Geliehen von', 'Verliehen an'],
            'rule_enable_event_invitations': 'on',
            'rule_enable_ical_sync': 'on',
        })
        self.assertRedirects(resp, reverse('core:template_studio'))

        cat = ListCategory.objects.get(name='Verleih-Test')
        self.assertEqual(len(cat.template.allowed_roles_json), 2)
        self.assertTrue(cat.template.get_logic_rule('enable_event_invitations'))
        self.assertTrue(cat.template.get_logic_rule('enable_ical_sync'))

        bucket = BucketList.objects.create(title='Werkzeug', category=cat, owner=staff)
        person = Person.objects.create(name='Max')
        item = ListItem.objects.create(bucket_list=bucket, title='Bohrer')
        ItemPersonRole.objects.create(item=item, person=person, role='lent_to')

        detail_resp = self.client.get(reverse('core:list_detail', args=[bucket.id]))
        self.assertEqual(detail_resp.status_code, 200)
        self.assertContains(detail_resp, 'Verliehen an')
        self.assertNotContains(detail_resp, 'Wunsch erfüllt')

    def test_ui_style_layout_modes(self):
        staff = User.objects.create_user(username='ui_admin', password='secret', is_staff=True)
        self.client.force_login(staff)

        resp = self.client.post(reverse('core:template_studio_create'), {
            'name': 'Karten-Liste',
            'icon': '🃏',
            'logic_type': 'generic',
            'ui_layout_mode': 'cards',
            'ui_density': 'compact',
            'ui_genre': 'scifi',
            # ui_show_creator omitted -> False
        })
        self.assertRedirects(resp, reverse('core:template_studio'))

        cat = ListCategory.objects.get(name='Karten-Liste')
        self.assertEqual(cat.template.get_ui_style()['layout_mode'], 'cards')
        self.assertEqual(cat.template.get_ui_style()['density'], 'compact')
        self.assertEqual(cat.template.get_ui_style()['genre'], 'scifi')
        self.assertFalse(cat.template.get_ui_style()['show_creator'])

        # Re-opening builder renders the saved genre pre-selected
        edit_resp = self.client.get(reverse('core:template_studio_edit', args=[cat.pk]))
        self.assertEqual(edit_resp.status_code, 200)
        self.assertContains(edit_resp, 'value="scifi" selected')

        bucket = BucketList.objects.create(title='Karten-Test', category=cat, owner=staff)
        ListItem.objects.create(bucket_list=bucket, title='Eintrag A', created_by=staff)
        detail_resp = self.client.get(reverse('core:list_detail', args=[bucket.id]))
        self.assertEqual(detail_resp.status_code, 200)
        self.assertContains(detail_resp, 'col-12 col-md-6 col-xl-4')
        self.assertContains(detail_resp, 'data-genre="scifi"')
        self.assertContains(detail_resp, '--ds-genre-accent:')
        self.assertContains(detail_resp, 'ds-genre-svg-layer')
        self.assertNotContains(detail_resp, 'Erstellt von ui_admin')

    def test_card_layout_and_hidden_custom_fields(self):
        import json
        staff = User.objects.create_user(username='layout_admin', password='secret', is_staff=True)
        self.client.force_login(staff)

        card_layout = {
            'header': ['use_brand'],
            'body': ['cf:autor'],
            'footer': ['use_price'],
            'hidden': ['cf:intern'],
        }
        resp = self.client.post(reverse('core:template_studio_create'), {
            'name': 'Bücher-Layout',
            'icon': '📚',
            'logic_type': 'generic',
            'use_brand': 'on',
            'use_price': 'on',
            'cf_key': ['autor', 'intern'],
            'cf_label': ['Autor', 'Interne Notiz'],
            'cf_type': ['text', 'text'],
            'cf_options': ['', ''],
            'cf_zone': ['body', 'hidden'],
            'cf_show_card': ['1', '0'],
            'ui_layout_mode': 'cards',
            'ui_card_layout_json': json.dumps(card_layout),
        })
        self.assertRedirects(resp, reverse('core:template_studio'))

        cat = ListCategory.objects.get(name='Bücher-Layout')
        self.assertEqual(cat.template.get_ui_style()['card_layout'], card_layout)
        self.assertEqual(cat.template.custom_fields_json[0]['zone'], 'body')
        self.assertTrue(cat.template.custom_fields_json[0]['show_on_card'])
        self.assertFalse(cat.template.custom_fields_json[1]['show_on_card'])

        bucket = BucketList.objects.create(title='Leseliste', category=cat, owner=staff)
        ListItem.objects.create(
            bucket_list=bucket,
            title='Der Schwarm',
            brand='Heyne',
            price=14.90,
            custom_data_json={'autor': 'Frank Schätzing', 'intern': 'Geheimcode 123'},
            created_by=staff,
        )
        detail_resp = self.client.get(reverse('core:list_detail', args=[bucket.id]))
        self.assertEqual(detail_resp.status_code, 200)
        self.assertContains(detail_resp, 'Heyne')
        self.assertContains(detail_resp, 'Frank Schätzing')
        self.assertNotContains(detail_resp, 'Geheimcode 123')

    def test_custom_person_role_completes_item(self):
        from core.models import Person, ItemPersonRole
        staff = User.objects.create_user(username='custom_role_admin', password='secret', is_staff=True)
        self.client.force_login(staff)

        resp = self.client.post(reverse('core:template_studio_create'), {
            'name': 'Rückgabe-Tracker',
            'icon': '🔄',
            'logic_type': 'generic',
            'use_persons': 'on',
            'role_key': ['lent_to', 'zurueckgegeben'],
            'role_label': ['Verliehen an', 'Zurückgegeben'],
            'role_completes': ['0', '1'],
        })
        self.assertRedirects(resp, reverse('core:template_studio'))

        cat = ListCategory.objects.get(name='Rückgabe-Tracker')
        bucket = BucketList.objects.create(title='Verleih', category=cat, owner=staff)
        person = Person.objects.create(name='Lisa')
        item = ListItem.objects.create(bucket_list=bucket, title='Leiter')
        role = ItemPersonRole.objects.create(item=item, person=person, role='lent_to')

        cycle_resp = self.client.post(reverse('core:cycle_person_role', args=[role.id]), {
            'role': 'zurueckgegeben',
        })
        self.assertIn(cycle_resp.status_code, (200, 204))
        role.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(role.role, 'zurueckgegeben')
        self.assertTrue(item.is_completed)

    def test_custom_fields_grouping_kpi_recurrence_alerts_and_export_import(self):
        from datetime import timedelta
        from django.utils import timezone
        import json

        staff = User.objects.create_user(username='flex_admin', password='secret', is_staff=True)
        self.client.force_login(staff)

        resp = self.client.post(reverse('core:template_studio_create'), {
            'name': 'Umzugskartons',
            'icon': '📦',
            'logic_type': 'generic',
            'cf_label': ['Zimmer', 'Gewicht'],
            'cf_key': ['zimmer', 'gewicht'],
            'cf_type': ['text', 'number'],
            'cf_options': ['', ''],
            'group_by': 'status',
            'summary_enabled': 'on',
            'summary_label': 'Gesamtgewicht',
            'summary_unit': 'kg',
            'summary_field': 'custom:gewicht',
            'summary_op': 'sum',
            'recurrence_mode': 'daily',
            'recurrence_days': '1',
            'rule_notify_overdue': 'on',
        })
        self.assertRedirects(resp, reverse('core:template_studio'))

        cat = ListCategory.objects.get(name='Umzugskartons')
        self.assertEqual(len(cat.template.custom_fields_json), 2)
        self.assertEqual(cat.template.group_by, 'status')

        bucket = BucketList.objects.create(title='Umzug 2026', category=cat, owner=staff)
        self.client.post(reverse('core:add_item', args=[bucket.id]), {
            'title': 'Karton 1',
            'notes': '',
            'custom_zimmer': 'Küche',
            'custom_gewicht': '12.5',
        })
        k1 = ListItem.objects.get(bucket_list=bucket, title='Karton 1')
        self.assertEqual(k1.custom_data_json['zimmer'], 'Küche')

        # Overdue alert + auto-reset recurrence
        k2 = ListItem.objects.create(
            bucket_list=bucket,
            title='Karton 2',
            end_date=timezone.now() - timedelta(days=1),
            is_completed=True,
            completed_at=timezone.now() - timedelta(days=2),
        )
        detail_resp = self.client.get(reverse('core:list_detail', args=[bucket.id]))
        self.assertEqual(detail_resp.status_code, 200)
        k2.refresh_from_db()
        self.assertFalse(k2.is_completed)  # auto-reset by daily recurrence
        self.assertContains(detail_resp, 'Gesamtgewicht')
        self.assertContains(detail_resp, 'Küche')
        self.assertContains(detail_resp, 'Überfällig')

        # Export & Import JSON
        exp_resp = self.client.get(reverse('core:template_studio_export', args=[cat.id]))
        self.assertEqual(exp_resp.status_code, 200)
        exported = json.loads(exp_resp.content.decode('utf-8'))
        self.assertEqual(exported['name'], 'Umzugskartons')

        imp_resp = self.client.post(reverse('core:template_studio_import'), {
            'template_json': json.dumps(exported),
        })
        self.assertEqual(imp_resp.status_code, 302)
        self.assertEqual(ListCategory.objects.filter(name='Umzugskartons').count(), 2)

    def test_poll_and_media_custom_fields(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        staff = User.objects.create_user(username='poll_admin', password='secret', is_staff=True)
        self.client.force_login(staff)

        resp = self.client.post(reverse('core:template_studio_create'), {
            'name': 'Umfrage & Links',
            'icon': '📊',
            'logic_type': 'generic',
            'cf_label': ['Website', 'Beleg', 'Abstimmung', 'Tags', 'Details', 'Sterne'],
            'cf_key': ['website', 'beleg', 'abstimmung', 'tags', 'details', 'sterne'],
            'cf_type': ['url', 'image', 'radio', 'multiselect', 'textarea', 'rating'],
            'cf_options': ['', '', 'Ja, Nein', 'Wichtig, Dringend, Optional', '', ''],
        })
        self.assertRedirects(resp, reverse('core:template_studio'))

        cat = ListCategory.objects.get(name='Umfrage & Links')
        bucket = BucketList.objects.create(title='Team Umfrage', category=cat, owner=staff)
        tiny_png = (
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
            b'\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00'
            b'\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
        )
        img = SimpleUploadedFile('beleg.png', tiny_png, content_type='image/png')

        self.client.post(reverse('core:add_item', args=[bucket.id]), {
            'title': 'Vorschlag 1',
            'notes': '',
            'custom_website': 'https://example.com',
            'custom_file_beleg': img,
            'custom_abstimmung': 'Ja',
            'custom_tags': ['Wichtig', 'Optional'],
            'custom_details': 'Mehrzeilige Beschreibung',
            'custom_sterne': '5',
        })
        item = ListItem.objects.get(bucket_list=bucket, title='Vorschlag 1')
        self.assertEqual(item.custom_data_json['website'], 'https://example.com')
        self.assertTrue(item.custom_data_json['beleg'].startswith('/media/custom_field_photos/'))
        self.assertEqual(item.custom_data_json['abstimmung'], 'Ja')
        self.assertEqual(item.custom_data_json['tags'], ['Wichtig', 'Optional'])
        self.assertEqual(item.custom_data_json['sterne'], '5')

        detail_resp = self.client.get(reverse('core:list_detail', args=[bucket.id]))
        self.assertEqual(detail_resp.status_code, 200)
        self.assertContains(detail_resp, 'https://example.com')
        self.assertContains(detail_resp, 'Wichtig, Optional')

    def test_ai_assistant_import_with_codefence_and_create_bucket(self):
        import json
        staff = User.objects.create_user(username='ai_admin', password='secret', is_staff=True)
        self.client.force_login(staff)

        payload = {
            'name': 'KFZ-Wartungsbuch',
            'bucket_title': 'Mein Golf VIII',
            'icon': '🚗',
            'logic_type': 'generic',
            'custom_fields_json': [
                {'key': 'km', 'label': 'Kilometerstand', 'type': 'number', 'options': ''},
            ],
            'demo_items': [
                {'title': 'Ölwechsel', 'notes': '5W-30', 'custom_data_json': {'km': '45000'}},
            ],
        }
        fenced = f"```json\n{json.dumps(payload)}\n```"
        resp = self.client.post(reverse('core:template_studio_import'), {
            'template_json': fenced,
            'create_bucket': 'on',
        })
        self.assertEqual(resp.status_code, 302)
        bucket = BucketList.objects.get(title='Mein Golf VIII', owner=staff)
        self.assertRedirects(resp, reverse('core:list_detail', args=[bucket.id]))
        self.assertEqual(bucket.items.count(), 1)
        self.assertEqual(bucket.items.first().custom_data_json['km'], '45000')

    def test_list_configure_frontend_page(self):
        owner = User.objects.create_user(username='cfg_owner', password='secret')
        other = User.objects.create_user(username='cfg_other', password='secret')
        cat = ListCategory.objects.create(name='CfgCat', icon='📋')
        ListTemplate.objects.create(category=cat, logic_type='generic')
        bucket = BucketList.objects.create(title='Meine Liste', category=cat, owner=owner)

        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse('core:list_configure', args=[bucket.id])).status_code, 403)

        self.client.force_login(owner)
        detail = self.client.get(reverse('core:list_detail', args=[bucket.id]))
        self.assertContains(detail, reverse('core:list_configure', args=[bucket.id]))
        self.assertNotContains(detail, '/admin/core/bucketlist/')

        get_resp = self.client.get(reverse('core:list_configure', args=[bucket.id]))
        self.assertEqual(get_resp.status_code, 200)

        post_resp = self.client.post(reverse('core:list_configure', args=[bucket.id]), {
            'title': 'Umbenannte Liste',
            'category': cat.id,
            'is_public': 'on',
            'shared_with': [other.id],
        })
        self.assertRedirects(post_resp, reverse('core:list_detail', args=[bucket.id]))
        bucket.refresh_from_db()
        self.assertEqual(bucket.title, 'Umbenannte Liste')
        self.assertTrue(bucket.is_public)
        self.assertIn(other, bucket.shared_with.all())

    def test_calendar_provider_todos_and_all_event_types(self):
        from datetime import datetime
        from django.utils import timezone

        owner = User.objects.create_user(username='cal_owner', password='secret')
        self.client.force_login(owner)

        todo_cat = ListCategory.objects.create(name='To-Do Test', icon='✅', slug='todo-test')
        ListTemplate.objects.create(
            category=todo_cat,
            logic_type='todo',
            use_end_date=True,
            use_reminder=True,
            custom_fields_json=[{'key': 'due_check', 'label': 'Kontrolle', 'type': 'date', 'options': ''}],
        )
        todo_list = BucketList.objects.create(title='Meine To-Dos', category=todo_cat, owner=owner)

        # Create To-Do via AddItemView with end_date, reminder_at, custom date
        add_resp = self.client.post(reverse('core:add_item', args=[todo_list.id]), {
            'title': 'Steuer abgeben',
            'end_date': '2026-11-25T18:00',
            'reminder_at': '2026-11-24T09:00',
            'custom_due_check': '2026-11-23',
            'notes': 'Belege prüfen',
        })
        self.assertIn(add_resp.status_code, (200, 204, 302))

        # Event with start + end range and Bootstrap icon category
        ev_cat = ListCategory.objects.create(name='Bücher Test', icon='bi-book', slug='buecher-test')
        ListTemplate.objects.create(category=ev_cat, logic_type='event', use_start_date=True, use_end_date=True, use_tracker=True)
        ev_list = BucketList.objects.create(title='Events', category=ev_cat, owner=owner)
        ListItem.objects.create(
            bucket_list=ev_list,
            title='Buchclub',
            start_date=timezone.make_aware(datetime(2026, 11, 20, 18, 0)),
            end_date=timezone.make_aware(datetime(2026, 11, 20, 20, 0)),
            tracker_times='08:00, 20:00',
        )
        ListItem.objects.create(
            bucket_list=ev_list,
            title='Projektstart',
            start_date=timezone.make_aware(datetime(2026, 11, 18, 10, 0)),
        )

        # Realistic FullCalendar Europe/Berlin query string (including unencoded +01:00)
        res = self.client.get(
            reverse('cal_kit:events_json') + '?start=2026-10-26T00:00:00+01:00&end=2026-12-07T00:00:00+01:00'
        )
        self.assertEqual(res.status_code, 200)
        events = res.json()
        by_type = {}
        for e in events:
            et = (e.get('extendedProps') or {}).get('event_type')
            by_type.setdefault(et, []).append(e)
            # Never leak raw 'bi-...' class names into visible titles
            self.assertNotIn('bi-book', e['title'])
            if et == 'tracker':
                self.assertFalse(e.get('editable', True))
            else:
                self.assertTrue(e.get('editable', False))
            self.assertTrue((e.get('extendedProps') or {}).get('read_only'))

        self.assertEqual(len(by_type.get('end', [])), 1)
        self.assertEqual(by_type['end'][0]['title'], 'Steuer abgeben')
        self.assertEqual(len(by_type.get('reminder', [])), 1)
        self.assertEqual(len(by_type.get('custom_date', [])), 1)
        self.assertEqual(by_type['custom_date'][0]['start'], '2026-11-23')
        self.assertEqual(len(by_type.get('range', [])), 1)
        self.assertEqual(len(by_type.get('start', [])), 1)
        self.assertEqual(len(by_type.get('tracker', [])), 2)

        # Drag & Drop moves on To-Do end_date, reminder_at, custom_date, and range resize
        import json as _json
        todo_item = ListItem.objects.get(title='Steuer abgeben')
        todo_item.reminder_sent = True
        todo_item.save(update_fields=['reminder_sent'])

        mv_end = self.client.post(
            reverse('cal_kit:move_event', args=[by_type['end'][0]['id']]),
            _json.dumps({'start': '2026-11-28T16:30:00+01:00'}),
            content_type='application/json',
        )
        self.assertEqual(mv_end.status_code, 200)
        mv_rem = self.client.post(
            reverse('cal_kit:move_event', args=[by_type['reminder'][0]['id']]),
            _json.dumps({'start': '2026-11-27T08:00:00+01:00'}),
            content_type='application/json',
        )
        self.assertEqual(mv_rem.status_code, 200)
        mv_cf = self.client.post(
            reverse('cal_kit:move_event', args=[by_type['custom_date'][0]['id']]),
            _json.dumps({'start': '2026-11-26T00:00:00Z', 'startStr': '2026-11-26', 'allDay': True}),
            content_type='application/json',
        )
        self.assertEqual(mv_cf.status_code, 200)
        todo_item.refresh_from_db()
        self.assertEqual(timezone.localtime(todo_item.end_date).day, 28)
        self.assertEqual(timezone.localtime(todo_item.reminder_at).day, 27)
        self.assertFalse(todo_item.reminder_sent)
        self.assertEqual(todo_item.custom_data_json['due_check'], '2026-11-26')

        mv_range = self.client.post(
            reverse('cal_kit:move_event', args=[by_type['range'][0]['id']]),
            _json.dumps({'start': '2026-11-21T19:00:00+01:00', 'end': '2026-11-21T22:00:00+01:00'}),
            content_type='application/json',
        )
        self.assertEqual(mv_range.status_code, 200)
        buchclub = ListItem.objects.get(title='Buchclub')
        self.assertEqual(timezone.localtime(buchclub.start_date).day, 21)
        self.assertEqual(timezone.localtime(buchclub.end_date).hour, 22)

        # Unauthorized user cannot move another user's list item
        intruder = User.objects.create_user(username='cal_intruder', password='secret')
        self.client.force_login(intruder)
        mv_denied = self.client.post(
            reverse('cal_kit:move_event', args=[by_type['end'][0]['id']]),
            _json.dumps({'start': '2026-11-30T10:00:00+01:00'}),
            content_type='application/json',
        )
        self.assertEqual(mv_denied.status_code, 400)
        todo_item.refresh_from_db()
        self.assertEqual(timezone.localtime(todo_item.end_date).day, 28)
        self.client.force_login(owner)

        # iCal feed includes To-Do deadline, VALARM reminder, range, start, and custom date
        ics = self.client.get(reverse('cal_kit:ical_feed')).content.decode('utf-8')
        self.assertIn('Steuer abgeben', ics)
        self.assertIn('BEGIN:VALARM', ics)
        self.assertIn('Kontrolle', ics)
        self.assertIn('Buchclub', ics)
