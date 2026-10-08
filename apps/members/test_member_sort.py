"""Phase 2 of Kennedy's feedback (item 5): Sort by on the Members list."""
import datetime
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from apps.farms.models import Farm
from apps.farms.tests import FarmFixture
from apps.finance.models import FinancialRecord

from .models import Member

NUMBERS = ("S-1", "S-2", "S-3")


class MemberSortTests(FarmFixture):
    def setUp(self):
        super().setUp()
        self.ama = self.make_member("Ama", "S-1")
        self.kofi = self.make_member("Kofi", "S-2")
        self.yaw = self.make_member("Yaw", "S-3")
        now = timezone.now()
        Member.objects.filter(pk=self.ama.pk).update(created_at=now - datetime.timedelta(days=30))
        Member.objects.filter(pk=self.kofi.pk).update(created_at=now - datetime.timedelta(days=1))
        Member.objects.filter(pk=self.yaw.pk).update(created_at=now - datetime.timedelta(days=10))

    def make_member(self, first_name, number):
        return Member.objects.create(
            organisation=self.alpha, first_name=first_name, last_name="Sorter", membership_number=number,
            created_by=self.admin, updated_by=self.admin,
        )

    def record(self, member, record_type, amount, paid="0", status=FinancialRecord.Status.PENDING):
        return FinancialRecord.objects.create(
            organisation=self.alpha, member=member, record_type=record_type, amount=Decimal(amount),
            paid_amount=Decimal(paid), status=status, payment_method=FinancialRecord.Method.CASH,
            payment_date=datetime.date(2026, 10, 1), recorded_by=self.admin,
        )

    def order(self, sort=None):
        self.login_as(self.admin)
        params = {"sort": sort} if sort is not None else {}
        response = self.client.get(reverse("member_list"), params)
        self.assertEqual(response.status_code, 200)
        return [m.first_name for m in response.context["members"] if m.membership_number in NUMBERS]

    def test_default_is_name_order(self):
        self.assertEqual(self.order(), ["Ama", "Kofi", "Yaw"])

    def test_unknown_sort_falls_back_to_name(self):
        self.assertEqual(self.order("drop table"), ["Ama", "Kofi", "Yaw"])

    def test_date_joined_newest_first(self):
        self.assertEqual(self.order("joined"), ["Kofi", "Yaw", "Ama"])

    def test_farm_size_converts_acres_to_hectares(self):
        # 5 acres = about 2.02 ha, so it ranks below 3 ha but above 1 ha.
        Farm.objects.create(organisation=self.alpha, member=self.ama, name="A", size=Decimal("1"), size_unit=Farm.SizeUnit.HECTARES)
        Farm.objects.create(organisation=self.alpha, member=self.kofi, name="K", size=Decimal("5"), size_unit=Farm.SizeUnit.ACRES)
        Farm.objects.create(organisation=self.alpha, member=self.yaw, name="Y", size=Decimal("3"), size_unit=Farm.SizeUnit.HECTARES)
        self.assertEqual(self.order("farm_size"), ["Yaw", "Kofi", "Ama"])

    def test_farm_size_sums_several_farms_without_duplicate_rows(self):
        Farm.objects.create(organisation=self.alpha, member=self.ama, name="A1", size=Decimal("2"))
        Farm.objects.create(organisation=self.alpha, member=self.ama, name="A2", size=Decimal("2"))
        Farm.objects.create(organisation=self.alpha, member=self.yaw, name="Y", size=Decimal("3"))
        self.assertEqual(self.order("farm_size"), ["Ama", "Yaw", "Kofi"])

    def test_owed_to_member_uses_unpaid_member_payments(self):
        self.record(self.ama, FinancialRecord.Type.MEMBER_PAYMENT, "100", paid="90", status=FinancialRecord.Status.PART_PAID)
        self.record(self.yaw, FinancialRecord.Type.MEMBER_PAYMENT, "50")
        self.record(self.kofi, FinancialRecord.Type.MEMBER_PAYMENT, "999", status=FinancialRecord.Status.CANCELLED)
        self.record(self.kofi, FinancialRecord.Type.DUE, "500")
        self.assertEqual(self.order("owed_to_member"), ["Yaw", "Ama", "Kofi"])

    def test_owed_by_member_uses_unpaid_dues_and_contributions(self):
        self.record(self.kofi, FinancialRecord.Type.DUE, "40")
        self.record(self.kofi, FinancialRecord.Type.CONTRIBUTION, "40")
        self.record(self.ama, FinancialRecord.Type.DUE, "60")
        self.record(self.yaw, FinancialRecord.Type.DUE, "999", status=FinancialRecord.Status.CANCELLED)
        self.record(self.yaw, FinancialRecord.Type.MEMBER_PAYMENT, "700")
        self.assertEqual(self.order("owed_by_member"), ["Kofi", "Ama", "Yaw"])

    def test_dropdown_keeps_selected_sort(self):
        self.login_as(self.admin)
        response = self.client.get(reverse("member_list"), {"sort": "joined"})
        self.assertContains(response, 'name="sort"')
        self.assertContains(response, '<option value="joined" selected>')
        self.assertContains(response, "Clear")
