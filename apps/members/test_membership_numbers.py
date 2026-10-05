"""Regression tests for membership-number uniqueness (UAT issue I-3).

Rule: membership numbers are trimmed, and uniqueness within an organisation
is case-insensitive. Duplicates must produce a field error, never a crash.
"""
import io

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.groups.models import GroupMemberAssignment, StructureUnit

from .models import Member
from .services import import_members
from .tests import MemberFixture

DUPLICATE_MESSAGE = "already exists in this organisation"
REQUIRED_MESSAGE = "Membership number is required."


class MemberFormDuplicateTests(MemberFixture):
    def assert_rejected(self, response, before):
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, DUPLICATE_MESSAGE)
        # A filled-in duplicate must not also be reported as missing.
        self.assertNotContains(response, REQUIRED_MESSAGE)
        self.assertEqual(Member.objects.count(), before)

    def test_create_exact_duplicate_shows_field_error_and_keeps_input(self):
        self.login_as(self.alpha_admin, self.alpha)
        before = Member.objects.count()
        response = self.client.post(reverse("member_create"), self.member_payload("A-001", first_name="Kept"))
        self.assert_rejected(response, before)
        self.assertContains(response, 'value="Kept"')

    def test_create_case_and_space_variant_is_rejected(self):
        self.login_as(self.alpha_admin, self.alpha)
        before = Member.objects.count()
        response = self.client.post(reverse("member_create"), self.member_payload("  a-001 "))
        self.assert_rejected(response, before)

    def test_same_number_allowed_in_other_organisation(self):
        self.login_as(self.beta_admin, self.beta)
        response = self.client.post(reverse("member_create"), self.member_payload("A-001"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Member.objects.filter(organisation=self.beta, membership_number="A-001").exists())

    def test_edit_to_existing_number_is_rejected(self):
        other = self.make_member(self.alpha, self.alpha_admin, "A-009", "Kofi", "Boateng")
        self.login_as(self.alpha_admin, self.alpha)
        response = self.client.post(reverse("member_edit", args=[other.pk]), self.member_payload("a-001"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, DUPLICATE_MESSAGE)
        self.assertNotContains(response, REQUIRED_MESSAGE)
        other.refresh_from_db()
        self.assertEqual(other.membership_number, "A-009")

    def test_edit_keeping_own_number_is_allowed(self):
        self.login_as(self.alpha_admin, self.alpha)
        response = self.client.post(
            reverse("member_edit", args=[self.alpha_member.pk]),
            self.member_payload("A-001", first_name="Ama", last_name="Mensah"),
        )
        self.assertEqual(response.status_code, 302)

    def test_create_stores_trimmed_number(self):
        self.login_as(self.alpha_admin, self.alpha)
        self.client.post(reverse("member_create"), self.member_payload("  A-050  "))
        self.assertTrue(Member.objects.filter(organisation=self.alpha, membership_number="A-050").exists())

    def test_field_registration_duplicate_shows_field_error(self):
        self.login_as(self.alpha_field, self.alpha)
        before = Member.objects.count()
        response = self.client.post(reverse("field_member_create"), self.member_payload("A-001"))
        self.assert_rejected(response, before)

    def test_blank_number_still_reports_required(self):
        self.login_as(self.alpha_admin, self.alpha)
        before = Member.objects.count()
        response = self.client.post(reverse("member_create"), self.member_payload("   "))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Member.objects.count(), before)
        self.assertTrue(response.context["form"].errors.get("membership_number"))

    def test_model_full_clean_still_requires_number(self):
        member = Member(
            organisation=self.alpha, first_name="Blank", last_name="Number",
            membership_number="   ", created_by=self.alpha_admin, updated_by=self.alpha_admin,
        )
        with self.assertRaises(ValidationError) as ctx:
            member.full_clean()
        self.assertIn("membership_number", ctx.exception.message_dict)


class MemberImportDuplicateTests(MemberFixture):
    def csv_file(self, numbers):
        lines = ["first_name,last_name,membership_number"]
        lines += [f"Person{i},Test,{number}" for i, number in enumerate(numbers)]
        return SimpleUploadedFile("members.csv", ("\n".join(lines) + "\n").encode(), content_type="text/csv")

    def test_import_rejects_case_variant_of_existing_number(self):
        before = Member.objects.count()
        with self.assertRaises(ValidationError) as ctx:
            import_members(self.csv_file(["a-001"]), self.alpha, self.alpha_admin)
        self.assertIn("already exists", " ".join(ctx.exception.messages))
        self.assertEqual(Member.objects.count(), before)

    def test_import_rejects_case_variant_duplicates_within_file(self):
        before = Member.objects.count()
        with self.assertRaises(ValidationError):
            import_members(self.csv_file(["X-1", "x-1"]), self.alpha, self.alpha_admin)
        self.assertEqual(Member.objects.count(), before)

    def test_import_allows_number_used_by_other_organisation(self):
        created = import_members(self.csv_file(["B-001"]), self.alpha, self.alpha_admin)
        self.assertEqual(len(created), 1)
