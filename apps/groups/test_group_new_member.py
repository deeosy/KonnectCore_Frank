"""Phase 3 of Kennedy's feedback (item 6): add a NEW member while setting up a group."""
from django.urls import reverse

from apps.farms.models import Farm, FarmCropSeason
from apps.farms.tests import FarmFixture
from apps.members.models import Member, MemberHistory

from .models import GroupMemberAssignment, StructureUnit


class NewMemberInGroupTests(FarmFixture):
    def setUp(self):
        super().setUp()
        self.group = StructureUnit.objects.create(organisation=self.alpha, name="Savelugu Growers", unit_type=StructureUnit.Type.GROUP)
        self.beta_group = StructureUnit.objects.create(organisation=self.beta, name="Nakuru Growers", unit_type=StructureUnit.Type.GROUP)
        self.url = reverse("assignment_new_member", args=[self.group.pk])

    def payload(self, number="A-G01", joined="2026-10-01", **farm):
        data = {
            "first_name": "Abena", "last_name": "Owusu", "phone": "+233200000077",
            "membership_number": number, "id_reference": "ID-77", "location": "Savelugu",
            "status": Member.Status.ACTIVE, "group-joined_at": joined,
        }
        data.update({f"farm-{key}": value for key, value in farm.items()})
        return data

    def new_member(self, number="A-G01"):
        return Member.objects.filter(organisation=self.alpha, membership_number=number).first()

    def test_admin_and_manager_see_the_form(self):
        for user in (self.admin, self.manager):
            self.client.logout()
            self.login_as(user)
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Add new member to Savelugu Growers")
            for text in ("Member information", "Farm details", 'id="id_group-joined_at"', "Save and add another"):
                self.assertContains(response, text)

    def test_field_officer_is_refused_and_signed_out_user_redirected(self):
        self.login_as(self.field)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, self.payload()).status_code, 403)
        self.assertIsNone(self.new_member())
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])

    def test_creates_member_and_assigns_to_group_in_one_step(self):
        self.login_as(self.manager)
        response = self.client.post(self.url, self.payload())
        member = self.new_member()
        self.assertIsNotNone(member)
        self.assertRedirects(response, reverse("structure_detail", args=[self.group.pk]))
        assignment = GroupMemberAssignment.objects.get(unit=self.group, member=member)
        self.assertEqual(assignment.organisation, self.alpha)
        self.assertEqual(str(assignment.joined_at), "2026-10-01")
        self.assertEqual(member.organisation, self.alpha)
        self.assertEqual(member.created_by, self.manager)
        self.assertFalse(Farm.objects.filter(member=member).exists())
        self.assertEqual(MemberHistory.objects.filter(member=member, action=MemberHistory.Action.CREATED).count(), 1)

    def test_joined_date_is_optional(self):
        self.login_as(self.admin)
        self.client.post(self.url, self.payload(joined=""))
        self.assertIsNone(GroupMemberAssignment.objects.get(unit=self.group, member=self.new_member()).joined_at)

    def test_farm_and_crops_are_saved_with_the_member(self):
        self.login_as(self.admin)
        self.client.post(self.url, self.payload(location="Savelugu", crops=[str(self.maize.pk)], season="2026 major"))
        member = self.new_member()
        farm = Farm.objects.get(member=member)
        self.assertEqual(farm.name, "Main farm")
        self.assertEqual(list(FarmCropSeason.objects.filter(farm=farm).values_list("crop__name", flat=True)), ["Maize"])
        self.assertTrue(GroupMemberAssignment.objects.filter(unit=self.group, member=member).exists())

    def test_save_and_add_another_returns_to_the_form(self):
        self.login_as(self.admin)
        data = self.payload()
        data["next"] = "another"
        response = self.client.post(self.url, data)
        self.assertRedirects(response, self.url)
        self.assertTrue(GroupMemberAssignment.objects.filter(unit=self.group, member=self.new_member()).exists())

    def test_duplicate_membership_number_saves_nothing(self):
        self.login_as(self.admin)
        response = self.client.post(self.url, self.payload(number="A-F01"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists")
        self.assertEqual(Member.objects.filter(organisation=self.alpha, membership_number="A-F01").count(), 1)
        self.assertFalse(GroupMemberAssignment.objects.filter(unit=self.group).exists())

    def test_invalid_farm_part_saves_no_member_and_no_assignment(self):
        self.login_as(self.admin)
        response = self.client.post(self.url, self.payload(crops=[str(self.maize.pk)]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter the season for the selected crops.")
        self.assertIsNone(self.new_member())
        self.assertFalse(GroupMemberAssignment.objects.filter(unit=self.group).exists())

    def test_other_organisations_group_is_not_found(self):
        self.login_as(self.admin)
        url = reverse("assignment_new_member", args=[self.beta_group.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, self.payload()).status_code, 404)
        self.assertIsNone(self.new_member())
        self.assertFalse(GroupMemberAssignment.objects.filter(unit=self.beta_group).exists())

    def test_other_organisations_crops_are_not_offered(self):
        self.login_as(self.admin)
        response = self.client.get(self.url)
        self.assertContains(response, "Maize")
        self.assertNotContains(response, "Coffee")

    def test_group_page_links_to_new_member_for_managers_only(self):
        detail = reverse("structure_detail", args=[self.group.pk])
        self.login_as(self.manager)
        self.assertContains(self.client.get(detail), f'href="{self.url}"')

    def test_create_group_save_and_add_members_goes_to_new_member_page(self):
        self.login_as(self.manager)
        data = {"name": "Tolon Growers", "unit_type": StructureUnit.Type.GROUP, "is_active": "on", "next": "members"}
        response = self.client.post(reverse("structure_create"), data)
        unit = StructureUnit.objects.get(organisation=self.alpha, name="Tolon Growers")
        self.assertRedirects(response, reverse("assignment_new_member", args=[unit.pk]))
        data.pop("next")
        data["name"] = "Kumbungu Growers"
        response = self.client.post(reverse("structure_create"), data)
        unit = StructureUnit.objects.get(organisation=self.alpha, name="Kumbungu Growers")
        self.assertRedirects(response, reverse("structure_detail", args=[unit.pk]))

    def test_save_and_add_members_button_only_on_create(self):
        self.login_as(self.admin)
        self.assertContains(self.client.get(reverse("structure_create")), "Save and add members")
        self.assertNotContains(self.client.get(reverse("structure_edit", args=[self.group.pk])), "Save and add members")