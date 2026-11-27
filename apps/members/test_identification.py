"""Tests for Ghana identification formatting, strict validation and privacy."""

import re
from importlib import import_module

from django.apps import apps as global_apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.groups.models import GroupMemberAssignment, StructureUnit
from apps.organisations.middleware import ActiveOrganisationMiddleware
from apps.organisations.models import Organisation, OrganisationMembership

from .forms import MemberForm
from .identification import available_id_types, mask_number, normalize
from .models import Member, MemberDocument, MemberHistory
from .services import import_members
from .tests import MemberFixture, PDF_BYTES, TEST_MEDIA_ROOT, TINY_PNG

NONCE_RE = re.compile(r"'nonce-([A-Za-z0-9_\-+/=]+)'")


class IdentificationRuleTests(SimpleTestCase):
    def test_ghana_card_formats_ten_digits_without_guessing(self):
        result = normalize(Member.IDType.GHANA_CARD, "1234567890")
        self.assertEqual(result.raw, "1234567890")
        self.assertEqual(result.normalized, "1234567890")
        self.assertEqual(result.display, "GHA-123456789-0")

    def test_ghana_card_accepts_only_the_exact_generated_display(self):
        formatted = normalize(Member.IDType.GHANA_CARD, "GHA-123456789-0")
        self.assertEqual(formatted.raw, "1234567890")
        self.assertEqual(formatted.normalized, "1234567890")
        self.assertEqual(formatted.display, "GHA-123456789-0")

    def test_ghana_card_rejects_bad_length_letters_and_malformed_prefix(self):
        for value in (
            "123456789", "12345678901", "12a4567890", "123 4567890",
            "GHA-1234567890", "gha-123456789-0", "GHA-12345678-90",
        ):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                normalize(Member.IDType.GHANA_CARD, value)

    def test_voter_and_nhis_preserve_leading_zeros(self):
        self.assertEqual(normalize(Member.IDType.VOTER_ID, "0444901295").display, "0444901295")
        self.assertEqual(normalize(Member.IDType.NHIS, "00123456").display, "00123456")
        with self.assertRaises(ValidationError):
            normalize(Member.IDType.VOTER_ID, "123")
        with self.assertRaises(ValidationError):
            normalize(Member.IDType.NHIS, "1234567a")

    @override_settings(IDENTIFICATION_LEGACY_VOTER_ENABLED=False)
    def test_legacy_voter_is_opt_in(self):
        self.assertNotIn("voter_id_legacy", dict(available_id_types()))
        with self.assertRaises(ValidationError):
            normalize("voter_id_legacy", "OLDVOTER123")

    @override_settings(IDENTIFICATION_LEGACY_VOTER_ENABLED=True)
    def test_legacy_voter_accepts_configured_historical_format(self):
        self.assertIn("voter_id_legacy", dict(available_id_types()))
        result = normalize("voter_id_legacy", " old voter 123 ")
        self.assertEqual(result.normalized, "OLDVOTER123")
        self.assertEqual(result.display, "OLDVOTER123")

    def test_passport_is_uppercased_without_prefix(self):
        result = normalize(Member.IDType.PASSPORT, " g1234567 ")
        self.assertEqual(result.normalized, "G1234567")
        self.assertEqual(result.display, "G1234567")
        with self.assertRaises(ValidationError) as ctx:
            normalize(Member.IDType.PASSPORT, "G123-4567")
        self.assertEqual(ctx.exception.messages[0], "Enter a valid passport number.")

    def test_drivers_licence_normalizes_and_keeps_leading_zero(self):
        result = normalize(Member.IDType.DRIVERS_LICENCE, " dl 001234 ")
        self.assertEqual(result.normalized, "DL001234")
        self.assertEqual(result.display, "DL001234")
        with self.assertRaisesMessage(ValidationError, "Enter a valid driving licence number."):
            normalize(Member.IDType.DRIVERS_LICENCE, "@@@")

    def test_other_does_not_borrow_other_rules(self):
        result = normalize(Member.IDType.OTHER, "Ref/2026-001")
        self.assertEqual(result.normalized, "Ref/2026-001")
        self.assertEqual(result.display, "Ref/2026-001")

    def test_masking_keeps_only_last_four(self):
        self.assertEqual(mask_number("GHA-123456789-0"), "•" * 9 + "7890")
        self.assertEqual(mask_number("123"), "•••")


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class MemberIdentificationFormTests(MemberFixture):
    def png(self, name="front.png"):
        return SimpleUploadedFile(name, TINY_PNG, content_type="image/png")

    def create_ghana_member(self, number="1234567890", member_number="A-ID-FORM", **overrides):
        payload = self.member_payload(
            number=member_number,
            id_type=Member.IDType.GHANA_CARD,
            id_number=number,
            id_front=self.png(),
            **overrides,
        )
        response = self.client.post(reverse("member_create"), payload)
        return response, Member.objects.get(organisation=self.alpha, membership_number=member_number)

    def test_form_formats_ghana_card_and_requires_front_image(self):
        self.login_as(self.alpha_manager, self.alpha)
        response = self.client.post(
            reverse("member_create"),
            self.member_payload(
                number="A-ID-NO-FRONT", id_type=Member.IDType.GHANA_CARD,
                id_number="1234567890", id_front="", id_back="",
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Upload a clear photo of the front of this document.")
        self.assertFalse(Member.objects.filter(membership_number="A-ID-NO-FRONT").exists())

        response, member = self.create_ghana_member()
        self.assertRedirects(response, reverse("member_detail", args=[member.pk]))
        self.assertEqual(member.id_number_raw, "1234567890")
        self.assertEqual(member.id_number_normalized, "1234567890")
        self.assertEqual(member.id_number_display, "GHA-123456789-0")
        self.assertEqual(member.id_number, "GHA-123456789-0")
        self.assertEqual(member.id_verification_status, Member.IDVerificationStatus.UNVERIFIED)

    def test_edit_form_renders_the_formatted_number_in_the_input(self):
        self.login_as(self.alpha_manager, self.alpha)
        _, member = self.create_ghana_member(member_number="A-ID-EDIT-DISPLAY")
        response = self.client.get(reverse("member_edit", args=[member.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="GHA-123456789-0"')

    def test_duplicate_number_is_rejected_with_specific_message(self):
        self.login_as(self.alpha_manager, self.alpha)
        self.create_ghana_member(number="1234567890", member_number="A-ID-FIRST")
        response = self.client.post(
            reverse("member_create"),
            self.member_payload(
                number="A-ID-DUP", id_type=Member.IDType.GHANA_CARD,
                id_number="1234567890", id_front=self.png(),
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This identification number is already registered.")

        # The same number may be used in a different organisation.
        self.login_as(self.beta_admin, self.beta)
        response = self.client.post(
            reverse("member_create"),
            self.member_payload(
                number="A-ID-BETA", id_type=Member.IDType.GHANA_CARD,
                id_number="1234567890", id_front=self.png(),
            ),
        )
        self.assertEqual(response.status_code, 302)

    def test_backend_rejects_invalid_input_even_without_javascript(self):
        self.login_as(self.alpha_manager, self.alpha)
        response = self.client.post(
            reverse("member_create"),
            self.member_payload(
                number="A-ID-BAD", id_type=Member.IDType.GHANA_CARD,
                id_number="12a4567890", id_front=self.png(),
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your Ghana Card number must contain exactly 10 digits.")
        self.assertFalse(Member.objects.filter(membership_number="A-ID-BAD").exists())

    def test_backend_accepts_the_value_written_by_the_live_formatter(self):
        self.login_as(self.alpha_manager, self.alpha)
        response = self.client.post(
            reverse("member_create"),
            self.member_payload(
                number="A-ID-FORMATTED", id_type=Member.IDType.GHANA_CARD,
                id_number="GHA-123456789-0", id_front=self.png(),
            ),
        )
        member = Member.objects.get(membership_number="A-ID-FORMATTED")
        self.assertRedirects(response, reverse("member_detail", args=[member.pk]))
        self.assertEqual(member.id_number_raw, "1234567890")
        self.assertEqual(member.id_number_normalized, "1234567890")
        self.assertEqual(member.id_number_display, "GHA-123456789-0")
        self.assertEqual(member.id_number, "GHA-123456789-0")

    def test_passport_is_normalized_and_other_needs_document_name(self):
        self.login_as(self.alpha_manager, self.alpha)
        response = self.client.post(
            reverse("member_create"),
            self.member_payload(
                number="A-ID-PASS", id_type=Member.IDType.PASSPORT,
                id_number=" g1234567 ", id_front=self.png(), id_document_name="",
            ),
        )
        member = Member.objects.get(membership_number="A-ID-PASS")
        self.assertRedirects(response, reverse("member_detail", args=[member.pk]))
        self.assertEqual(member.id_number_normalized, "G1234567")
        self.assertEqual(member.id_document_name, "")

        response = self.client.post(
            reverse("member_create"),
            self.member_payload(number="A-ID-OTHER", id_type=Member.IDType.OTHER, id_document_name=""),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter the name of this identification document.")

    def test_other_requires_issuing_organization_and_front_image(self):
        self.login_as(self.alpha_manager, self.alpha)
        response = self.client.post(
            reverse("member_create"),
            self.member_payload(
                number="A-ID-OTHER-INCOMPLETE",
                id_type=Member.IDType.OTHER,
                id_document_name="Community ID",
                id_issuing_authority="",
                id_front="",
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter the issuing organization for this document.")
        self.assertContains(response, "Upload a clear photo of the front of this document.")
        self.assertFalse(
            Member.objects.filter(membership_number="A-ID-OTHER-INCOMPLETE").exists()
        )

        response = self.client.post(
            reverse("member_create"),
            self.member_payload(
                number="A-ID-OTHER-OK",
                id_type=Member.IDType.OTHER,
                id_document_name="Community ID",
                id_issuing_authority="Local Council",
                id_front=self.png(),
                id_back=self.png("back.png"),
            ),
        )
        member = Member.objects.get(membership_number="A-ID-OTHER-OK")
        self.assertRedirects(response, reverse("member_detail", args=[member.pk]))
        self.assertEqual(member.id_document_name, "Community ID")
        self.assertEqual(member.id_issuing_authority, "Local Council")
        self.assertTrue(member.id_front)
        self.assertTrue(member.id_back)

    def test_id_image_content_is_verified(self):
        self.login_as(self.alpha_manager, self.alpha)
        response = self.client.post(
            reverse("member_create"),
            self.member_payload(
                number="A-ID-EVIL", id_type=Member.IDType.GHANA_CARD,
                id_number="1234567890",
                id_front=SimpleUploadedFile("front.png", b"MZ\x90\x00 executable", content_type="image/png"),
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Upload a valid image")
        self.assertFalse(Member.objects.filter(membership_number="A-ID-EVIL").exists())

    def test_edit_keeps_existing_uploads_when_no_replacement_is_supplied(self):
        self.login_as(self.alpha_manager, self.alpha)
        _, member = self.create_ghana_member(member_number="A-ID-EDIT")
        original_front = member.id_front.name
        original_back = member.id_back.name
        response = self.client.post(
            reverse("member_edit", args=[member.pk]),
            self.member_payload(
                number="A-ID-EDIT", first_name="Ama", last_name="Mensah",
                id_type=Member.IDType.GHANA_CARD, id_number="1234567890", location="Accra",
                id_front="", id_back="",
            ),
        )
        self.assertRedirects(response, reverse("member_detail", args=[member.pk]))
        member.refresh_from_db()
        self.assertEqual(member.id_front.name, original_front)
        self.assertEqual(member.id_back.name, original_back)
        self.assertEqual(member.id_number_display, "GHA-123456789-0")

    def test_verification_status_requires_explicit_review(self):
        self.login_as(self.alpha_manager, self.alpha)
        _, member = self.create_ghana_member(member_number="A-ID-REVIEW")
        self.assertEqual(member.id_verification_status, Member.IDVerificationStatus.UNVERIFIED)
        self.assertIsNone(member.id_verified_at)

        response = self.client.post(
            reverse("member_id_verification_update", args=[member.pk]),
            {"id_verification_status": Member.IDVerificationStatus.VERIFIED},
        )
        self.assertRedirects(response, reverse("member_detail", args=[member.pk]))
        member.refresh_from_db()
        self.assertEqual(member.id_verification_status, Member.IDVerificationStatus.VERIFIED)
        self.assertIsNotNone(member.id_verified_at)
        event = member.history.get(action=MemberHistory.Action.ID_VERIFICATION_REVIEWED)
        self.assertNotIn(member.id_number_normalized, str(event.changes))

    def test_document_and_id_image_access_is_audited(self):
        self.login_as(self.alpha_admin, self.alpha)
        response = self.client.post(
            reverse("member_document_add", args=[self.alpha_member.pk]),
            {"title": "Ghana Card", "document_type": MemberDocument.DocumentType.GHANA_CARD,
             "file": SimpleUploadedFile("card.pdf", PDF_BYTES, content_type="application/pdf")},
        )
        self.assertRedirects(response, reverse("member_detail", args=[self.alpha_member.pk]))
        document = MemberDocument.objects.get(member=self.alpha_member)
        self.client.get(reverse("member_document_download", args=[document.pk]))
        self.assertTrue(self.alpha_member.history.filter(action=MemberHistory.Action.DOCUMENT_DOWNLOADED).exists())

        self.alpha_member.id_front = SimpleUploadedFile("front.png", TINY_PNG, content_type="image/png")
        self.alpha_member.save(update_fields=["id_front"])
        self.client.get(reverse("member_id_photo", args=[self.alpha_member.pk, "front"]))
        self.assertTrue(self.alpha_member.history.filter(action=MemberHistory.Action.ID_IMAGE_VIEWED).exists())

    def test_list_masks_id_number_and_search_uses_only_last_four(self):
        self.login_as(self.alpha_admin, self.alpha)
        self.alpha_member.id_number_display = "GHA-123456789-0"
        self.alpha_member.id_number_normalized = "1234567890"
        self.alpha_member.save(update_fields=["id_number_display", "id_number_normalized"])
        response = self.client.get(reverse("member_list"), {"q": "7890"})
        self.assertContains(response, "•••••••••7890")
        self.assertNotContains(response, "GHA-123456789-0")
        self.assertNotContains(response, "1234567890")

    def test_full_id_is_only_shown_to_managers_and_admins(self):
        self.alpha_member.id_type = Member.IDType.GHANA_CARD
        self.alpha_member.id_number = "GHA-123456789-0"
        self.alpha_member.id_number_display = "GHA-123456789-0"
        self.alpha_member.id_number_normalized = "1234567890"
        self.alpha_member.save(update_fields=[
            "id_type", "id_number", "id_number_display", "id_number_normalized"
        ])
        membership = OrganisationMembership.objects.get(
            organisation=self.alpha, user=self.alpha_field
        )
        unit = StructureUnit.objects.create(
            organisation=self.alpha, name="Masked Group", unit_type="group",
            field_officer=membership,
        )
        GroupMemberAssignment.objects.create(
            organisation=self.alpha, unit=unit, member=self.alpha_member
        )

        self.login_as(self.alpha_field, self.alpha)
        response = self.client.get(reverse("field_member_detail", args=[self.alpha_member.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "GHA-123456789-0")
        self.assertNotContains(response, "1234567890")
        self.assertContains(response, "•••••••••7890")

        self.login_as(self.alpha_admin, self.alpha)
        response = self.client.get(reverse("member_detail", args=[self.alpha_member.pk]))
        self.assertContains(response, "GHA-123456789-0")

    def test_member_form_loads_csp_safe_dynamic_script(self):
        self.login_as(self.alpha_manager, self.alpha)
        response = self.client.get(reverse("member_create"))
        nonce = NONCE_RE.search(response.headers["Content-Security-Policy"]).group(1)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'js/member_id.js" nonce="{nonce}"')
        self.assertContains(response, 'id-profile-config')
        self.assertContains(
            response,
            "Type only the digits; GHA and the hyphens are added automatically.",
        )
        self.assertNotContains(response, "Formatted as shown on the document")


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class IdentificationModelValidationTests(TestCase):
    def setUp(self):
        self.organisation = Organisation.objects.create(name="ID Org", slug="id-org", currency="GHS")
        self.user = get_user_model().objects.create_user(email="id@example.test", password="StrongPass!42")
        OrganisationMembership.objects.create(
            user=self.user, organisation=self.organisation, role=OrganisationMembership.Role.ADMIN,
        )

    def make_member(self, **kwargs):
        return Member.objects.create(
            organisation=self.organisation, created_by=self.user, updated_by=self.user,
            membership_number=kwargs.pop("membership_number"), first_name="Test", last_name="Member",
            **kwargs,
        )

    def test_model_revalidates_direct_writes(self):
        member = self.make_member(membership_number="ID-1")
        member.id_type = Member.IDType.NHIS
        member.id_number_raw = "00123456"
        member.full_clean()
        self.assertEqual(member.id_number_normalized, "00123456")
        self.assertEqual(member.id_number_display, "00123456")
        self.assertEqual(member.id_number, "00123456")

    def test_database_and_form_rules_share_the_same_normalized_value(self):
        first = self.make_member(membership_number="ID-2")
        first.id_type = Member.IDType.GHANA_CARD
        first.id_number_raw = "1234567890"
        first.full_clean()
        first.save()
        self.assertEqual(first.id_number_display, "GHA-123456789-0")

        second = self.make_member(membership_number="ID-3")
        second.id_type = Member.IDType.GHANA_CARD
        second.id_number_raw = "1234567890"
        with self.assertRaisesMessage(ValidationError, "This identification number is already registered."):
            second.full_clean()

    def test_legacy_display_value_is_preserved_without_raw_input(self):
        member = self.make_member(membership_number="ID-4", id_type=Member.IDType.GHANA_CARD, id_number="GHA-820000000")
        member.full_clean()
        self.assertEqual(member.id_number, "GHA-820000000")
        self.assertEqual(member.id_number_raw, "")

    def test_form_respects_active_organisation_middleware(self):
        self.client.force_login(self.user)
        session = self.client.session
        session[ActiveOrganisationMiddleware.SESSION_KEY] = self.organisation.pk
        session.save()
        self.assertEqual(self.client.get(reverse("member_create")).status_code, 200)

    def test_form_rejects_unknown_type(self):
        form = MemberForm(
            {"first_name": "A", "last_name": "B", "membership_number": "ID-5",
             "id_type": "unknown", "id_number": "123", "status": "active"},
            organisation=self.organisation,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("id_type", form.errors)

    def test_import_normalizes_identification_numbers(self):
        uploaded = SimpleUploadedFile(
            "members.csv",
            b"first_name,last_name,membership_number,id_type,id_number\n"
            b"Kofi,Asare,ID-IMPORT,ghana_card,1234567890\n",
            content_type="text/csv",
        )
        created = import_members(uploaded, self.organisation, self.user)
        member = created[0]
        self.assertEqual(member.id_number_raw, "1234567890")
        self.assertEqual(member.id_number_normalized, "1234567890")
        self.assertEqual(member.id_number_display, "GHA-123456789-0")
        self.assertEqual(member.id_verification_status, Member.IDVerificationStatus.UNVERIFIED)

    def test_import_rejects_invalid_identification_number(self):
        uploaded = SimpleUploadedFile(
            "members.csv",
            b"first_name,last_name,membership_number,id_type,id_number\n"
            b"Kofi,Asare,ID-BAD,ghana_card,GHA-1234567890\n",
            content_type="text/csv",
        )
        with self.assertRaisesMessage(
            ValidationError, "Enter the 10 digits exactly as shown on the Ghana Card."
        ):
            import_members(uploaded, self.organisation, self.user)
        self.assertFalse(Member.objects.filter(membership_number="ID-BAD").exists())

    def test_backfill_preserves_legacy_display_and_skips_duplicates(self):
        first = self.make_member(
            membership_number="ID-LEGACY-1", id_type=Member.IDType.GHANA_CARD,
            id_number="GHA-123456789-0",
        )
        second = self.make_member(
            membership_number="ID-LEGACY-2", id_type=Member.IDType.GHANA_CARD,
            id_number="GHA-123456789-0",
        )
        Member.objects.filter(pk__in=[first.pk, second.pk]).update(
            id_number_display="", id_number_normalized=""
        )
        migration = import_module("apps.members.migrations.0008_backfill_identification_fields")
        migration.backfill(global_apps, None)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.id_number_display, "GHA-123456789-0")
        self.assertEqual(second.id_number_display, "GHA-123456789-0")
        self.assertEqual(
            sum(bool(member.id_number_normalized) for member in (first, second)),
            1,
        )
