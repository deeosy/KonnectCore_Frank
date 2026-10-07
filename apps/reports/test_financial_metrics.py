"""Dashboard and export finance figures (UAT I-6).

Definitions under test:
- ``amount`` is the amount owed or scheduled; ``paid_amount`` is money actually paid.
- Outgoing records: "Payment to member" and organisation expenses.
- Incoming records: dues, contributions and savings paid by members.
- Cancelled records owe nothing.

Expected totals below are worked out by hand from the fixture, not from the code.
"""
import csv
import io
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.finance.models import FinancialRecord
from apps.members.models import Member
from apps.organisations.middleware import ActiveOrganisationMiddleware
from apps.organisations.models import Organisation, OrganisationMembership

User = get_user_model()


class FinancialMetricTests(TestCase):
    def setUp(self):
        self.org = Organisation.objects.create(name="Metrics Org", slug="metrics-org", currency="GHS")
        self.other = Organisation.objects.create(name="Other Org", slug="metrics-other", currency="GHS")
        self.admin = User.objects.create_user(email="admin@metrics.test", password="x")
        self.other_admin = User.objects.create_user(email="admin@other.test", password="x")
        OrganisationMembership.objects.create(organisation=self.org, user=self.admin, role="admin")
        OrganisationMembership.objects.create(organisation=self.other, user=self.other_admin, role="admin")
        self.member = Member.objects.create(
            organisation=self.org, created_by=self.admin, updated_by=self.admin,
            membership_number="M1", first_name="Mia", last_name="Metric",
        )
        foreign_member = Member.objects.create(
            organisation=self.other, created_by=self.other_admin, updated_by=self.other_admin,
            membership_number="X1", first_name="Xan", last_name="Other",
        )
        rows = [
            # (type, status, amount, paid)
            ("member_payment", "paid", "500", "500"),
            ("member_payment", "part_paid", "1000", "400"),
            ("member_payment", "pending", "300", "0"),
            ("member_payment", "cancelled", "200", "0"),
            ("due", "part_paid", "100", "25"),
            ("contribution", "pending", "80", "0"),
            ("saving", "paid", "60", "60"),
        ]
        for record_type, status, amount, paid in rows:
            self.record(self.org, self.member, self.admin, record_type, status, amount, paid)
        self.record(self.org, None, self.admin, "expense", "paid", "700", "700")
        # Another organisation's record must never be counted.
        self.record(self.other, foreign_member, self.other_admin, "member_payment", "pending", "999", "0")

    def record(self, org, member, user, record_type, status, amount, paid):
        return FinancialRecord.objects.create(
            organisation=org, member=member, record_type=record_type, status=status,
            amount=Decimal(amount), paid_amount=Decimal(paid), payment_method="cash",
            payment_date=date(2026, 9, 1), recorded_by=user,
        )

    def login(self):
        self.client.force_login(self.admin)
        session = self.client.session
        session[ActiveOrganisationMiddleware.SESSION_KEY] = self.org.pk
        session.save()

    EXPECTED = {
        "paid_to_members": Decimal("900.00"),       # 500 + 400
        "owed_to_members": Decimal("900.00"),       # 600 + 300; cancelled owes nothing
        "received_from_members": Decimal("85.00"),  # 25 + 60
        "owed_by_members": Decimal("155.00"),       # 75 + 80
        "expenses_paid": Decimal("700.00"),
    }

    def test_dashboard_separates_money_directions(self):
        self.login()
        response = self.client.get(reverse("dashboard"))
        metrics = response.context["metrics"]
        for key, expected in self.EXPECTED.items():
            self.assertEqual(Decimal(metrics[key]), expected, key)

    def test_dashboard_labels_are_unambiguous(self):
        self.login()
        response = self.client.get(reverse("dashboard"))
        for label in ("Paid to members", "Owed to members", "Received from members", "Owed by members"):
            self.assertContains(response, label)
        self.assertNotContains(response, "Total Payments")

    def test_recent_payments_show_amount_actually_paid(self):
        self.login()
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "GHS\u00a0400.00 paid of GHS\u00a01,000.00")

    def test_finance_export_matches_dashboard_by_direction(self):
        self.login()
        response = self.client.get(reverse("export_report", args=["finance", "csv"]))
        rows = list(csv.DictReader(io.StringIO(response.content.decode())))
        self.assertIn("Direction", rows[0])
        self.assertEqual(len(rows), 8, "other organisation's record must be excluded")

        def total(direction, column, types=None):
            return sum(
                (Decimal(row[column]) for row in rows
                 if row["Direction"] == direction and (types is None or row["Type"] in types)),
                Decimal("0"),
            )

        to_member = {"Payment to member"}
        self.assertEqual(total("Outgoing", "Paid", to_member), self.EXPECTED["paid_to_members"])
        self.assertEqual(total("Outgoing", "Outstanding", to_member), self.EXPECTED["owed_to_members"])
        self.assertEqual(total("Incoming", "Paid"), self.EXPECTED["received_from_members"])
        self.assertEqual(total("Incoming", "Outstanding"), self.EXPECTED["owed_by_members"])
        self.assertEqual(total("Outgoing", "Paid", {"Organisation expense"}), self.EXPECTED["expenses_paid"])
