from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.groups.models import GroupMemberAssignment, StructureUnit
from apps.members.models import Member
from apps.organisations.middleware import ActiveOrganisationMiddleware
from apps.organisations.models import Organisation, OrganisationMembership

from .models import InputAllocation
from .services import build_distribution_audit

User = get_user_model()


class InputFixture(TestCase):
    def setUp(self):
        self.alpha = Organisation.objects.create(name="Alpha Inputs", slug="alpha-inputs", currency="GHS")
        self.beta = Organisation.objects.create(name="Beta Inputs", slug="beta-inputs", currency="KES")

        self.admin = self.create_user("admin@inputs.test", self.alpha, OrganisationMembership.Role.ADMIN)
        self.manager = self.create_user("manager@inputs.test", self.alpha, OrganisationMembership.Role.MANAGER)
        self.officer = self.create_user("officer@inputs.test", self.alpha, OrganisationMembership.Role.FIELD_OFFICER)
        self.beta_admin = self.create_user("admin@beta-inputs.test", self.beta, OrganisationMembership.Role.ADMIN)

        self.assigned_member = self.create_member(self.alpha, self.admin, "A-001", "Ama", "Assigned")
        self.unassigned_member = self.create_member(self.alpha, self.admin, "A-002", "Kojo", "Unassigned")
        self.beta_member = self.create_member(self.beta, self.beta_admin, "B-001", "Beta", "Farmer")

        officer_membership = OrganisationMembership.objects.get(user=self.officer, organisation=self.alpha)
        self.region = StructureUnit.objects.create(
            organisation=self.alpha,
            name="Northern",
            unit_type=StructureUnit.Type.REGION,
        )
        self.other_region = StructureUnit.objects.create(
            organisation=self.alpha,
            name="Savannah",
            unit_type=StructureUnit.Type.REGION,
        )
        self.group = StructureUnit.objects.create(
            organisation=self.alpha,
            name="Tamale A",
            unit_type=StructureUnit.Type.GROUP,
            parent=self.region,
            field_officer=officer_membership,
        )
        self.other_group = StructureUnit.objects.create(
            organisation=self.alpha,
            name="Tamale B",
            unit_type=StructureUnit.Type.GROUP,
            parent=self.other_region,
        )
        GroupMemberAssignment.objects.create(
            organisation=self.alpha, unit=self.group, member=self.assigned_member
        )
        GroupMemberAssignment.objects.create(
            organisation=self.alpha, unit=self.other_group, member=self.unassigned_member
        )

        self.admin_allocation = self.create_allocation(
            self.alpha, self.assigned_member, InputAllocation.Status.DELIVERED, "120.00"
        )
        self.manager_allocation = self.create_allocation(
            self.alpha, self.unassigned_member, InputAllocation.Status.VERIFIED, "80.00"
        )
        self.beta_allocation = self.create_allocation(
            self.beta, self.beta_member, InputAllocation.Status.DELIVERED, "999.00"
        )

    @staticmethod
    def create_user(email, organisation, role):
        user = User.objects.create_user(email=email, password="test-password")
        OrganisationMembership.objects.create(organisation=organisation, user=user, role=role)
        return user

    @staticmethod
    def create_member(organisation, actor, number, first, last):
        return Member.objects.create(
            organisation=organisation,
            created_by=actor,
            updated_by=actor,
            membership_number=number,
            first_name=first,
            last_name=last,
        )

    @staticmethod
    def create_allocation(organisation, member, status, quantity):
        return InputAllocation.objects.create(
            organisation=organisation,
            member=member,
            input_type=InputAllocation.InputType.NPK,
            quantity=Decimal(quantity),
            status=status,
        )

    def login(self, user, organisation=None):
        self.client.force_login(user)
        session = self.client.session
        session[ActiveOrganisationMiddleware.SESSION_KEY] = (organisation or self.alpha).pk
        session.save()


class InputAllocationModelTests(InputFixture):
    def test_allocation_rejects_cross_tenant_member(self):
        allocation = InputAllocation(
            organisation=self.alpha,
            member=self.beta_member,
            input_type=InputAllocation.InputType.ORGANIC,
            quantity=Decimal("10.00"),
        )
        with self.assertRaises(ValidationError) as context:
            allocation.full_clean()
        self.assertIn("member", context.exception.message_dict)

    def test_allocation_rejects_zero_and_negative_quantity(self):
        for quantity in ("0.00", "-5.00"):
            allocation = InputAllocation(
                organisation=self.alpha,
                member=self.assigned_member,
                input_type=InputAllocation.InputType.NPK,
                quantity=Decimal(quantity),
            )
            with self.assertRaises(ValidationError) as context:
                allocation.full_clean()
            self.assertIn("quantity", context.exception.message_dict)

    def test_allocation_accepts_valid_data(self):
        allocation = InputAllocation(
            organisation=self.alpha,
            member=self.assigned_member,
            input_type=InputAllocation.InputType.NPK,
            quantity=Decimal("25.00"),
        )
        allocation.full_clean()
        allocation.save()
        self.assertEqual(allocation.status, InputAllocation.Status.REQUESTED)
        self.assertEqual(allocation.get_input_type_display(), "NPK")


class InputAllocationAccessTests(InputFixture):
    def test_field_officer_list_only_shows_assigned_members(self):
        self.login(self.officer)
        response = self.client.get(reverse("input_allocation_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ama Assigned")
        self.assertNotContains(response, "Kojo Unassigned")
        self.assertNotContains(response, "Beta Farmer")

    def test_field_officer_cannot_open_unassigned_allocation(self):
        self.login(self.officer)
        response = self.client.get(
            reverse("input_allocation_detail", args=[self.manager_allocation.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_field_officer_cannot_open_another_tenant_allocation(self):
        self.login(self.officer)
        response = self.client.get(
            reverse("input_allocation_detail", args=[self.beta_allocation.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_field_officer_form_only_offers_assigned_members(self):
        self.login(self.officer)
        response = self.client.get(reverse("input_allocation_create"))
        self.assertEqual(response.status_code, 200)
        member_ids = {str(member.pk) for member in response.context["form"].fields["member"].queryset}
        self.assertEqual(member_ids, {str(self.assigned_member.pk)})

    def test_field_officer_can_request_input_for_assigned_member(self):
        self.login(self.officer)
        response = self.client.post(
            reverse("input_allocation_create"),
            {
                "member": str(self.assigned_member.pk),
                "input_type": InputAllocation.InputType.ORGANIC,
                "quantity": "40.00",
            },
        )
        self.assertRedirects(response, reverse("input_allocation_list"))
        allocation = InputAllocation.objects.get(member=self.assigned_member, input_type="organic")
        self.assertEqual(allocation.organisation, self.alpha)
        self.assertEqual(allocation.status, InputAllocation.Status.REQUESTED)
        self.assertIsNone(allocation.verified_by)

    def test_field_officer_cannot_request_input_for_unassigned_member(self):
        self.login(self.officer)
        response = self.client.post(
            reverse("input_allocation_create"),
            {
                "member": str(self.unassigned_member.pk),
                "input_type": InputAllocation.InputType.NPK,
                "quantity": "15.00",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("member", response.context["form"].errors)
        self.assertFalse(
            InputAllocation.objects.filter(
                member=self.unassigned_member, quantity=Decimal("15.00")
            ).exists()
        )

    def test_field_officer_cannot_update_allocation_status(self):
        self.login(self.officer)
        response = self.client.post(
            reverse("input_allocation_detail", args=[self.admin_allocation.pk]),
            {"status": InputAllocation.Status.REJECTED},
        )
        self.assertEqual(response.status_code, 200)
        self.admin_allocation.refresh_from_db()
        self.assertEqual(self.admin_allocation.status, InputAllocation.Status.DELIVERED)

    def test_manager_can_update_status_and_records_verifier(self):
        self.login(self.manager)
        response = self.client.post(
            reverse("input_allocation_detail", args=[self.admin_allocation.pk]),
            {"status": InputAllocation.Status.PARTIALLY_DELIVERED},
        )
        self.assertRedirects(
            response, reverse("input_allocation_detail", args=[self.admin_allocation.pk])
        )
        self.admin_allocation.refresh_from_db()
        self.assertEqual(self.admin_allocation.status, InputAllocation.Status.PARTIALLY_DELIVERED)
        self.assertEqual(self.admin_allocation.verified_by, self.manager)

    def test_manager_sees_all_allocations_but_not_other_tenants(self):
        self.login(self.manager)
        response = self.client.get(reverse("input_allocation_list"))
        self.assertContains(response, "Ama Assigned")
        self.assertContains(response, "Kojo Unassigned")
        self.assertNotContains(response, "Beta Farmer")


class DistributionAuditTests(InputFixture):
    def test_audit_groups_allocations_by_region_and_group(self):
        audit = build_distribution_audit(self.alpha)

        self.assertTrue(audit["has_data"])
        self.assertEqual(audit["totals"]["total"], 2)
        self.assertEqual(audit["totals"]["delivered"], 1)
        self.assertEqual(audit["totals"]["verified"], 1)
        self.assertEqual(audit["totals"]["quantity"], Decimal("200.00"))
        self.assertEqual(audit["totals"]["delivered_quantity"], Decimal("120.00"))

        rows = {(row["region"], row["group"]): row for row in audit["rows"]}
        northern = rows[("Northern", "Tamale A")]
        self.assertEqual(northern["total"], 1)
        self.assertEqual(northern["delivered"], 1)
        self.assertEqual(northern["quantity"], Decimal("120.00"))

        savannah = rows[("Savannah", "Tamale B")]
        self.assertEqual(savannah["total"], 1)
        self.assertEqual(savannah["verified"], 1)

        region_rows = {row["region"]: row for row in audit["region_rows"]}
        self.assertEqual(region_rows["Northern"]["delivered"], 1)
        self.assertEqual(region_rows["Savannah"]["verified"], 1)

    def test_audit_is_tenant_isolated(self):
        audit = build_distribution_audit(self.alpha)
        self.assertEqual(audit["totals"]["total"], 2)
        self.assertNotIn("Nakuru", {row["region"] for row in audit["rows"]})

        beta_audit = build_distribution_audit(self.beta)
        self.assertEqual(beta_audit["totals"]["total"], 1)
        self.assertEqual(beta_audit["totals"]["quantity"], Decimal("999.00"))

    def test_audit_marks_members_without_a_group_as_unassigned(self):
        member = self.create_member(self.alpha, self.admin, "A-003", "Adwoa", "Loose")
        self.create_allocation(self.alpha, member, InputAllocation.Status.REQUESTED, "5.00")

        audit = build_distribution_audit(self.alpha)
        self.assertIn(
            ("Unassigned", "No group"),
            {(row["region"], row["group"]) for row in audit["rows"]},
        )

    def test_field_officer_cannot_open_distribution_audit(self):
        self.login(self.officer)
        response = self.client.get(reverse("input_distribution_audit"))
        self.assertEqual(response.status_code, 403)

    def test_manager_sees_distribution_audit_totals(self):
        self.login(self.manager)
        response = self.client.get(reverse("input_distribution_audit"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Northern")
        self.assertContains(response, "Tamale A")
        self.assertNotContains(response, "Nakuru")

    def test_distribution_audit_export_csv(self):
        self.login(self.manager)
        response = self.client.get(reverse("export_report", args=["distribution_audit", "csv"]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        content = response.content.decode()
        lines = content.strip().splitlines()
        self.assertEqual(
            lines[0],
            "Region,Group,Total allocations,Requested,Verified,Partially delivered,"
            "Delivered,Rejected,Quantity allocated,Quantity delivered",
        )
        self.assertIn("Northern,Tamale A,1,0,0,0,1,0,120.00,120.00", content)
        self.assertNotIn("999.00", content)

    def test_export_rejects_unknown_report(self):
        self.login(self.manager)
        response = self.client.get(reverse("export_report", args=["unknown", "csv"]))
        self.assertEqual(response.status_code, 404)
