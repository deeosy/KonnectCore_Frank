import csv
import io
import shutil
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from openpyxl import Workbook

from apps.organisations.middleware import ActiveOrganisationMiddleware
from apps.organisations.models import Organisation, OrganisationMembership

from .models import Member, MemberDocument, MemberHistory

User = get_user_model()
TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix="konnectcore-test-media-")


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class MemberFixture(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.alpha = Organisation.objects.create(name="Alpha Cooperative", slug="alpha", currency="GHS")
        self.beta = Organisation.objects.create(name="Beta Farmers", slug="beta", currency="KES")
        self.alpha_admin = User.objects.create_user(email="admin@alpha.test", password="StrongPass!42")
        self.alpha_manager = User.objects.create_user(email="manager@alpha.test", password="StrongPass!42")
        self.alpha_field = User.objects.create_user(email="field@alpha.test", password="StrongPass!42")
        self.beta_admin = User.objects.create_user(email="admin@beta.test", password="StrongPass!42")
        for user, organisation, role in [
            (self.alpha_admin, self.alpha, OrganisationMembership.Role.ADMIN),
            (self.alpha_manager, self.alpha, OrganisationMembership.Role.MANAGER),
            (self.alpha_field, self.alpha, OrganisationMembership.Role.FIELD_OFFICER),
            (self.beta_admin, self.beta, OrganisationMembership.Role.ADMIN),
        ]:
            OrganisationMembership.objects.create(user=user, organisation=organisation, role=role)
        self.alpha_member = self.make_member(self.alpha, self.alpha_admin, "A-001", "Ama", "Mensah")
        self.beta_member = self.make_member(self.beta, self.beta_admin, "B-001", "Ben", "Otieno")

    def make_member(self, organisation, actor, number, first, last, **kwargs):
        return Member.objects.create(
            organisation=organisation,
            created_by=actor,
            updated_by=actor,
            membership_number=number,
            first_name=first,
            last_name=last,
            status=kwargs.pop("status", Member.Status.ACTIVE),
            **kwargs,
        )

    def login_as(self, user, organisation):
        self.client.force_login(user)
        session = self.client.session
        session[ActiveOrganisationMiddleware.SESSION_KEY] = organisation.pk
        session.save()

    def member_payload(self, number="A-002", **overrides):
        data = {
            "first_name": "Abena", "last_name": "Owusu", "phone": "+233200000001",
            "membership_number": number, "id_reference": "ID-88", "location": "Kumasi",
            "status": Member.Status.ACTIVE,
        }
        data.update(overrides)
        return data


class MemberIsolationTests(MemberFixture):
    def test_list_and_search_never_show_other_organisation(self):
        self.login_as(self.alpha_admin, self.alpha)
        response = self.client.get(reverse("member_list"))
        self.assertContains(response, "Ama Mensah")
        self.assertNotContains(response, "Ben Otieno")
        response = self.client.get(reverse("member_list"), {"q": "Otieno"})
        self.assertNotContains(response, "Ben Otieno")
        self.assertContains(response, "No members match")

    def test_guessed_member_uuid_returns_404_for_detail_edit_and_document_add(self):
        self.login_as(self.alpha_admin, self.alpha)
        for name in ("member_detail", "member_edit", "member_document_add"):
            self.assertEqual(self.client.get(reverse(name, args=[self.beta_member.pk])).status_code, 404)

    def test_same_membership_number_is_allowed_across_organisations_only(self):
        self.make_member(self.beta, self.beta_admin, "A-001", "Other", "Member")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.make_member(self.alpha, self.alpha_admin, "A-001", "Duplicate", "Member")

    def test_cross_tenant_document_model_validation_fails(self):
        document = MemberDocument(
            organisation=self.alpha, member=self.beta_member, title="Wrong tenant",
            file=SimpleUploadedFile("id.pdf", b"pdf"), uploaded_by=self.alpha_admin,
        )
        with self.assertRaises(ValidationError):
            document.full_clean()


class MemberRoleTests(MemberFixture):
    def test_all_roles_can_view_members(self):
        for user in (self.alpha_admin, self.alpha_manager, self.alpha_field):
            self.client.logout()
            self.login_as(user, self.alpha)
            self.assertEqual(self.client.get(reverse("member_list")).status_code, 200)
            self.assertEqual(self.client.get(reverse("member_detail", args=[self.alpha_member.pk])).status_code, 200)

    def test_field_officer_cannot_mutate_or_import_in_stage_two(self):
        self.login_as(self.alpha_field, self.alpha)
        urls = [
            reverse("member_create"), reverse("member_edit", args=[self.alpha_member.pk]),
            reverse("member_document_add", args=[self.alpha_member.pk]), reverse("member_import"),
        ]
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 403)

    def test_manager_can_create_and_edit_with_history(self):
        self.login_as(self.alpha_manager, self.alpha)
        response = self.client.post(reverse("member_create"), self.member_payload())
        member = Member.objects.get(organisation=self.alpha, membership_number="A-002")
        self.assertRedirects(response, reverse("member_detail", args=[member.pk]))
        self.assertTrue(member.history.filter(action=MemberHistory.Action.CREATED, actor=self.alpha_manager).exists())
        payload = self.member_payload(location="Accra")
        response = self.client.post(reverse("member_edit", args=[member.pk]), payload)
        self.assertRedirects(response, reverse("member_detail", args=[member.pk]))
        event = member.history.get(action=MemberHistory.Action.UPDATED)
        self.assertEqual(event.changes["location"], {"from": "Kumasi", "to": "Accra"})


class MemberSearchTests(MemberFixture):
    def test_searches_phone_membership_id_location_and_name(self):
        self.alpha_member.phone = "+233555123"
        self.alpha_member.id_reference = "NAT-443"
        self.alpha_member.location = "Tamale North"
        self.alpha_member.save()
        self.login_as(self.alpha_admin, self.alpha)
        for query in ("Ama", "Mensah", "A-001", "555123", "NAT-443", "Tamale"):
            self.assertContains(self.client.get(reverse("member_list"), {"q": query}), "Ama Mensah")

    def test_status_filter_is_scoped(self):
        self.alpha_member.status = Member.Status.INACTIVE
        self.alpha_member.save(update_fields=["status"])
        self.login_as(self.alpha_admin, self.alpha)
        self.assertContains(self.client.get(reverse("member_list"), {"status": "inactive"}), "Ama Mensah")
        self.assertNotContains(self.client.get(reverse("member_list"), {"status": "active"}), "Ama Mensah")


class MemberFileTests(MemberFixture):
    def test_missing_photo_returns_404(self):
        self.login_as(self.alpha_admin, self.alpha)
        response = self.client.get(reverse("member_photo", args=[self.alpha_member.pk]))
        self.assertEqual(response.status_code, 404)
    def test_document_upload_and_download_are_tenant_protected(self):
        self.login_as(self.beta_admin, self.beta)
        response = self.client.post(
            reverse("member_document_add", args=[self.beta_member.pk]),
            {"title": "Identity", "file": SimpleUploadedFile("identity.pdf", b"private-beta-data", content_type="application/pdf")},
        )
        self.assertRedirects(response, reverse("member_detail", args=[self.beta_member.pk]))
        document = MemberDocument.objects.get(member=self.beta_member)
        self.assertTrue(document.file.name.startswith(f"organisations/{self.beta.pk}/members/{self.beta_member.pk}/documents/"))
        self.client.logout()
        self.login_as(self.alpha_admin, self.alpha)
        self.assertEqual(self.client.get(reverse("member_document_download", args=[document.pk])).status_code, 404)
        self.client.logout()
        self.login_as(self.beta_admin, self.beta)
        download = self.client.get(reverse("member_document_download", args=[document.pk]))
        self.assertEqual(download.status_code, 200)
        self.assertEqual(b"".join(download.streaming_content), b"private-beta-data")

    def test_disallowed_document_extension_is_rejected(self):
        self.login_as(self.alpha_admin, self.alpha)
        response = self.client.post(
            reverse("member_document_add", args=[self.alpha_member.pk]),
            {"title": "Executable", "file": SimpleUploadedFile("bad.exe", b"not allowed")},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Upload a PDF or image file")
        self.assertFalse(MemberDocument.objects.filter(member=self.alpha_member).exists())


class MemberImportTests(MemberFixture):
    def upload_csv(self, text, name="members.csv"):
        return SimpleUploadedFile(name, text.encode("utf-8"), content_type="text/csv")

    def test_csv_import_creates_tenant_members_and_history(self):
        self.login_as(self.alpha_admin, self.alpha)
        uploaded = self.upload_csv(
            "first_name,last_name,membership_number,phone,location,status\n"
            "Kojo,Asare,A-100,+2331,Sunyani,active\n"
            "Esi,Boateng,A-101,+2332,Accra,inactive\n"
        )
        response = self.client.post(reverse("member_import"), {"file": uploaded})
        self.assertRedirects(response, reverse("member_list"))
        imported = Member.objects.for_organisation(self.alpha).filter(membership_number__in=["A-100", "A-101"])
        self.assertEqual(imported.count(), 2)
        self.assertEqual(Member.objects.for_organisation(self.beta).filter(membership_number="A-100").count(), 0)
        self.assertEqual(MemberHistory.objects.for_organisation(self.alpha).filter(action=MemberHistory.Action.IMPORTED).count(), 2)

    def test_xlsx_import_works(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["first_name", "last_name", "membership_number", "status"])
        sheet.append(["Yaw", "Kumi", "A-200", "active"])
        content = io.BytesIO()
        workbook.save(content)
        self.login_as(self.alpha_manager, self.alpha)
        response = self.client.post(
            reverse("member_import"),
            {"file": SimpleUploadedFile("members.xlsx", content.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        self.assertRedirects(response, reverse("member_list"))
        self.assertTrue(Member.objects.filter(organisation=self.alpha, membership_number="A-200").exists())

    def test_import_is_atomic_when_any_row_is_invalid(self):
        self.login_as(self.alpha_admin, self.alpha)
        uploaded = self.upload_csv(
            "first_name,last_name,membership_number,status\n"
            "Good,Member,A-300,active\n"
            "Bad,Member,A-301,unknown\n"
        )
        response = self.client.post(reverse("member_import"), {"file": uploaded})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "invalid status")
        self.assertFalse(Member.objects.filter(organisation=self.alpha, membership_number__in=["A-300", "A-301"]).exists())

    def test_duplicate_number_rolls_back_whole_import(self):
        self.login_as(self.alpha_admin, self.alpha)
        uploaded = self.upload_csv(
            "first_name,last_name,membership_number\n"
            "New,Member,A-400\n"
            "Duplicate,Member,A-001\n"
        )
        response = self.client.post(reverse("member_import"), {"file": uploaded})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists")
        self.assertFalse(Member.objects.filter(organisation=self.alpha, membership_number="A-400").exists())


class SuspendedOrganisationTests(MemberFixture):
    def test_suspended_organisation_cannot_access_member_routes(self):
        self.alpha.status = Organisation.Status.SUSPENDED
        self.alpha.save(update_fields=["status"])
        self.login_as(self.alpha_admin, self.alpha)
        self.assertRedirects(self.client.get(reverse("member_list")), reverse("choose_organisation"))
