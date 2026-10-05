"""Field Workspace for Admins/Managers has real actions, not dead-end cards (UAT I-9)."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.groups.models import GroupMemberAssignment, StructureUnit
from apps.members.models import Member
from apps.organisations.middleware import ActiveOrganisationMiddleware
from apps.organisations.models import Organisation, OrganisationMembership

User = get_user_model()


class ManagerFieldWorkspaceTests(TestCase):
    def setUp(self):
        self.org = Organisation.objects.create(name="Workspace Org", slug="workspace-org")
        self.admin = self.user("admin@ws.test", "admin")
        self.manager = self.user("manager@ws.test", "manager")
        self.officer = self.user("officer@ws.test", "field_officer")
        officer_membership = OrganisationMembership.objects.get(organisation=self.org, user=self.officer)
        self.member = Member.objects.create(
            organisation=self.org, created_by=self.admin, updated_by=self.admin,
            membership_number="W1", first_name="Wura", last_name="Workspace",
        )
        unit = StructureUnit.objects.create(organisation=self.org, name="WS G", unit_type="group", field_officer=officer_membership)
        GroupMemberAssignment.objects.create(organisation=self.org, unit=unit, member=self.member)

    def user(self, email, role):
        user = User.objects.create_user(email=email, password="x")
        OrganisationMembership.objects.create(organisation=self.org, user=user, role=role)
        return user

    def login(self, user):
        self.client.logout()
        self.client.force_login(user)
        session = self.client.session
        session[ActiveOrganisationMiddleware.SESSION_KEY] = self.org.pk
        session.save()

    def admin_links(self):
        return (
            reverse("member_detail", args=[self.member.pk]),
            f"{reverse('farm_create')}?member={self.member.pk}",
            f"{reverse('collection_create')}?member={self.member.pk}",
        )

    def test_manager_and_admin_cards_have_actions(self):
        for user in (self.manager, self.admin):
            self.login(user)
            response = self.client.get(reverse("field_home"))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "All members (field view)")
            self.assertContains(response, "View profile")
            for link in self.admin_links():
                self.assertContains(response, link)
            self.assertNotContains(response, reverse("field_visit_add", args=[self.member.pk]))

    def test_admin_actions_open_working_pages(self):
        self.login(self.manager)
        for link in self.admin_links():
            self.assertEqual(self.client.get(link).status_code, 200, link)

    def test_field_officer_cards_unchanged(self):
        self.login(self.officer)
        response = self.client.get(reverse("field_home"))
        self.assertContains(response, "My assigned members")
        self.assertContains(response, reverse("field_visit_add", args=[self.member.pk]))
        self.assertContains(response, reverse("field_collection_add", args=[self.member.pk]))
        self.assertNotContains(response, "All members (field view)")
        self.assertNotContains(response, f"{reverse('farm_create')}?member={self.member.pk}")
