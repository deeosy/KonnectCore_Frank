"""Phase 2 of Kennedy's feedback (item 5): Sort by for members within a group."""
import datetime
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from apps.farms.models import Farm
from apps.farms.tests import FarmFixture
from apps.members.models import Member

from .models import GroupMemberAssignment, StructureUnit


class GroupMemberSortTests(FarmFixture):
    def setUp(self):
        super().setUp()
        self.group = StructureUnit.objects.create(organisation=self.alpha, name="Sort Growers", unit_type=StructureUnit.Type.GROUP)
        self.ama = self.make_member("Ama", "G-1")
        self.kofi = self.make_member("Kofi", "G-2")
        self.yaw = self.make_member("Yaw", "G-3")
        self.outsider = self.make_member("Zed", "G-9")
        now = timezone.now()
        for member, days in ((self.ama, 30), (self.kofi, 1), (self.yaw, 10)):
            Member.objects.filter(pk=member.pk).update(created_at=now - datetime.timedelta(days=days))
            GroupMemberAssignment.objects.create(organisation=self.alpha, unit=self.group, member=member)

    def make_member(self, first_name, number):
        return Member.objects.create(
            organisation=self.alpha, first_name=first_name, last_name="Grouped", membership_number=number,
            created_by=self.admin, updated_by=self.admin,
        )

    def get(self, sort=None):
        self.login_as(self.admin)
        params = {"sort": sort} if sort is not None else {}
        response = self.client.get(reverse("structure_detail", args=[self.group.pk]), params)
        self.assertEqual(response.status_code, 200)
        return response

    def order(self, sort=None):
        return [a.member.first_name for a in self.get(sort).context["assignments"]]

    def test_default_is_name_order_and_only_group_members(self):
        self.assertEqual(self.order(), ["Ama", "Kofi", "Yaw"])

    def test_unknown_sort_falls_back_to_name(self):
        self.assertEqual(self.order("nonsense"), ["Ama", "Kofi", "Yaw"])

    def test_date_joined_newest_first(self):
        self.assertEqual(self.order("joined"), ["Kofi", "Yaw", "Ama"])

    def test_farm_size_largest_first(self):
        Farm.objects.create(organisation=self.alpha, member=self.yaw, name="Y", size=Decimal("4"))
        Farm.objects.create(organisation=self.alpha, member=self.ama, name="A", size=Decimal("1"))
        Farm.objects.create(organisation=self.alpha, member=self.outsider, name="Z", size=Decimal("99"))
        self.assertEqual(self.order("farm_size"), ["Yaw", "Ama", "Kofi"])

    def test_dropdown_count_and_remove_form(self):
        response = self.get("joined")
        self.assertContains(response, '<option value="joined" selected>')
        self.assertContains(response, '<span class="status">3</span>')
        self.assertContains(response, ">Remove</button>", count=3)
