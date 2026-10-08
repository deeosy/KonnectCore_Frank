"""Phase 2 of Kennedy's feedback (item 8): group selection on collections."""
from datetime import date

from django.urls import reverse

from apps.groups.models import GroupMemberAssignment, StructureUnit

from .models import CollectionRecord
from .tests import CollectionFixture


class CollectionGroupFilterTests(CollectionFixture):
    def setUp(self):
        super().setUp()
        self.region = StructureUnit.objects.create(organisation=self.alpha, name="North", unit_type=StructureUnit.Type.REGION)
        self.group = StructureUnit.objects.create(organisation=self.alpha, name="Tamale Growers", unit_type=StructureUnit.Type.GROUP, parent=self.region)
        self.other_group = StructureUnit.objects.create(organisation=self.alpha, name="Yendi Growers", unit_type=StructureUnit.Type.GROUP)
        self.beta_group = StructureUnit.objects.create(organisation=self.beta, name="Nakuru Growers", unit_type=StructureUnit.Type.GROUP)
        GroupMemberAssignment.objects.create(organisation=self.alpha, unit=self.group, member=self.alpha_member)
        GroupMemberAssignment.objects.create(organisation=self.alpha, unit=self.other_group, member=self.alpha_member_two)
        self.two_record = self.record(
            self.alpha, self.alpha_member_two, self.cocoa, self.admin, "4", "2", date(2026, 9, 12), "Yendi depot"
        )

    def listed(self, **params):
        self.login_as(self.admin)
        response = self.client.get(reverse("collection_list"), params)
        self.assertEqual(response.status_code, 200)
        return response, {r.pk for r in response.context["records"]}

    def create_url(self, group):
        return f"{reverse('collection_create')}?group={group.pk}"

    def test_list_filters_by_group(self):
        response, ids = self.listed(group=str(self.group.pk))
        self.assertEqual(ids, {self.alpha_record.pk})
        self.assertContains(response, f'<option value="{self.group.pk}" selected>')

    def test_parent_unit_includes_child_unit_members(self):
        _, ids = self.listed(group=str(self.region.pk))
        self.assertEqual(ids, {self.alpha_record.pk})

    def test_other_organisation_group_is_ignored(self):
        response, ids = self.listed(group=str(self.beta_group.pk))
        self.assertEqual(ids, {self.alpha_record.pk, self.two_record.pk})
        self.assertNotContains(response, "Nakuru Growers")

    def test_invalid_group_value_is_ignored(self):
        _, ids = self.listed(group="not-a-uuid")
        self.assertEqual(ids, {self.alpha_record.pk, self.two_record.pk})

    def test_record_form_member_picker_narrowed_by_group(self):
        self.login_as(self.admin)
        response = self.client.get(self.create_url(self.group))
        self.assertEqual(response.status_code, 200)
        members = set(response.context["form"].fields["member"].queryset)
        self.assertEqual(members, {self.alpha_member})

    def test_record_form_without_group_lists_all_members(self):
        self.login_as(self.admin)
        response = self.client.get(reverse("collection_create"))
        members = set(response.context["form"].fields["member"].queryset)
        self.assertEqual(members, {self.alpha_member, self.alpha_member_two})
        self.assertContains(response, "Show members")

    def test_save_rejects_member_outside_selected_group(self):
        self.login_as(self.admin)
        before = CollectionRecord.objects.count()
        response = self.client.post(self.create_url(self.group), self.payload(member=str(self.alpha_member_two.pk)))
        self.assertEqual(response.status_code, 200)
        self.assertIn("member", response.context["form"].errors)
        self.assertEqual(CollectionRecord.objects.count(), before)

    def test_save_accepts_member_in_selected_group(self):
        self.login_as(self.admin)
        before = CollectionRecord.objects.count()
        response = self.client.post(self.create_url(self.group), self.payload(member=str(self.alpha_member.pk)))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(CollectionRecord.objects.count(), before + 1)
