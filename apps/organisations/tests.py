import re
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from apps.organisations.invitations import StaffInvitation
from apps.organisations.middleware import ActiveOrganisationMiddleware
from apps.organisations.models import Organisation, OrganisationMembership, OrganisationOwnedModel
from django.db import models

User = get_user_model()

class TenantFixture(TestCase):
    def setUp(self):
        self.alpha = Organisation.objects.create(name="Alpha Cooperative", slug="alpha", currency="GHS")
        self.beta = Organisation.objects.create(name="Beta Farmers", slug="beta", currency="KES")
        self.alpha_admin = User.objects.create_user(email="admin@alpha.test", password="CorrectHorse!42")
        self.beta_admin = User.objects.create_user(email="admin@beta.test", password="CorrectHorse!42")
        self.manager = User.objects.create_user(email="manager@alpha.test", password="CorrectHorse!42")
        self.field = User.objects.create_user(email="field@alpha.test", password="CorrectHorse!42")
        OrganisationMembership.objects.create(organisation=self.alpha, user=self.alpha_admin, role=OrganisationMembership.Role.ADMIN)
        OrganisationMembership.objects.create(organisation=self.beta, user=self.beta_admin, role=OrganisationMembership.Role.ADMIN)
        OrganisationMembership.objects.create(organisation=self.alpha, user=self.manager, role=OrganisationMembership.Role.MANAGER)
        OrganisationMembership.objects.create(organisation=self.alpha, user=self.field, role=OrganisationMembership.Role.FIELD_OFFICER)

    def login_as(self, user, organisation=None):
        self.client.force_login(user)
        if organisation:
            session = self.client.session
            session[ActiveOrganisationMiddleware.SESSION_KEY] = organisation.pk
            session.save()

class AuthenticationTests(TenantFixture):
    def test_public_registration_route_does_not_exist(self):
        self.assertEqual(self.client.get("/register/").status_code, 404)

    def test_anonymous_workspace_redirects_to_login(self):
        response = self.client.get(reverse("workspace"))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('workspace')}")

    def test_email_login_opens_single_workspace(self):
        response = self.client.post(reverse("login"), {"username": "ADMIN@ALPHA.TEST", "password": "CorrectHorse!42"})
        self.assertRedirects(response, reverse("workspace"), fetch_redirect_response=False)
        response = self.client.get(reverse("workspace"))
        self.assertContains(response, "Alpha Cooperative")

    def test_manager_login_opens_organisation_dashboard(self):
        response = self.client.post(reverse("login"), {
            "username": self.manager.email,
            "password": "CorrectHorse!42",
        })
        self.assertRedirects(response, reverse("workspace"), fetch_redirect_response=False)

    def test_field_officer_login_opens_field_workspace(self):
        response = self.client.post(reverse("login"), {
            "username": self.field.email,
            "password": "CorrectHorse!42",
        })
        self.assertRedirects(response, reverse("field_home"), fetch_redirect_response=False)
        response = self.client.get(reverse("field_home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My assigned members")
        self.assertNotContains(response, "Payments &amp; Dues")

    def test_field_officer_workspace_entry_redirects_to_field_workspace(self):
        self.login_as(self.field, self.alpha)
        self.assertRedirects(self.client.get(reverse("workspace")), reverse("field_home"))

    def test_explicit_safe_next_url_is_preserved(self):
        response = self.client.post(
            f"{reverse('login')}?next={reverse('field_home')}",
            {"username": self.field.email, "password": "CorrectHorse!42"},
        )
        self.assertRedirects(response, reverse("field_home"), fetch_redirect_response=False)

class TenantIsolationTests(TenantFixture):
    def test_forged_session_cannot_select_another_organisation(self):
        self.login_as(self.alpha_admin, self.beta)
        response = self.client.get(reverse("workspace"))
        self.assertRedirects(response, reverse("choose_organisation"))
        response = self.client.get(reverse("choose_organisation"))
        self.assertContains(response, "Alpha Cooperative")
        self.assertNotContains(response, "Beta Farmers")

    def test_choose_workspace_rejects_other_tenant_id(self):
        self.login_as(self.alpha_admin)
        response = self.client.post(reverse("choose_organisation"), {"organisation": self.beta.pk})
        self.assertEqual(response.status_code, 404)

    def test_staff_listing_never_leaks_other_tenant(self):
        self.login_as(self.alpha_admin, self.alpha)
        response = self.client.get(reverse("staff_list"))
        self.assertContains(response, self.alpha_admin.email)
        self.assertContains(response, self.manager.email)
        self.assertNotContains(response, self.beta_admin.email)

    def test_suspended_organisation_has_no_active_workspace(self):
        self.alpha.status = Organisation.Status.SUSPENDED
        self.alpha.save(update_fields=["status"])
        self.login_as(self.alpha_admin, self.alpha)
        response = self.client.get(reverse("workspace"))
        self.assertRedirects(response, reverse("choose_organisation"))

class RolePermissionTests(TenantFixture):
    def test_manager_cannot_manage_staff(self):
        self.login_as(self.manager, self.alpha)
        for name in ("staff_list", "staff_create", "staff_invite"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403)

    def test_field_officer_cannot_manage_staff(self):
        self.login_as(self.field, self.alpha)
        self.assertEqual(self.client.get(reverse("staff_list")).status_code, 403)

    def test_admin_creates_user_only_in_active_tenant(self):
        self.login_as(self.alpha_admin, self.alpha)
        response = self.client.post(reverse("staff_create"), {
            "email": "new@alpha.test", "first_name": "New", "last_name": "Manager",
            "role": OrganisationMembership.Role.MANAGER,
            "password1": "StrongPass!845", "password2": "StrongPass!845",
        })
        self.assertRedirects(response, reverse("staff_list"))
        user = User.objects.get(email="new@alpha.test")
        self.assertTrue(OrganisationMembership.objects.filter(user=user, organisation=self.alpha).exists())
        self.assertFalse(OrganisationMembership.objects.filter(user=user, organisation=self.beta).exists())

class PlatformOnboardingTests(TenantFixture):
    def setUp(self):
        super().setUp()
        self.platform_admin = User.objects.create_superuser(email="owner@konnectcore.test", password="OwnerPass!52")

    def test_organisation_user_cannot_open_platform_area(self):
        self.login_as(self.alpha_admin, self.alpha)
        response = self.client.get(reverse("platform_organisations"))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('platform_organisations')}")

    def test_super_admin_creates_workspace_and_first_admin_invitation(self):
        self.client.force_login(self.platform_admin)
        response = self.client.post(reverse("platform_organisation_create"), {
            "name": "Gamma Growers", "slug": "gamma", "currency": "UGX", "status": Organisation.Status.ACTIVE,
            "admin_email": "admin@gamma.test", "admin_first_name": "Grace", "admin_last_name": "A",
        })
        self.assertEqual(response.status_code, 200)
        gamma = Organisation.objects.get(slug="gamma")
        invitation = StaffInvitation.objects.get(organisation=gamma)
        self.assertEqual(invitation.role, OrganisationMembership.Role.ADMIN)
        self.assertFalse(User.objects.filter(email="admin@gamma.test").exists())
        self.assertNotContains(response, invitation.token_hash)
        self.assertContains(response, "/invitations/")

class InvitationSecurityTests(TenantFixture):
    def test_invitation_token_is_hashed_and_single_use(self):
        invitation, token = StaffInvitation.issue(organisation=self.alpha, email="invitee@alpha.test", role=OrganisationMembership.Role.FIELD_OFFICER, invited_by=self.alpha_admin)
        self.assertNotEqual(invitation.token_hash, token)
        self.assertEqual(len(invitation.token_hash), 64)
        url = reverse("accept_invitation", args=[token])
        response = self.client.post(url, {"first_name": "Ivy", "last_name": "Officer", "password1": "StrongPass!942", "password2": "StrongPass!942"})
        self.assertRedirects(response, reverse("field_home"))
        membership = OrganisationMembership.objects.get(user__email="invitee@alpha.test", organisation=self.alpha)
        self.assertEqual(membership.role, OrganisationMembership.Role.FIELD_OFFICER)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_expired_invitation_is_denied(self):
        invitation, token = StaffInvitation.issue(organisation=self.alpha, email="late@alpha.test", role=OrganisationMembership.Role.MANAGER, invited_by=self.alpha_admin)
        invitation.expires_at = timezone.now() - timezone.timedelta(seconds=1)
        invitation.save(update_fields=["expires_at"])
        self.assertEqual(self.client.get(reverse("accept_invitation", args=[token])).status_code, 403)

class PlatformAdministrationTests(TenantFixture):
    def setUp(self):
        super().setUp()
        self.owner = User.objects.create_superuser(email="platform-owner@konnectcore.test", password="OwnerPass!63")

    def test_platform_list_shows_user_and_member_counts(self):
        from apps.members.models import Member
        Member.objects.create(organisation=self.alpha, created_by=self.alpha_admin, updated_by=self.alpha_admin, membership_number="COUNT-1", first_name="Count", last_name="Member")
        self.client.force_login(self.owner)
        response = self.client.get(reverse("platform_organisations"))
        self.assertContains(response, "Alpha Cooperative")
        self.assertContains(response, reverse("platform_organisation_detail", args=[self.alpha.pk]))
        alpha = response.context["organisations"].get(pk=self.alpha.pk)
        self.assertEqual(alpha.user_count, 3)
        self.assertEqual(alpha.member_count, 1)

    def test_only_super_admin_can_open_platform_detail(self):
        self.login_as(self.alpha_admin, self.alpha)
        url = reverse("platform_organisation_detail", args=[self.alpha.pk])
        self.assertRedirects(self.client.get(url), f"{reverse('login')}?next={url}")
        self.client.force_login(self.owner)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.alpha_admin.email)
        self.assertNotContains(response, self.beta_admin.email)

    def test_super_admin_can_suspend_organisation(self):
        self.client.force_login(self.owner)
        url = reverse("platform_organisation_detail", args=[self.alpha.pk])
        response = self.client.post(url, {"status": Organisation.Status.SUSPENDED})
        self.assertRedirects(response, url)
        self.alpha.refresh_from_db()
        self.assertEqual(self.alpha.status, Organisation.Status.SUSPENDED)
        self.client.logout()
        self.login_as(self.alpha_admin, self.alpha)
        self.assertRedirects(self.client.get(reverse("workspace")), reverse("choose_organisation"))

    def test_platform_detail_unknown_organisation_is_404(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("platform_organisation_detail", args=[999999])).status_code, 404)
