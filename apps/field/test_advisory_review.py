from datetime import date
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.groups.models import GroupMemberAssignment, StructureUnit
from apps.members.models import Member
from apps.organisations.middleware import ActiveOrganisationMiddleware
from apps.organisations.models import Organisation, OrganisationMembership

from .models import AdvisoryRecord, FieldVisit


User = get_user_model()
TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix="konnectcore-advisory-tests-")
TINY_GIF = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class AdvisoryReviewTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.organisation = Organisation.objects.create(name="Advisory Org", slug="advisory-org")
        self.admin = self.create_user("admin@advisory.test", self.organisation, "admin")
        self.manager = self.create_user("manager@advisory.test", self.organisation, "manager")
        self.officer = self.create_user("officer@advisory.test", self.organisation, "field_officer")
        officer_membership = OrganisationMembership.objects.get(user=self.officer, organisation=self.organisation)
        member = Member.objects.create(
            organisation=self.organisation,
            created_by=self.admin,
            updated_by=self.admin,
            membership_number="A1",
            first_name="Ama",
            last_name="Farmer",
        )
        unit = StructureUnit.objects.create(
            organisation=self.organisation,
            name="Officer group",
            unit_type="group",
            field_officer=officer_membership,
        )
        GroupMemberAssignment.objects.create(organisation=self.organisation, unit=unit, member=member)
        self.member = member
        visit = FieldVisit.objects.create(
            organisation=self.organisation,
            member=member,
            visit_date=date(2026, 11, 12),
            notes="Farm visit",
            recorded_by=self.officer,
        )
        self.advisory = AdvisoryRecord.objects.create(
            organisation=self.organisation,
            visit=visit,
            observation="Needs irrigation advice",
            photo=SimpleUploadedFile("advisory.gif", TINY_GIF, content_type="image/gif"),
        )
        self.visit = visit

    def create_user(self, email, organisation, role):
        user = User.objects.create_user(email=email, password="test-password")
        OrganisationMembership.objects.create(organisation=organisation, user=user, role=role)
        return user

    def login(self, user, organisation=None):
        self.client.force_login(user)
        session = self.client.session
        session[ActiveOrganisationMiddleware.SESSION_KEY] = (organisation or self.organisation).pk
        session.save()

    def test_manager_can_list_and_mark_advisory_reviewed(self):
        self.login(self.manager)

        response = self.client.get(reverse("field_advisory_review_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Needs irrigation advice")
        self.assertContains(response, reverse("field_advisory_review_detail", args=[self.advisory.pk]))

        response = self.client.post(
            reverse("field_advisory_review_detail", args=[self.advisory.pk]),
            {"action": "comment", "review_comment": "Please check the water source."},
        )
        self.assertRedirects(response, reverse("field_advisory_review_detail", args=[self.advisory.pk]))
        self.advisory.refresh_from_db()
        self.assertEqual(self.advisory.status, "requested")
        self.assertEqual(self.advisory.review_comment, "Please check the water source.")

        response = self.client.post(
            reverse("field_advisory_review_detail", args=[self.advisory.pk]),
            {"action": "review", "review_comment": "Advice approved."},
        )
        self.assertRedirects(response, reverse("field_advisory_review_list"))
        self.advisory.refresh_from_db()
        self.assertEqual(self.advisory.status, "reviewed")
        self.assertEqual(self.advisory.review_comment, "Advice approved.")
        self.assertEqual(self.advisory.reviewed_by, self.manager)

    def test_field_officer_activity_page_lists_only_their_assigned_records(self):
        self.login(self.officer)
        response = self.client.get(reverse("field_activity"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My field activity")
        self.assertContains(response, "Needs irrigation advice")
        self.assertContains(response, reverse("field_visit_add", args=[self.member.pk]))
        self.assertEqual(self.client.get(reverse("field_activity")).status_code, 200)

    def test_manager_cannot_open_field_officer_activity_workspace(self):
        self.login(self.manager)
        self.assertEqual(self.client.get(reverse("field_activity")).status_code, 403)

    def test_field_officer_cannot_review_advisories(self):
        self.login(self.officer)
        self.assertEqual(self.client.get(reverse("field_advisory_review_list")).status_code, 403)

    def test_review_is_scoped_to_active_organisation(self):
        other_organisation = Organisation.objects.create(name="Other Org", slug="other-advisory-org")
        other_admin = self.create_user("admin@other-advisory.test", other_organisation, "admin")
        other_member = Member.objects.create(
            organisation=other_organisation,
            created_by=other_admin,
            updated_by=other_admin,
            membership_number="B1",
            first_name="Beta",
            last_name="Farmer",
        )
        other_visit = FieldVisit.objects.create(
            organisation=other_organisation,
            member=other_member,
            visit_date=date(2026, 11, 12),
            notes="Other farm visit",
            recorded_by=other_admin,
        )
        other_advisory = AdvisoryRecord.objects.create(
            organisation=other_organisation,
            visit=other_visit,
            observation="Private advice",
        )

        self.login(self.manager)
        response = self.client.get(reverse("field_advisory_review_detail", args=[other_advisory.pk]))
        self.assertEqual(response.status_code, 404)

    def test_advisory_photo_is_served_only_to_users_with_member_access(self):
        self.login(self.officer)
        url = reverse("field_advisory_photo", args=[self.advisory.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), TINY_GIF)
        self.assertEqual(self.client.get("/media/" + self.advisory.photo.name).status_code, 404)

        other_organisation = Organisation.objects.create(name="Private Org", slug="private-advisory-org")
        other_admin = self.create_user("admin@private-advisory.test", other_organisation, "admin")
        self.login(other_admin, other_organisation)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_advisory_photo_requires_authentication(self):
        url = reverse("field_advisory_photo", args=[self.advisory.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
