from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from apps.members.models import Member
from apps.organisations.middleware import ActiveOrganisationMiddleware
from apps.organisations.models import Organisation, OrganisationMembership

from .forms import GroupMemberAssignmentForm, StructureUnitForm
from .models import GroupMemberAssignment, StructureUnit

User = get_user_model()


class StructureFixture(TestCase):
    def setUp(self):
        self.alpha = Organisation.objects.create(name="Alpha Cooperative", slug="alpha", currency="GHS")
        self.beta = Organisation.objects.create(name="Beta Farmers", slug="beta", currency="KES")
        self.alpha_admin = User.objects.create_user(email="admin@alpha.test", password="StrongPass!42")
        self.alpha_manager = User.objects.create_user(email="manager@alpha.test", password="StrongPass!42")
        self.alpha_field_user = User.objects.create_user(email="field@alpha.test", password="StrongPass!42")
        self.beta_admin = User.objects.create_user(email="admin@beta.test", password="StrongPass!42")
        self.beta_field_user = User.objects.create_user(email="field@beta.test", password="StrongPass!42")
        self.alpha_admin_membership = self.membership(self.alpha, self.alpha_admin, OrganisationMembership.Role.ADMIN)
        self.alpha_manager_membership = self.membership(self.alpha, self.alpha_manager, OrganisationMembership.Role.MANAGER)
        self.alpha_field = self.membership(self.alpha, self.alpha_field_user, OrganisationMembership.Role.FIELD_OFFICER)
        self.beta_admin_membership = self.membership(self.beta, self.beta_admin, OrganisationMembership.Role.ADMIN)
        self.beta_field = self.membership(self.beta, self.beta_field_user, OrganisationMembership.Role.FIELD_OFFICER)
        self.alpha_member = self.member(self.alpha, self.alpha_admin, "A-001", "Ama", "Mensah")
        self.alpha_member_two = self.member(self.alpha, self.alpha_admin, "A-002", "Kojo", "Asare")
        self.beta_member = self.member(self.beta, self.beta_admin, "B-001", "Ben", "Otieno")
        self.alpha_region = StructureUnit.objects.create(
            organisation=self.alpha,
            name="Northern Region",
            unit_type=StructureUnit.Type.REGION,
            leader=self.alpha_member,
            field_officer=self.alpha_field,
        )
        self.alpha_group = StructureUnit.objects.create(
            organisation=self.alpha,
            name="Tamale Growers",
            unit_type=StructureUnit.Type.GROUP,
            parent=self.alpha_region,
        )
        self.beta_group = StructureUnit.objects.create(
            organisation=self.beta,
            name="Nakuru Growers",
            unit_type=StructureUnit.Type.GROUP,
            leader=self.beta_member,
            field_officer=self.beta_field,
        )

    def membership(self, organisation, user, role):
        return OrganisationMembership.objects.create(organisation=organisation, user=user, role=role)

    def member(self, organisation, actor, number, first, last):
        return Member.objects.create(
            organisation=organisation,
            created_by=actor,
            updated_by=actor,
            membership_number=number,
            first_name=first,
            last_name=last,
        )

    def login_as(self, user, organisation):
        self.client.force_login(user)
        session = self.client.session
        session[ActiveOrganisationMiddleware.SESSION_KEY] = organisation.pk
        session.save()

    def unit_payload(self, **overrides):
        data = {
            "name": "Central District",
            "unit_type": StructureUnit.Type.DISTRICT,
            "parent": str(self.alpha_region.pk),
            "leader": str(self.alpha_member.pk),
            "field_officer": str(self.alpha_field.pk),
            "description": "District structure",
            "is_active": "on",
        }
        data.update(overrides)
        return data


class StructureIsolationTests(StructureFixture):
    def test_list_search_and_detail_never_leak_other_tenant(self):
        self.login_as(self.alpha_admin, self.alpha)
        response = self.client.get(reverse("structure_list"))
        self.assertContains(response, "Northern Region")
        self.assertContains(response, "Tamale Growers")
        self.assertNotContains(response, "Nakuru Growers")
        response = self.client.get(reverse("structure_list"), {"q": "Nakuru"})
        self.assertNotContains(response, "Nakuru Growers")
        self.assertContains(response, "No structure units match")
        self.assertEqual(self.client.get(reverse("structure_detail", args=[self.beta_group.pk])).status_code, 404)

    def test_guessed_cross_tenant_unit_cannot_be_edited_or_assigned(self):
        self.login_as(self.alpha_admin, self.alpha)
        self.assertEqual(self.client.get(reverse("structure_edit", args=[self.beta_group.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("assignment_add", args=[self.beta_group.pk])).status_code, 404)

    def test_form_querysets_contain_only_current_tenant_records(self):
        form = StructureUnitForm(organisation=self.alpha)
        self.assertQuerySetEqual(form.fields["parent"].queryset.order_by("name"), [self.alpha_region, self.alpha_group], transform=lambda item: item)
        self.assertIn(self.alpha_member, form.fields["leader"].queryset)
        self.assertNotIn(self.beta_member, form.fields["leader"].queryset)
        self.assertIn(self.alpha_field, form.fields["field_officer"].queryset)
        self.assertNotIn(self.beta_field, form.fields["field_officer"].queryset)

    def test_cross_tenant_parent_leader_and_officer_are_rejected(self):
        unit = StructureUnit(
            organisation=self.alpha,
            name="Invalid",
            unit_type=StructureUnit.Type.GROUP,
            parent=self.beta_group,
            leader=self.beta_member,
            field_officer=self.beta_field,
        )
        with self.assertRaises(ValidationError) as context:
            unit.full_clean()
        self.assertEqual(set(context.exception.message_dict), {"parent", "leader", "field_officer"})

    def test_cross_tenant_member_assignment_is_rejected(self):
        assignment = GroupMemberAssignment(
            organisation=self.alpha,
            unit=self.alpha_group,
            member=self.beta_member,
        )
        with self.assertRaises(ValidationError):
            assignment.full_clean()


class HierarchyValidationTests(StructureFixture):
    def test_direct_self_parent_is_rejected(self):
        self.alpha_region.parent = self.alpha_region
        with self.assertRaises(ValidationError):
            self.alpha_region.full_clean()

    def test_indirect_hierarchy_cycle_is_rejected(self):
        self.alpha_region.parent = self.alpha_group
        with self.assertRaises(ValidationError) as context:
            self.alpha_region.full_clean()
        self.assertIn("parent", context.exception.message_dict)

    def test_non_field_officer_membership_is_rejected(self):
        self.alpha_group.field_officer = self.alpha_manager_membership
        with self.assertRaises(ValidationError) as context:
            self.alpha_group.full_clean()
        self.assertIn("field_officer", context.exception.message_dict)

    def test_root_names_are_unique_per_organisation(self):
        StructureUnit.objects.create(organisation=self.beta, name="Northern Region", unit_type=StructureUnit.Type.REGION)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StructureUnit.objects.create(organisation=self.alpha, name="Northern Region", unit_type=StructureUnit.Type.DISTRICT)

    def test_sibling_names_are_unique_but_can_repeat_under_other_parent(self):
        StructureUnit.objects.create(organisation=self.alpha, name="Zone One", unit_type=StructureUnit.Type.GROUP, parent=self.alpha_region)
        other_region = StructureUnit.objects.create(organisation=self.alpha, name="Southern Region", unit_type=StructureUnit.Type.REGION)
        StructureUnit.objects.create(organisation=self.alpha, name="Zone One", unit_type=StructureUnit.Type.GROUP, parent=other_region)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StructureUnit.objects.create(organisation=self.alpha, name="Zone One", unit_type=StructureUnit.Type.COMMUNITY, parent=self.alpha_region)


class StructureRoleTests(StructureFixture):
    def test_operational_roles_view_structure_and_field_officer_is_redirected(self):
        for user in (self.alpha_admin, self.alpha_manager):
            self.client.logout()
            self.login_as(user, self.alpha)
            self.assertEqual(self.client.get(reverse("structure_list")).status_code, 200)
            self.assertEqual(self.client.get(reverse("structure_detail", args=[self.alpha_group.pk])).status_code, 200)
        self.client.logout()
        self.login_as(self.alpha_field_user, self.alpha)
        for url in (reverse("structure_list"), reverse("structure_detail", args=[self.alpha_group.pk])):
            self.assertRedirects(self.client.get(url), reverse("field_home"), fetch_redirect_response=False)

    def test_field_officer_cannot_mutate_structure(self):
        self.login_as(self.alpha_field_user, self.alpha)
        urls = [
            reverse("structure_create"),
            reverse("structure_edit", args=[self.alpha_group.pk]),
            reverse("assignment_add", args=[self.alpha_group.pk]),
        ]
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 403)

    def test_admin_and_manager_can_create_units(self):
        for index, user in enumerate((self.alpha_admin, self.alpha_manager), start=1):
            self.client.logout()
            self.login_as(user, self.alpha)
            payload = self.unit_payload(name=f"District {index}")
            response = self.client.post(reverse("structure_create"), payload)
            unit = StructureUnit.objects.get(organisation=self.alpha, name=f"District {index}")
            self.assertRedirects(response, reverse("structure_detail", args=[unit.pk]))
            self.assertEqual(unit.parent, self.alpha_region)
            self.assertEqual(unit.leader, self.alpha_member)
            self.assertEqual(unit.field_officer, self.alpha_field)


class AssignmentWorkflowTests(StructureFixture):
    def test_manager_assigns_and_removes_tenant_member(self):
        self.login_as(self.alpha_manager, self.alpha)
        response = self.client.post(
            reverse("assignment_add", args=[self.alpha_group.pk]),
            {"member": str(self.alpha_member_two.pk), "joined_at": "2026-09-11"},
        )
        assignment = GroupMemberAssignment.objects.get(unit=self.alpha_group, member=self.alpha_member_two)
        self.assertRedirects(response, reverse("structure_detail", args=[self.alpha_group.pk]))
        self.assertEqual(assignment.organisation, self.alpha)
        response = self.client.post(reverse("assignment_remove", args=[self.alpha_group.pk, assignment.pk]))
        self.assertRedirects(response, reverse("structure_detail", args=[self.alpha_group.pk]))
        self.assertFalse(GroupMemberAssignment.objects.filter(pk=assignment.pk).exists())

    def test_assignment_form_excludes_other_tenant_and_already_assigned_members(self):
        GroupMemberAssignment.objects.create(organisation=self.alpha, unit=self.alpha_group, member=self.alpha_member)
        form = GroupMemberAssignmentForm(organisation=self.alpha, unit=self.alpha_group)
        self.assertNotIn(self.alpha_member, form.fields["member"].queryset)
        self.assertIn(self.alpha_member_two, form.fields["member"].queryset)
        self.assertNotIn(self.beta_member, form.fields["member"].queryset)

    def test_duplicate_assignment_is_blocked(self):
        GroupMemberAssignment.objects.create(organisation=self.alpha, unit=self.alpha_group, member=self.alpha_member)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                GroupMemberAssignment.objects.create(organisation=self.alpha, unit=self.alpha_group, member=self.alpha_member)

    def test_cross_tenant_assignment_id_cannot_be_removed(self):
        beta_assignment = GroupMemberAssignment.objects.create(organisation=self.beta, unit=self.beta_group, member=self.beta_member)
        self.login_as(self.alpha_admin, self.alpha)
        response = self.client.post(reverse("assignment_remove", args=[self.alpha_group.pk, beta_assignment.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(GroupMemberAssignment.objects.filter(pk=beta_assignment.pk).exists())


class StructureFilterAndStatusTests(StructureFixture):
    def test_type_filter_is_tenant_scoped(self):
        self.login_as(self.alpha_admin, self.alpha)
        response = self.client.get(reverse("structure_list"), {"type": StructureUnit.Type.REGION})
        self.assertContains(response, "Northern Region")
        self.assertNotContains(response, "Tamale Growers")
        self.assertNotContains(response, "Nakuru Growers")

    def test_suspended_organisation_cannot_access_structure(self):
        self.alpha.status = Organisation.Status.SUSPENDED
        self.alpha.save(update_fields=["status"])
        self.login_as(self.alpha_admin, self.alpha)
        self.assertRedirects(self.client.get(reverse("structure_list")), reverse("choose_organisation"))
