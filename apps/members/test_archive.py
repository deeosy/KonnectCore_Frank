"""Archiving members (UAT I-5). Records and historical reporting are kept."""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.collections.models import CollectionRecord
from apps.farms.models import Crop
from apps.groups.models import GroupMemberAssignment, StructureUnit
from apps.organisations.middleware import ActiveOrganisationMiddleware
from apps.organisations.models import Organisation, OrganisationMembership

from .models import Member, MemberHistory

User = get_user_model()


class MemberArchiveTests(TestCase):
    def setUp(self):
        self.org = Organisation.objects.create(name="Archive Org", slug="archive-org")
        self.manager, _ = self.user("manager@archive.test", "manager")
        self.officer, officer_membership = self.user("officer@archive.test", "field_officer")
        self.member = Member.objects.create(
            organisation=self.org, created_by=self.manager, updated_by=self.manager,
            membership_number="AR1", first_name="Arch", last_name="Ived", status=Member.Status.SUSPENDED,
        )
        self.kept = Member.objects.create(
            organisation=self.org, created_by=self.manager, updated_by=self.manager,
            membership_number="AR2", first_name="Kept", last_name="Active",
        )
        unit = StructureUnit.objects.create(organisation=self.org, name="Archive G", unit_type="group", field_officer=officer_membership)
        GroupMemberAssignment.objects.create(organisation=self.org, unit=unit, member=self.member)
        crop = Crop.objects.create(organisation=self.org, name="Maize")
        CollectionRecord.objects.create(
            organisation=self.org, member=self.member, crop=crop, quantity=Decimal("10"), quantity_unit="kg",
            collection_date=date(2026, 9, 1), collection_location="Point", price_per_unit=Decimal("5.00"),
            recorded_by=self.manager, notes="QA archived member collection",
        )

    def user(self, email, role):
        user = User.objects.create_user(email=email, password="x")
        membership = OrganisationMembership.objects.create(organisation=self.org, user=user, role=role)
        return user, membership

    def login(self, user):
        self.client.logout()
        self.client.force_login(user)
        session = self.client.session
        session[ActiveOrganisationMiddleware.SESSION_KEY] = self.org.pk
        session.save()

    def url(self):
        return reverse("member_archive", args=[self.member.pk])

    def archive(self, reason="Left the cooperative"):
        return self.client.post(self.url(), {"reason": reason})

    def status(self):
        self.member.refresh_from_db()
        return self.member.status

    def test_field_officer_cannot_archive(self):
        self.login(self.officer)
        self.assertNotEqual(self.client.get(self.url()).status_code, 200)
        self.archive()
        self.assertEqual(self.status(), Member.Status.SUSPENDED)

    def test_reason_required_and_entry_kept(self):
        self.login(self.manager)
        response = self.archive(reason="   ")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Give a reason for archiving this member.")
        self.assertEqual(self.status(), Member.Status.SUSPENDED)

    def test_archive_records_history_with_previous_status(self):
        self.login(self.manager)
        response = self.archive()
        self.assertRedirects(response, reverse("member_detail", args=[self.member.pk]), fetch_redirect_response=False)
        self.assertEqual(self.status(), Member.Status.ARCHIVED)
        event = MemberHistory.objects.get(member=self.member, action=MemberHistory.Action.ARCHIVED)
        self.assertEqual(event.actor, self.manager)
        self.assertEqual(event.changes, {"previous_status": "suspended", "new_status": "archived", "reason": "Left the cooperative"})
        detail = self.client.get(reverse("member_detail", args=[self.member.pk]))
        self.assertContains(detail, "Archived member.")
        self.assertContains(detail, "Restore member")

    def test_archived_hidden_from_default_list_but_filterable(self):
        self.login(self.manager)
        self.archive()
        default = self.client.get(reverse("member_list"))
        self.assertNotContains(default, "Arch Ived")
        self.assertContains(default, "Kept Active")
        filtered = self.client.get(reverse("member_list"), {"status": "archived"})
        self.assertContains(filtered, "Arch Ived")
        self.assertNotContains(filtered, "Kept Active")

    def test_archived_member_hidden_from_assigned_field_officer(self):
        self.login(self.officer)
        self.assertContains(self.client.get(reverse("field_home")), "Arch Ived")
        self.login(self.manager)
        self.archive()
        self.login(self.officer)
        self.assertNotContains(self.client.get(reverse("field_home")), "Arch Ived")

    def test_historical_reporting_kept(self):
        self.login(self.manager)
        self.archive()
        dashboard = self.client.get(reverse("dashboard"))
        self.assertEqual(dashboard.context["metrics"]["collections"], 1)
        self.assertEqual(dashboard.context["metrics"]["members"], 2)
        export = self.client.get(reverse("export_report", args=["collections", "csv"]))
        self.assertIn("Arch Ived", export.content.decode())
        self.assertEqual(CollectionRecord.objects.filter(member=self.member).count(), 1)

    def test_restore_returns_previous_status(self):
        self.login(self.manager)
        self.archive()
        self.assertContains(self.client.get(self.url()), "Suspended")
        response = self.client.post(self.url(), {"reason": "Archived by mistake"})
        self.assertRedirects(response, reverse("member_detail", args=[self.member.pk]), fetch_redirect_response=False)
        self.assertEqual(self.status(), Member.Status.SUSPENDED)
        event = MemberHistory.objects.get(member=self.member, action=MemberHistory.Action.RESTORED)
        self.assertEqual(event.changes["new_status"], "suspended")
        self.assertEqual(event.changes["reason"], "Archived by mistake")
