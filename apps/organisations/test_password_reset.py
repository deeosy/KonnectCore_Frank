"""Admin-issued password reset links (no email): one-time link shared by WhatsApp, like invitations."""
import re
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.organisations.middleware import ActiveOrganisationMiddleware
from apps.organisations.models import Organisation, OrganisationMembership
from apps.organisations.password_resets import StaffPasswordReset

User = get_user_model()
NEW_PASSWORD = "Fresh-Mango-Lantern-93"


class ResetFixture(TestCase):
    def setUp(self):
        self.alpha = Organisation.objects.create(name="Alpha Cooperative", slug="alpha", currency="GHS")
        self.beta = Organisation.objects.create(name="Beta Farmers", slug="beta", currency="GHS")
        self.admin = User.objects.create_user(email="admin@alpha.test", password="CorrectHorse!42")
        self.beta_admin = User.objects.create_user(email="admin@beta.test", password="CorrectHorse!42")
        self.manager = User.objects.create_user(email="manager@alpha.test", password="CorrectHorse!42")
        self.field = User.objects.create_user(email="field@alpha.test", password="OldPassword!42")
        self.admin_m = OrganisationMembership.objects.create(organisation=self.alpha, user=self.admin, role=OrganisationMembership.Role.ADMIN)
        OrganisationMembership.objects.create(organisation=self.beta, user=self.beta_admin, role=OrganisationMembership.Role.ADMIN)
        self.manager_m = OrganisationMembership.objects.create(organisation=self.alpha, user=self.manager, role=OrganisationMembership.Role.MANAGER)
        self.field_m = OrganisationMembership.objects.create(organisation=self.alpha, user=self.field, role=OrganisationMembership.Role.FIELD_OFFICER)

    def login_as(self, user, organisation):
        self.client.force_login(user)
        session = self.client.session
        session[ActiveOrganisationMiddleware.SESSION_KEY] = organisation.pk
        session.save()

    def issue_url(self, membership):
        return reverse("staff_password_reset", args=[membership.pk])

    def issue_link(self, membership=None):
        self.login_as(self.admin, self.alpha)
        response = self.client.post(self.issue_url(membership or self.field_m))
        self.assertEqual(response.status_code, 200)
        match = re.search(r"/password-reset/([A-Za-z0-9_-]+)/", response.content.decode())
        self.assertIsNotNone(match, "reset link not shown")
        self.client.logout()
        return match.group(1)


class IssueResetTests(ResetFixture):
    def test_admin_gets_one_time_link_and_only_hash_is_stored(self):
        token = self.issue_link()
        reset = StaffPasswordReset.objects.get(user=self.field)
        self.assertNotEqual(reset.token_hash, token)
        self.assertEqual(reset.token_hash, StaffPasswordReset.digest(token))
        self.assertEqual(reset.issued_by, self.admin)
        self.assertEqual(reset.organisation, self.alpha)
        self.assertTrue(reset.is_valid)
        self.assertLessEqual(reset.expires_at, timezone.now() + timedelta(hours=24, minutes=1))

    def test_issue_requires_post(self):
        self.login_as(self.admin, self.alpha)
        self.assertEqual(self.client.get(self.issue_url(self.field_m)).status_code, 405)
        self.assertFalse(StaffPasswordReset.objects.exists())

    def test_manager_and_field_officer_cannot_issue(self):
        for user in (self.manager, self.field):
            self.login_as(user, self.alpha)
            self.assertEqual(self.client.post(self.issue_url(self.admin_m)).status_code, 403)
        self.assertFalse(StaffPasswordReset.objects.exists())

    def test_other_organisation_admin_gets_404(self):
        self.login_as(self.beta_admin, self.beta)
        self.assertEqual(self.client.post(self.issue_url(self.field_m)).status_code, 404)
        self.assertFalse(StaffPasswordReset.objects.exists())

    def test_user_in_another_organisation_cannot_be_reset(self):
        OrganisationMembership.objects.create(organisation=self.beta, user=self.field, role=OrganisationMembership.Role.FIELD_OFFICER)
        self.login_as(self.admin, self.alpha)
        self.assertEqual(self.client.post(self.issue_url(self.field_m)).status_code, 403)
        self.assertFalse(StaffPasswordReset.objects.exists())

    def test_super_admin_cannot_be_reset(self):
        self.field.is_superuser = True
        self.field.is_staff = True
        self.field.save()
        self.login_as(self.admin, self.alpha)
        self.assertEqual(self.client.post(self.issue_url(self.field_m)).status_code, 403)
        self.assertFalse(StaffPasswordReset.objects.exists())

    def test_new_link_replaces_old_one(self):
        old = self.issue_link()
        new = self.issue_link()
        self.assertEqual(self.client.get(reverse("password_reset_accept", args=[old])).status_code, 404)
        self.assertEqual(self.client.get(reverse("password_reset_accept", args=[new])).status_code, 200)

    def test_staff_list_offers_reset_for_each_staff_member(self):
        self.login_as(self.admin, self.alpha)
        html = self.client.get(reverse("staff_list")).content.decode()
        for membership in (self.manager_m, self.field_m):
            self.assertIn(self.issue_url(membership), html)
        self.assertIn("Reset password", html)


class UseResetTests(ResetFixture):
    def accept_url(self, token):
        return reverse("password_reset_accept", args=[token])

    def test_link_sets_new_password_once(self):
        token = self.issue_link()
        self.assertEqual(self.client.get(self.accept_url(token)).status_code, 200)
        response = self.client.post(self.accept_url(token), {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD})
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
        self.field.refresh_from_db()
        self.assertTrue(self.field.check_password(NEW_PASSWORD))
        self.assertIsNotNone(StaffPasswordReset.objects.get(user=self.field).used_at)
        self.assertEqual(self.client.get(self.accept_url(token)).status_code, 404)

    def test_mismatched_passwords_change_nothing(self):
        token = self.issue_link()
        response = self.client.post(self.accept_url(token), {"new_password1": NEW_PASSWORD, "new_password2": "Other-Value-77"})
        self.assertEqual(response.status_code, 200)
        self.field.refresh_from_db()
        self.assertTrue(self.field.check_password("OldPassword!42"))
        self.assertIsNone(StaffPasswordReset.objects.get(user=self.field).used_at)

    def test_expired_link_is_refused(self):
        token = self.issue_link()
        StaffPasswordReset.objects.filter(user=self.field).update(expires_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(self.client.get(self.accept_url(token)).status_code, 404)
        self.client.post(self.accept_url(token), {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD})
        self.field.refresh_from_db()
        self.assertTrue(self.field.check_password("OldPassword!42"))

    def test_unknown_token_is_404(self):
        self.assertEqual(self.client.get(self.accept_url("not-a-real-token")).status_code, 404)

    def test_existing_sessions_end_after_reset(self):
        token = self.issue_link()
        other = self.client_class()
        other.force_login(self.field)
        session = other.session
        session[ActiveOrganisationMiddleware.SESSION_KEY] = self.alpha.pk
        session.save()
        self.assertEqual(other.get(reverse("field_home")).status_code, 200)
        self.client.post(self.accept_url(token), {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD})
        self.assertEqual(other.get(reverse("field_home")).status_code, 302)

    def test_reset_page_is_not_cached(self):
        token = self.issue_link()
        response = self.client.get(self.accept_url(token))
        self.assertIn("no-store", response.get("Cache-Control", ""))
