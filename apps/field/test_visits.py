"""Field visit visibility and photo protection (UAT I-4) and awaiting-assignment feedback (I-7)."""
import shutil
import tempfile
from datetime import date

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.groups.models import GroupMemberAssignment, StructureUnit
from apps.members.models import Member
from apps.organisations.middleware import ActiveOrganisationMiddleware
from apps.organisations.models import Organisation, OrganisationMembership

from .models import FieldVisit

User = get_user_model()
TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix="konnectcore-visit-tests-")
TINY_GIF = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class FieldVisitVisibilityTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.org = Organisation.objects.create(name="Visits Org", slug="visits-org")
        self.other = Organisation.objects.create(name="Other Visits Org", slug="visits-other")
        self.admin = self.user("admin@visits.test", self.org, "admin")
        self.manager = self.user("manager@visits.test", self.org, "manager")
        self.north = self.user("north@visits.test", self.org, "field_officer")
        self.south = self.user("south@visits.test", self.org, "field_officer")
        self.other_admin = self.user("admin@other-visits.test", self.other, "admin")
        north_membership = OrganisationMembership.objects.get(organisation=self.org, user=self.north)
        south_membership = OrganisationMembership.objects.get(organisation=self.org, user=self.south)
        self.north_member = self.member("N1", "Nana", "North")
        self.south_member = self.member("S1", "Sena", "South")
        self.unassigned = self.member("U1", "Uche", "Unassigned")
        for name, officer, member in (("North G", north_membership, self.north_member), ("South G", south_membership, self.south_member)):
            unit = StructureUnit.objects.create(organisation=self.org, name=name, unit_type="group", field_officer=officer)
            GroupMemberAssignment.objects.create(organisation=self.org, unit=unit, member=member)
        self.visit = FieldVisit.objects.create(
            organisation=self.org, member=self.north_member, visit_date=date(2026, 9, 30),
            notes="QA visit north notes", recorded_by=self.north,
            photo=SimpleUploadedFile("visit.gif", TINY_GIF, content_type="image/gif"),
        )
        self.plain_visit = FieldVisit.objects.create(
            organisation=self.org, member=self.south_member, visit_date=date(2026, 9, 29),
            notes="QA visit south notes", recorded_by=self.south,
        )

    def user(self, email, org, role):
        user = User.objects.create_user(email=email, password="x")
        OrganisationMembership.objects.create(organisation=org, user=user, role=role)
        return user

    def member(self, number, first, last):
        return Member.objects.create(
            organisation=self.org, created_by=self.admin, updated_by=self.admin,
            membership_number=number, first_name=first, last_name=last,
        )

    def login(self, user, org=None):
        self.client.logout()
        self.client.force_login(user)
        session = self.client.session
        session[ActiveOrganisationMiddleware.SESSION_KEY] = (org or self.org).pk
        session.save()

    def photo_url(self, visit=None):
        return reverse("field_visit_photo", args=[(visit or self.visit).pk])

    def test_member_profile_lists_visits_with_photo_link(self):
        self.login(self.admin)
        response = self.client.get(reverse("member_detail", args=[self.north_member.pk]))
        self.assertContains(response, "Field visits")
        self.assertContains(response, "QA visit north notes")
        self.assertContains(response, self.photo_url())

    def test_photo_allowed_for_admin_manager_and_assigned_officer(self):
        for user in (self.admin, self.manager, self.north):
            self.login(user)
            response = self.client.get(self.photo_url())
            self.assertEqual(response.status_code, 200, user.email)
            self.assertEqual(response["Content-Type"], "image/gif")
            self.assertEqual(b"".join(response.streaming_content), TINY_GIF)

    def test_photo_hidden_from_unassigned_officer_and_other_organisation(self):
        self.login(self.south)
        self.assertEqual(self.client.get(self.photo_url()).status_code, 404)
        self.login(self.other_admin, self.other)
        self.assertEqual(self.client.get(self.photo_url()).status_code, 404)

    def test_photo_requires_login_and_missing_photo_is_404(self):
        self.client.logout()
        response = self.client.get(self.photo_url())
        self.assertNotEqual(response.status_code, 200)
        self.login(self.admin)
        self.assertEqual(self.client.get(self.photo_url(self.plain_visit)).status_code, 404)

    def test_direct_media_path_is_not_served(self):
        self.login(self.admin)
        self.assertEqual(self.client.get("/media/" + self.visit.photo.name).status_code, 404)

    def test_field_workspace_shows_only_own_recent_visits(self):
        self.login(self.north)
        response = self.client.get(reverse("field_home"))
        self.assertContains(response, "My recent visits")
        self.assertContains(response, "QA visit north notes")
        self.assertNotContains(response, "QA visit south notes")

    def test_dashboard_shows_recent_field_visits(self):
        self.login(self.manager)
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "Recent field visits")
        self.assertContains(response, "QA visit north notes")
        self.assertContains(response, "QA visit south notes")

    def test_dashboard_lists_members_awaiting_assignment(self):
        self.login(self.admin)
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "Members awaiting assignment")
        self.assertContains(response, "Uche Unassigned")
        self.assertNotContains(response, "Nana North (N1)")

    def test_field_registration_explains_awaiting_assignment(self):
        self.login(self.north)
        response = self.client.post(reverse("field_member_create"), {
            "first_name": "QA_TEST_New", "last_name": "Officer", "membership_number": "QA_NEW1", "status": "active",
        }, follow=True)
        self.assertContains(response, "awaiting assignment")
        self.assertTrue(Member.objects.filter(organisation=self.org, membership_number="QA_NEW1").exists())
