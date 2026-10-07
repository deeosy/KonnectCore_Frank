"""Phone-size UI fixes from the 7 Oct 2026 UI review (items 1-5).

1. List tables become labelled cards on phones (every body cell has data-label).
2. Whole rows are tappable (primary link carries row-link, stretched by CSS).
3. No text below 12px; base font 16px.
4. Payment form: no '---------' placeholders, amount paid starts empty.
5. Money shows as 'GHS 2,160.00' on one line (non-breaking space).
"""
import re
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.template import Context, Template
from django.test import TestCase
from django.urls import reverse

from apps.finance.models import FinancialRecord
from apps.members.models import Member
from apps.organisations.middleware import ActiveOrganisationMiddleware
from apps.organisations.models import Organisation, OrganisationMembership

User = get_user_model()
BASE = Path(settings.BASE_DIR)
CSS = BASE / "static" / "css" / "app.css"
TEMPLATES = BASE / "templates"
NBSP = "\u00a0"
LIST_TEMPLATES = [
    "members/member_list.html",
    "collections/collection_list.html",
    "finance/list.html",
    "organisations/staff_list.html",
]


def body_cells(html):
    """Opening <td> tags inside <tbody>, ignoring full-width empty-state cells."""
    tags = []
    for body in re.findall(r"<tbody>(.*?)</tbody>", html, re.S):
        tags += [t for t in re.findall(r"<td\b[^>]*>", body) if "colspan" not in t]
    return tags


class MoneyFilterTests(TestCase):
    def render(self, value, currency="GHS"):
        return Template("{% load money %}{{ value|money:currency }}").render(
            Context({"value": value, "currency": currency}))

    def test_thousands_separator_two_decimals_one_line(self):
        self.assertEqual(self.render(Decimal("2160")), "GHS" + NBSP + "2,160.00")
        self.assertEqual(self.render(Decimal("1234567.5")), "GHS" + NBSP + "1,234,567.50")
        self.assertEqual(self.render(Decimal("0")), "GHS" + NBSP + "0.00")

    def test_negative_and_missing_values(self):
        self.assertEqual(self.render(Decimal("-5")), "-GHS" + NBSP + "5.00")
        self.assertEqual(self.render(None), "")

    def test_no_raw_currency_amount_pairs_left_in_money_templates(self):
        for name in LIST_TEMPLATES + ["reports/dashboard.html"]:
            source = (TEMPLATES / name).read_text(encoding="utf-8")
            self.assertNotRegex(source, r"\{\{ active_organisation\.currency \}\} \{\{", name)


class MobileListTests(TestCase):
    def setUp(self):
        self.org = Organisation.objects.create(name="Mobile Org", slug="mobile-org", currency="GHS")
        self.admin = User.objects.create_user(email="mobile-admin@x.test", password="x")
        OrganisationMembership.objects.create(organisation=self.org, user=self.admin, role="admin")
        self.member = Member.objects.create(
            organisation=self.org, created_by=self.admin, updated_by=self.admin,
            membership_number="MB-1", first_name="Ama", last_name="Mensah")
        self.record = FinancialRecord.objects.create(
            organisation=self.org, record_type="due", member=self.member, amount=Decimal("1234.50"),
            paid_amount=0, payment_method="cash", status="pending", payment_date=date(2026, 9, 1),
            recorded_by=self.admin)
        self.client.force_login(self.admin)
        session = self.client.session
        session[ActiveOrganisationMiddleware.SESSION_KEY] = self.org.pk
        session.save()

    def page(self, name):
        response = self.client.get(reverse(name))
        self.assertEqual(response.status_code, 200, name)
        return response.content.decode()

    def test_list_cells_are_labelled_for_phone_cards(self):
        for name in ("member_list", "finance_list", "staff_list"):
            html = self.page(name)
            self.assertIn('class="table-wrap responsive"', html, name)
            cells = body_cells(html)
            self.assertTrue(cells, name)
            for cell in cells:
                self.assertRegex(cell, r'data-label="[^"]+"', name)

    def test_collection_template_cells_are_labelled(self):
        source = (TEMPLATES / "collections/collection_list.html").read_text(encoding="utf-8")
        self.assertIn('class="table-wrap responsive"', source)
        for cell in body_cells(source):
            self.assertRegex(cell, r'data-label="[^"]+"')

    def test_rows_have_one_tappable_primary_link(self):
        self.assertRegex(self.page("member_list"), r'<a class="row-link" href="/workspace/members/')
        self.assertRegex(self.page("finance_list"), r'<a class="row-link" href="/workspace/finance/')
        source = (TEMPLATES / "collections/collection_list.html").read_text(encoding="utf-8")
        self.assertIn('class="row-link"', source)

    def test_amounts_are_formatted(self):
        html = self.page("finance_list")
        self.assertIn("GHS" + NBSP + "1,234.50", html)
        self.assertNotIn("GHS 1234.50", html)

    def test_payment_form_has_prompts_and_empty_amount_paid(self):
        html = self.page("finance_create")
        self.assertNotIn("---------", html)
        self.assertIn("Choose a member", html)
        self.assertIn("Choose a record type", html)
        paid = re.search(r'<input[^>]*name="paid_amount"[^>]*>', html).group(0)
        self.assertNotIn("value=", paid)

    def test_empty_amount_paid_saves_as_zero_for_pending(self):
        response = self.client.post(reverse("finance_create"), {
            "record_type": "due", "member": str(self.member.pk), "amount": "50", "paid_amount": "",
            "payment_method": "cash", "status": "pending", "payment_date": "2026-09-11",
            "reference_number": "", "notes": ""})
        created = FinancialRecord.objects.exclude(pk=self.record.pk).get()
        self.assertRedirects(response, reverse("finance_detail", args=[created.pk]))
        self.assertEqual(created.paid_amount, Decimal("0.00"))

    def test_empty_amount_paid_still_blocks_paid_status(self):
        response = self.client.post(reverse("finance_create"), {
            "record_type": "due", "member": str(self.member.pk), "amount": "50", "paid_amount": "",
            "payment_method": "cash", "status": "paid", "payment_date": "2026-09-11",
            "reference_number": "", "notes": ""})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(FinancialRecord.objects.count(), 1)


class StylesheetTests(TestCase):
    def css(self):
        return CSS.read_text(encoding="utf-8")

    def test_no_text_below_12px_and_16px_base(self):
        sizes = [float(v) for v in re.findall(r"font-size:\s*(\d+(?:\.\d+)?)px", self.css())]
        self.assertTrue(sizes)
        self.assertEqual([s for s in sizes if s < 12], [])
        self.assertRegex(self.css(), r"html\{[^}]*font-size:16px")

    def test_phone_card_layout_and_stretched_row_link(self):
        css = self.css()
        self.assertIn(".table-wrap.responsive td::before", css)
        self.assertIn("attr(data-label)", css)
        self.assertIn(".row-link::after", css)
        self.assertIn(".money{", css)
