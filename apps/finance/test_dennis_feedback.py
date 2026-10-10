"""Dennis feedback (9 Oct 2026): disabled dropdown placeholders, clickable dashboard cards, balanced form buttons."""
import re
import uuid
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.members.models import Member
from apps.organisations.middleware import ActiveOrganisationMiddleware
from apps.organisations.models import Organisation, OrganisationMembership

from .models import FinancialRecord

User = get_user_model()


def blank_option(html, name):
    """The blank <option> of the <select name=...> in html."""
    select = re.search(r'<select[^>]*name="%s"[^>]*>(.*?)</select>' % re.escape(name), html, re.S)
    assert select, f"select {name} not found"
    option = re.search(r'<option[^>]*value=""[^>]*>', select.group(1))
    assert option, f"blank option for {name} not found"
    return option.group(0)


class DennisFeedbackTests(TestCase):
    def setUp(self):
        self.org = Organisation.objects.create(name="Dennis Org", slug="dennis-org")
        self.manager = User.objects.create_user(email="mgr@dennis.test", password="x")
        OrganisationMembership.objects.create(organisation=self.org, user=self.manager, role="manager")
        self.member = Member.objects.create(organisation=self.org, created_by=self.manager, updated_by=self.manager, membership_number="D1", first_name="Dee", last_name="Ennis")
        self.client.force_login(self.manager)
        session = self.client.session
        session[ActiveOrganisationMiddleware.SESSION_KEY] = self.org.pk
        session.save()

    # Item 2: placeholders on required dropdowns cannot be picked.
    def test_required_dropdown_prompts_are_disabled(self):
        html = self.client.get(reverse("finance_create")).content.decode()
        self.assertIn("disabled", blank_option(html, "record_type"))
        self.assertIn("disabled", blank_option(html, "payment_method"))
        self.assertIn("Choose a record type", html)

    def test_optional_dropdowns_keep_a_selectable_blank(self):
        html = self.client.get(reverse("finance_create")).content.decode()
        self.assertNotIn("disabled", blank_option(html, "member"))
        self.assertNotIn("disabled", blank_option(html, "purpose"))

    def test_missing_record_type_is_still_rejected(self):
        data = {
            "record_type": "", "member": str(self.member.pk), "amount": "10.00", "paid_amount": "",
            "payment_method": "cash", "status": "pending", "payment_date": "2026-10-09",
            "purpose": "", "purpose_description": "", "reference_number": "", "notes": "",
            "submission_key": str(uuid.uuid4()),
        }
        response = self.client.post(reverse("finance_create"), data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors.get("record_type"))
        self.assertFalse(FinancialRecord.objects.exists())

    # Item 4: dashboard cards link to their pages.
    def test_dashboard_cards_are_links(self):
        html = self.client.get(reverse("dashboard")).content.decode()
        self.assertEqual(html.count('class="metric-card metric-link'), 10)
        self.assertNotIn('<article class="metric-card', html)
        for href in [
            reverse("member_list"),
            reverse("member_list") + "?status=active",
            reverse("structure_list"),
            reverse("farm_list"),
            reverse("collection_list"),
            reverse("finance_list") + "?type=member_payment",
            reverse("finance_list") + "?type=expense",
            reverse("finance_list"),
        ]:
            self.assertIn(f'href="{href}"', html)

    def test_dashboard_card_targets_open_for_manager(self):
        for url in [
            reverse("member_list") + "?status=active",
            reverse("structure_list"),
            reverse("farm_list"),
            reverse("collection_list"),
            reverse("finance_list") + "?type=member_payment",
            reverse("finance_list") + "?type=expense",
        ]:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    # Items 1, 4 and 5: shared CSS rules.
    def test_shared_css_rules_present(self):
        css = (Path(settings.BASE_DIR) / "static" / "css" / "app.css").read_text(encoding="utf-8")
        self.assertIn(".form-actions>a:not(.button){", css)
        self.assertIn(".form-grid p,.stack p{align-content:start}", css)
        self.assertIn("a.metric-link:hover", css)
        self.assertIn("a.metric-link:focus-visible", css)

    def test_payment_form_cancel_sits_in_form_actions(self):
        html = self.client.get(reverse("finance_create")).content.decode()
        self.assertRegex(html, r'class="form-actions"><a href="%s">Cancel</a>' % re.escape(reverse("finance_list")))
